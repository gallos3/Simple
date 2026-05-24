"""
Simple - Legal Knowledge Graph Ingestion
=========================================
Reads legal_corpus.jsonl and ingests it into Neo4j as a structured
knowledge graph alongside the existing procurement data.

Node labels added:
  :LegalAct     — A law, directive, or regulation
  :Article      — A specific article / provision within a LegalAct
  :LegalConcept — A procurement concept (e.g. DirectAward, TaxClearance)
  :ProcStage    — A procurement stage (Evaluation, Award, Execution...)
  :LegalDecision — A court or authority decision

Relationships added:
  (:Article)-[:PART_OF]->(:LegalAct)
  (:Article)-[:REGULATES]->(:LegalConcept)
  (:Article)-[:APPLIES_AT]->(:ProcStage)
  (:LegalDecision)-[:INTERPRETS]->(:Article)

Run once:
  cd backend && python legal_graph_ingest.py
"""

import json
import re
from pathlib import Path
from database import get_session

BASE_DIR = Path(__file__).resolve().parent
CORPUS_PATH = BASE_DIR / "legal_corpus.jsonl"

# =============================================================================
# STAGE CLASSIFICATION
# Keywords → ProcurementStage
# =============================================================================
STAGE_KEYWORDS = {
    "Planning":     ["σχεδιασμ", "προγραμματισμ", "planning", "needs assessment"],
    "Tendering":    ["προκήρυξ", "διακήρυξ", "tender", "notice", "διαγωνισμ"],
    "Evaluation":   ["αξιολόγηση", "προσφορ", "evaluation", "award criteria",
                     "δικαιολογητ", "υπεύθυνη δήλωση", "αποκλεισμ"],
    "Award":        ["ανάθεση", "κατακύρωση", "award", "σύμβαση", "contract"],
    "Execution":    ["εκτέλεση", "execution", "παράδοση", "delivery", "τιμολόγ"],
    "Control":      ["έλεγχος", "audit", "παράβαση", "violation", "ελεγκτ",
                     "κύρωση", "sanction"],
}

# =============================================================================
# CONCEPT CLASSIFICATION
# Keywords → LegalConcept
# =============================================================================
CONCEPT_KEYWORDS = {
    "DirectAward":          ["απευθείας ανάθεση", "direct award", "χωρίς διαγωνισμ"],
    "DirectAwardThreshold": ["30.000", "60.000", "threshold", "όριο", "ανώτατο ποσό"],
    "ContractSplitting":    ["κατάτμηση", "splitting", "τμηματοποίηση"],
    "TaxClearance":         ["φορολογική ενημερότητα", "tax clearance", "φορολογικ"],
    "InsuranceClearance":   ["ασφαλιστική ενημερότητα", "insurance clearance"],
    "AbnormallyLowTender":  ["ασυνήθιστα χαμηλή", "abnormally low", "υπερβολικά χαμηλή"],
    "ConflictOfInterest":   ["σύγκρουση συμφερόντων", "conflict of interest"],
    "MarketConsultation":   ["προκαταρκτική διαβούλευση", "market consultation"],
    "TechnicalSpecs":       ["τεχνικές προδιαγραφές", "technical specifications",
                              "φωτογραφικ"],
    "EvaluationCriteria":   ["κριτήρια αξιολόγησης", "award criteria", "πλέον συμφέρουσα"],
    "ExclusionGrounds":     ["λόγοι αποκλεισμού", "exclusion grounds", "αποκλεισμ"],
    "FrameworkAgreement":   ["συμφωνία πλαίσιο", "framework agreement"],
    "Subcontracting":       ["υπεργολαβία", "subcontracting"],
    "ContractModification": ["τροποποίηση σύμβασης", "contract modification", "αναθεώρηση"],
}

# =============================================================================
# SOURCE PARSING
# =============================================================================

def parse_source(source: str) -> dict:
    """
    Parses a source string into structured metadata.
    Handles real corpus formats:
      - ν.4412_16  → Ν.4412/2016
      - ν.5164_24  → Ν.5164/2024
      - 9Χ9ΜΟΞΤΒ-Δ63 (ADA code) → ΕΑΔΗΣΥ decision
      - Το σύνταγμα της Ελλάδας → Greek Constitution
      - guidance_public_procurement_2018_en → EU guidance
    """
    result = {
        "law_name": None,
        "law_short": None,
        "article_num": None,
        "is_decision": False,
        "court": None,
        "case_ref": None,
    }

    s = source.strip()

    # === Greek ADA decision codes: mix of CAPS Greek letters + digits + dash ===
    # Pattern: 8+ chars of [A-Z Greek uppercase] and digits, containing a dash
    import unicodedata
    def is_ada_code(text):
        """Returns True if text looks like a Greek ADA code (e.g. 9Χ9ΜΟΞΤΒ-Δ63)"""
        if '-' not in text:
            return False
        clean = text.replace('-', '')
        if len(clean) < 6:
            return False
        # ADA codes contain Greek uppercase letters
        greek_count = sum(1 for c in clean if unicodedata.category(c) == 'Lu'
                         and ord(c) > 127)
        return greek_count >= 2

    if is_ada_code(s):
        result["is_decision"] = True
        result["court"] = "EAADHSY"
        result["case_ref"] = s
        return result

    # === CJEU case references (e.g. C-425/14) ===
    if re.search(r'C-\d+/\d+', s):
        result["is_decision"] = True
        result["court"] = "CJEU"
        m = re.search(r'(C-\d+/\d+)', s)
        if m:
            result["case_ref"] = m.group(1)
        return result

    # === Greek laws: ν.4412_16 or ν.5164_24 ===
    m = re.search(r'[νΝ]\.?(\d{3,5})_(\d{2,4})', s)
    if m:
        num = m.group(1)
        yr = m.group(2)
        if len(yr) == 2:
            yr = '20' + yr if int(yr) < 50 else '19' + yr
        result["law_short"] = f"N.{num}/{yr}"
        result["law_name"] = f"Νόμος {num}/{yr}"
        return result

    # === EU Directives ===
    m2 = re.search(r'(Directive|Οδηγία)\s+(\d{4}/\d+/\w+)', s, re.IGNORECASE)
    if m2:
        result["law_short"] = f"Dir.{m2.group(2)}"
        result["law_name"] = f"Directive {m2.group(2)}"
        return result

    # === Greek Constitution ===
    if 'σύνταγμα' in s.lower() or 'constitution' in s.lower():
        result["law_short"] = "GR_CONST"
        result["law_name"] = "Σύνταγμα της Ελλάδας"
        return result

    # === EU/International guidance documents ===
    if 'guidance' in s.lower() or 'common mistakes' in s.lower() or re.match(r'[0-9a-f]{6,}-', s):
        result["law_short"] = "EU_GUIDANCE"
        result["law_name"] = "EU Procurement Guidance"
        return result

    # === Fallback: use source as-is ===
    result["law_short"] = s[:40].replace(' ', '_') if s else "UNKNOWN"
    result["law_name"] = s[:100] if s else "Unknown"
    return result



def classify_stages(text: str) -> list:
    """Returns list of ProcStage names relevant to the text."""
    t = text.lower()
    stages = []
    for stage, keywords in STAGE_KEYWORDS.items():
        if any(k in t for k in keywords):
            stages.append(stage)
    return stages or ["General"]


def classify_concepts(text: str) -> list:
    """Returns list of LegalConcept names relevant to the text."""
    t = text.lower()
    concepts = []
    for concept, keywords in CONCEPT_KEYWORDS.items():
        if any(k in t for k in keywords):
            concepts.append(concept)
    return concepts


# =============================================================================
# NEO4J INGESTION
# =============================================================================

def create_constraints(session):
    """Creates uniqueness constraints for the legal graph."""
    constraints = [
        "CREATE CONSTRAINT legal_act_name IF NOT EXISTS FOR (n:LegalAct) REQUIRE n.short_name IS UNIQUE",
        "CREATE CONSTRAINT article_id IF NOT EXISTS FOR (n:Article) REQUIRE n.article_id IS UNIQUE",
        "CREATE CONSTRAINT legal_concept_name IF NOT EXISTS FOR (n:LegalConcept) REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT proc_stage_name IF NOT EXISTS FOR (n:ProcStage) REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT legal_decision_ref IF NOT EXISTS FOR (n:LegalDecision) REQUIRE n.case_ref IS UNIQUE",
    ]
    for c in constraints:
        try:
            session.run(c)
        except Exception as e:
            print(f"  [!] Constraint warning (may already exist): {e}")


def ingest_doc(session, doc: dict, idx: int):
    """Ingests a single legal corpus entry into Neo4j."""
    source = doc.get("source", "")
    text = doc.get("text", "")
    doc_id = doc.get("id", f"doc_{idx}")

    meta = parse_source(source)

    if meta["is_decision"]:
        # === LEGAL DECISION ===
        case_ref = meta["case_ref"] or doc_id
        court = meta["court"] or "Unknown"

        session.run("""
            MERGE (d:LegalDecision {case_ref: $case_ref})
            SET d.court = $court,
                d.source = $source,
                d.summary = $text,
                d.corpus_id = $doc_id
        """, case_ref=case_ref, court=court, source=source,
             text=text[:500], doc_id=doc_id)

        # Link to concepts
        for concept in classify_concepts(text):
            session.run("""
                MERGE (c:LegalConcept {name: $concept})
                WITH c
                MATCH (d:LegalDecision {case_ref: $case_ref})
                MERGE (d)-[:CLARIFIES]->(c)
            """, concept=concept, case_ref=case_ref)

    else:
        # === LAW / DIRECTIVE ARTICLE ===
        law_short = meta["law_short"]
        law_name = meta["law_name"]
        article_num = meta["article_num"]

        if not law_short:
            # Unclassified — store as generic article
            law_short = "OTHER"
            law_name = source[:100] if source else "Unknown"

        article_id = f"{law_short}_art{article_num}" if article_num else f"{law_short}_{doc_id}"

        # Create LegalAct
        session.run("""
            MERGE (la:LegalAct {short_name: $short_name})
            SET la.full_name = $full_name
        """, short_name=law_short, full_name=law_name)

        # Create Article
        session.run("""
            MERGE (a:Article {article_id: $article_id})
            SET a.article_num = $article_num,
                a.source = $source,
                a.text = $text,
                a.corpus_id = $doc_id
            WITH a
            MATCH (la:LegalAct {short_name: $law_short})
            MERGE (a)-[:PART_OF]->(la)
        """, article_id=article_id, article_num=article_num,
             source=source, text=text, doc_id=doc_id,
             law_short=law_short)

        # Link to ProcStages
        for stage in classify_stages(text):
            session.run("""
                MERGE (s:ProcStage {name: $stage})
                WITH s
                MATCH (a:Article {article_id: $article_id})
                MERGE (a)-[:APPLIES_AT]->(s)
            """, stage=stage, article_id=article_id)

        # Link to LegalConcepts
        for concept in classify_concepts(text):
            session.run("""
                MERGE (c:LegalConcept {name: $concept})
                WITH c
                MATCH (a:Article {article_id: $article_id})
                MERGE (a)-[:REGULATES]->(c)
            """, concept=concept, article_id=article_id)


def ingest_all():
    """Main ingestion function."""
    if not CORPUS_PATH.exists():
        print(f"[!] Corpus not found: {CORPUS_PATH}")
        return

    docs = []
    with open(CORPUS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    docs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    print(f"[legal_graph_ingest] Found {len(docs)} corpus entries to ingest...")

    with get_session() as session:
        print("[legal_graph_ingest] Creating constraints...")
        create_constraints(session)

        ok = 0
        errors = 0
        for i, doc in enumerate(docs):
            try:
                ingest_doc(session, doc, i)
                ok += 1
                if (i + 1) % 100 == 0:
                    print(f"  [{i+1}/{len(docs)}] processed...")
            except Exception as e:
                errors += 1
                print(f"  [!] Error on doc {i} ({doc.get('id','?')}): {e}")

    print(f"\n[legal_graph_ingest] Done. {ok} OK, {errors} errors.")
    print("[legal_graph_ingest] Legal knowledge graph is ready in Neo4j.")


def print_summary():
    """Prints a summary of what was ingested."""
    with get_session() as session:
        r = session.run("""
            MATCH (la:LegalAct) WITH count(la) as acts
            MATCH (a:Article) WITH acts, count(a) as articles
            MATCH (c:LegalConcept) WITH acts, articles, count(c) as concepts
            MATCH (s:ProcStage) WITH acts, articles, concepts, count(s) as stages
            MATCH (d:LegalDecision) WITH acts, articles, concepts, stages, count(d) as decisions
            RETURN acts, articles, concepts, stages, decisions
        """).single()
        if r:
            print("\n=== Legal Graph Summary ===")
            print(f"  :LegalAct      {r['acts']}")
            print(f"  :Article       {r['articles']}")
            print(f"  :LegalConcept  {r['concepts']}")
            print(f"  :ProcStage     {r['stages']}")
            print(f"  :LegalDecision {r['decisions']}")


if __name__ == "__main__":
    ingest_all()
    print_summary()
