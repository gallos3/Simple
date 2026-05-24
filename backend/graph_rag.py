"""
Simple - GraphRAG Module
=========================
Replaces text-similarity (FAISS) retrieval with structured graph traversal.

Instead of: "find text chunks similar to this query"
We do:      "traverse the legal knowledge graph via concept/stage relationships"

This guarantees:
  - No hallucinated article references
  - Context is always relevant (graph-constrained)
  - LLM receives structured facts, not raw text similarity

Main entry points:
  search_by_concept(concept_name)   -> list of article texts
  search_by_stage(stage_name)       -> list of article texts
  search_for_query(user_query)      -> list of article texts (auto-routes)
  get_legal_context(user_query)     -> formatted string for LLM prompt
"""

import re
from typing import List, Optional
from database import get_session

# =============================================================================
# KEYWORD → CONCEPT / STAGE MAPPING
# (same logic as in legal_graph_ingest.py, mirrored here for routing)
# =============================================================================

QUERY_TO_CONCEPT = {
    # Απευθείας Ανάθεση & Συνώνυμα
    "απευθείας ανάθεση":    "DirectAward",
    "direct award":         "DirectAward",
    "χωρίς προκήρυξη":      "DirectAward",
    "χωρίς διαφάνεια":      "DirectAward",
    "επιλογή φορέα":        "DirectAward",
    "χωρίς δημοσιότητα":    "DirectAward",
    "άρθρο 118":            "DirectAward",
    "αδιαφάνεια":           "DirectAward",
    
    # Κατάτμηση & Συνώνυμα
    "κατάτμηση":            "ContractSplitting",
    "splitting":            "ContractSplitting",
    "τεμαχισμός":           "ContractSplitting",
    "τεχνητή κατάτμηση":    "ContractSplitting",
    "σπάσιμο σύμβασης":     "ContractSplitting",
    
    # Ενημερότητες
    "φορολογική":           "TaxClearance",
    "tax clearance":        "TaxClearance",
    "ασφαλιστική":          "InsuranceClearance",
    "insurance clearance":  "InsuranceClearance",
    
    # Προσφορές & Αξιολόγηση
    "χαμηλή προσφορά":      "AbnormallyLowTender",
    "abnormally low":       "AbnormallyLowTender",
    "ασυνήθιστα χαμηλή":    "AbnormallyLowTender",
    "κριτήρια":             "EvaluationCriteria",
    "award criteria":       "EvaluationCriteria",
    "τεχνικές προδιαγραφές":"TechnicalSpecs",
    "προδιαγραφές":         "TechnicalSpecs",
    "technical spec":       "TechnicalSpecs",
    
    # Σύγκρουση Συμφερόντων & Αποκλεισμός
    "σύγκρουση":            "ConflictOfInterest",
    "conflict of interest": "ConflictOfInterest",
    "συμφέροντα":           "ConflictOfInterest",
    "αποκλεισμ":            "ExclusionGrounds",
    "exclusion":            "ExclusionGrounds",
    "ποινικό μητρώο":       "ExclusionGrounds",
    
    # Ειδικές Διαδικασίες
    "πλαίσιο":              "FrameworkAgreement",
    "framework":            "FrameworkAgreement",
    "συμφωνία-πλαίσιο":     "FrameworkAgreement",
    "υπεργολαβ":            "Subcontracting",
    "subcontract":          "Subcontracting",
    "τροποποίηση":          "ContractModification",
    "modification":         "ContractModification",
    "παράταση":             "ContractModification",
    "διαβούλευση":          "MarketConsultation",
    "market consultation":  "MarketConsultation",
    
    # Όρια
    "όριο":                 "DirectAwardThreshold",
    "threshold":            "DirectAwardThreshold",
    "30.000":               "DirectAwardThreshold",
    "60.000":               "DirectAwardThreshold",
    "χρηματικό όριο":       "DirectAwardThreshold",
}

QUERY_TO_STAGE = {
    "αξιολόγηση":           "Evaluation",
    "evaluation":           "Evaluation",
    "προσφορά":             "Evaluation",
    "tender":               "Tendering",
    "προκήρυξ":             "Tendering",
    "διακήρυξ":             "Tendering",
    "ανάθεση":              "Award",
    "award":                "Award",
    "κατακύρωση":           "Award",
    "εκτέλεση":             "Execution",
    "execution":            "Execution",
    "έλεγχος":              "Control",
    "audit":                "Control",
    "σχεδιασμ":             "Planning",
    "planning":             "Planning",
}


# =============================================================================
# GRAPH RETRIEVAL FUNCTIONS
# =============================================================================

def search_by_concept(concept_name: str, limit: int = 5) -> List[dict]:
    """
    Returns articles that REGULATE a given LegalConcept,
    plus any LegalDecision that CLARIFIES that concept.
    """
    results = []
    with get_session() as session:
        # Articles regulating the concept
        rows = session.run("""
            MATCH (a:Article)-[:REGULATES]->(c:LegalConcept {name: $concept})
            MATCH (a)-[:PART_OF]->(law:LegalAct)
            RETURN a.article_id AS id,
                   a.source     AS source,
                   a.text       AS text,
                   law.short_name AS law,
                   'article' AS type
            ORDER BY size(a.text) DESC
            LIMIT $limit
        """, concept=concept_name, limit=limit)

        for row in rows:
            results.append({
                "id":     row["id"],
                "source": row["source"],
                "text":   row["text"],
                "law":    row["law"],
                "type":   row["type"],
            })

        # Decisions clarifying the concept
        decisions = session.run("""
            MATCH (d:LegalDecision)-[:CLARIFIES]->(c:LegalConcept {name: $concept})
            RETURN d.case_ref AS id,
                   d.court    AS source,
                   d.summary  AS text,
                   d.court    AS law,
                   'decision' AS type
            LIMIT 2
        """, concept=concept_name)

        for row in decisions:
            results.append({
                "id":     row["id"],
                "source": row["source"],
                "text":   row["text"],
                "law":    row["law"],
                "type":   row["type"],
            })

    return results


def search_by_stage(stage_name: str, limit: int = 5) -> List[dict]:
    """
    Returns articles that APPLY_AT a given ProcStage.
    """
    results = []
    with get_session() as session:
        rows = session.run("""
            MATCH (a:Article)-[:APPLIES_AT]->(s:ProcStage {name: $stage})
            MATCH (a)-[:PART_OF]->(law:LegalAct)
            RETURN a.article_id AS id,
                   a.source     AS source,
                   a.text       AS text,
                   law.short_name AS law,
                   'article' AS type
            ORDER BY size(a.text) DESC
            LIMIT $limit
        """, stage=stage_name, limit=limit)

        for row in rows:
            results.append({
                "id":     row["id"],
                "source": row["source"],
                "text":   row["text"],
                "law":    row["law"],
                "type":   row["type"],
            })
    return results


def search_by_law(law_short: str, limit: int = 5) -> List[dict]:
    """
    Returns articles from a specific LegalAct.
    """
    results = []
    with get_session() as session:
        rows = session.run("""
            MATCH (a:Article)-[:PART_OF]->(law:LegalAct {short_name: $law})
            RETURN a.article_id AS id,
                   a.source     AS source,
                   a.text       AS text,
                   law.short_name AS law,
                   'article' AS type
            ORDER BY size(a.text) DESC
            LIMIT $limit
        """, law=law_short, limit=limit)

        for row in rows:
            results.append({
                "id":     row["id"],
                "source": row["source"],
                "text":   row["text"],
                "law":    row["law"],
                "type":   row["type"],
            })
    return results


# =============================================================================
# AUTO-ROUTING: query → concept + stage → graph traversal
# =============================================================================

def _detect_concepts(query: str) -> List[str]:
    """Maps user query to LegalConcept names. Falls back to LLM semantic routing if keywords fail."""
    q = query.lower()
    found = []
    seen = set()
    
    # 1. Fast Path: Lexical Keyword Matching
    for kw, concept in QUERY_TO_CONCEPT.items():
        if kw in q and concept not in seen:
            found.append(concept)
            seen.add(concept)
            
    # 2. Semantic Path: Zero-Shot LLM Router (if no keywords matched)
    if not found:
        try:
            from llm_interface import get_llm
            llm = get_llm()
            if llm:
                prompt = f"""<|im_start|>system
You are a legal AI router. Map the user query to the most relevant LegalConcept from this list:
- DirectAward (απευθείας ανάθεση, επιλογή φορέα χωρίς διαγωνισμό, αδιαφάνεια, κλειστή διαδικασία)
- ContractSplitting (κατάτμηση, τεμαχισμός συμβάσεων για αποφυγή ορίων)
- AbnormallyLowTender (ασυνήθιστα χαμηλή προσφορά)
- ConflictOfInterest (σύγκρουση συμφερόντων)
- ExclusionGrounds (λόγοι αποκλεισμού, ποινικό μητρώο, καταδίκη)
- EvaluationCriteria (κριτήρια αξιολόγησης, ανάθεση)
- TechnicalSpecs (τεχνικές προδιαγραφές, απαιτήσεις)
If none match, output 'None'. Output ONLY the concept name.<|im_end|>
<|im_start|>user
Query: {query}<|im_end|>
<|im_start|>assistant
"""
                response = llm(prompt, max_tokens=15, temperature=0.0)
                text = response["choices"][0]["text"].strip()
                valid_concepts = [
                    "DirectAward", "ContractSplitting", "AbnormallyLowTender", 
                    "ConflictOfInterest", "ExclusionGrounds", "EvaluationCriteria", "TechnicalSpecs"
                ]
                for c in valid_concepts:
                    if c in text:
                        print(f"[GraphRAG] LLM Routed '{query}' -> {c}")
                        found.append(c)
                        break
        except Exception as e:
            print(f"[GraphRAG] LLM Routing failed: {e}")
            
    return found


def _detect_stages(query: str) -> List[str]:
    """Maps user query to ProcStage names."""
    q = query.lower()
    found = []
    seen = set()
    for kw, stage in QUERY_TO_STAGE.items():
        if kw in q and stage not in seen:
            found.append(stage)
            seen.add(stage)
    return found


def search_for_query(query: str, limit_per_source: int = 3) -> List[dict]:
    """
    Main retrieval function. Auto-routes by detecting concepts and stages.
    Falls back to stage 'General' if nothing matches.
    """
    results = []
    seen_ids = set()

    concepts = _detect_concepts(query)
    stages = _detect_stages(query)

    for concept in concepts[:2]:  # max 2 concepts
        for item in search_by_concept(concept, limit=limit_per_source):
            if item["id"] not in seen_ids:
                results.append(item)
                seen_ids.add(item["id"])

    for stage in stages[:2]:  # max 2 stages
        for item in search_by_stage(stage, limit=limit_per_source):
            if item["id"] not in seen_ids:
                results.append(item)
                seen_ids.add(item["id"])

    # Fallback: general articles
    if not results:
        for item in search_by_stage("General", limit=3):
            if item["id"] not in seen_ids:
                results.append(item)
                seen_ids.add(item["id"])

    return results[:10]  # never return more than 10


def get_legal_context(query: str) -> str:
    """
    Returns a formatted string ready to inject into an LLM prompt.
    This is the main interface used by streaming_endpoint.py and agent_modules.py.
    """
    items = search_for_query(query)
    if not items:
        return ""

    parts = []
    for item in items:
        law = item.get("law", "")
        source = item.get("source", "")
        text = (item.get("text") or "")[:400]
        ref = f"[{law} — {source}]" if law else f"[{source}]"
        parts.append(f"{ref}\n{text}")

    return "\n\n---\n\n".join(parts)


def get_concepts_for_query(query: str) -> List[str]:
    """Returns matched LegalConcept names for a query (useful for game engine)."""
    return _detect_concepts(query)


def get_stages_for_query(query: str) -> List[str]:
    """Returns matched ProcStage names for a query (useful for game engine)."""
    return _detect_stages(query)


def search_graph_corpus(query: str, top_k: int = 5) -> List[str]:
    """
    Drop-in replacement for legal_rag.search_legal_corpus().
    Returns a list of text strings (same interface) but uses graph traversal
    instead of FAISS cosine similarity.
    No embedding model loaded — zero extra memory.
    """
    items = search_for_query(query, limit_per_source=top_k)
    passages = []
    for item in items:
        law = item.get("law", "")
        source = item.get("source", "")
        text = (item.get("text") or "")
        ref = f"[{law} — {source}]\n" if law else f"[{source}]\n"
        passages.append(ref + text)
    return passages


# =============================================================================
# QUICK TEST
# =============================================================================
if __name__ == "__main__":
    test_queries = [
        "απευθείας ανάθεση κατάτμηση",
        "αξιολόγηση προσφορών φορολογική ενημερότητα",
        "audit έλεγχος παραβάσεις",
        "direct award threshold 30000",
    ]
    for q in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {q}")
        concepts = _detect_concepts(q)
        stages = _detect_stages(q)
        print(f"  Concepts: {concepts}")
        print(f"  Stages:   {stages}")
        items = search_for_query(q)
        print(f"  Results:  {len(items)} articles/decisions")
        if items:
            print(f"  First:    [{items[0]['law']}] {items[0]['text'][:100]}...")
