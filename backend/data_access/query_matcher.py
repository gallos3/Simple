"""
Simple - Query Matcher
Semantic matching of natural language questions to predefined Cypher queries.
"""

import re
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

from utils.config import SIMILARITY_THRESHOLD, EMBEDDINGS_PATH

# =============================================================================
# EMBEDDER (Lazy Loading)
# =============================================================================
_embedder = None
_query_embeddings = None

def get_embedder():
    """Lazy load the sentence transformer model."""
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer(str(EMBEDDINGS_PATH))
        except Exception as e:
            print(f"⚠️ Could not load embedder: {e}")
            _embedder = False  # Mark as failed
    return _embedder if _embedder else None
def _get_query_texts(q: Dict) -> List[str]:
    """Επιστρέφει όλες τις παραλλαγές ερώτησης ενός query."""
    val = q.get("question") or q.get("questions") or q.get("description", "")
    if isinstance(val, list):
        return [v for v in val if v]
    elif isinstance(val, str) and val:
        return [val]
    return []
def _compute_query_embeddings(queries: List[Dict]) -> Dict[str, any]:
    global _query_embeddings
    if _query_embeddings is not None:
        return _query_embeddings

    embedder = get_embedder()
    if not embedder:
        return {}

    _query_embeddings = {}
    for q in queries:
        texts = _get_query_texts(q)
        if not texts:
            continue
        qid = str(q["id"])
        # Κράτα ΟΛΑ τα embeddings ξεχωριστά (όχι mean)
        _query_embeddings[qid] = embedder.encode(texts, convert_to_tensor=True)

    return _query_embeddings

# =============================================================================
# SEMANTIC MATCHING
# =============================================================================
def get_query_match(
    question: str,
    queries: List[Dict],
    has_entity: bool = False,
    threshold: float = None
) -> Optional[Tuple[Dict, float]]:
    """
    Find the best matching predefined query using semantic similarity.
    
    Args:
        question: User's natural language question
        queries: List of predefined query dictionaries
        has_entity: Whether an entity was extracted (affects scoring)
        threshold: Minimum similarity score (uses config default if None)
    
    Returns:
        Tuple of (matched_query, score) or None if no match above threshold
    """
    if threshold is None:
        threshold = SIMILARITY_THRESHOLD

    # --- Parameter-Aware Filtering ---
    from data_access.entity_extractor import extract_year_from_question
    year_found = bool(extract_year_from_question(question))
    
    valid_queries = []
    for q in queries:
        cypher = str(q.get("cypher", "")) + str(q.get("query", ""))
        requires_entity = any(p in cypher for p in ["{αναθέτουσα}", "{Buyer}", "$name"])
        requires_year = any(p in cypher for p in ["{έτος}", "{year}", "$year"])
        
        if requires_entity and not has_entity:
            continue
        if requires_year and not year_found:
            continue
        valid_queries.append(q)
        
    if valid_queries:
        queries = valid_queries
    # ---------------------------------
    
    # === PASS 1: Keyword-based matching (fast, reliable for structured questions) ===
    keyword_match = _keyword_based_match(question, queries, has_entity)
    if keyword_match and keyword_match[1] >= threshold:
        print(f"[MATCH] Keyword-based match found: Q{keyword_match[0]['id']} (score: {keyword_match[1]:.2f})")
        return keyword_match
    
    # === PASS 2: Semantic matching (embeddings-based) ===
    embedder = get_embedder()
    
    # If no embedder, use sequence matching as fallback
    if not embedder:
        result = find_best_match_sequence(question, queries, threshold, has_entity=has_entity)
        if result:
            print(f"[MATCH] Sequence-based match found: Q{result[0]['id']} (score: {result[1]:.2f})")
        return result
    
    # Compute embeddings
    query_embeddings = _compute_query_embeddings(queries)
    if not query_embeddings:
        result = find_best_match_sequence(question, queries, threshold, has_entity=has_entity)
        if result:
            print(f"[MATCH] Sequence-based match (embeddings failed): Q{result[0]['id']} (score: {result[1]:.2f})")
        return result
    
    # Encode the question
    try:
        import torch
        question_embedding = embedder.encode(question, convert_to_tensor=True)
    except Exception as e:
        print(f"⚠️ Encoding failed: {e}")
        result = find_best_match_sequence(question, queries, threshold, has_entity=has_entity)
        if result:
            print(f"[MATCH] Sequence-based match (encoding failed): Q{result[0]['id']} (score: {result[1]:.2f})")
        return result
    
    # Find best semantic match
    best_query = None
    best_score = 0.0
    
    from torch.nn.functional import cosine_similarity

    for q in queries:
        qid = str(q["id"])
        if qid not in query_embeddings:
            continue
        
        query_embs = query_embeddings[qid]  # [N, dim] - όλες οι παραλλαγές
        
        # Βρες το MAX similarity από όλες τις παραλλαγές
        sims = cosine_similarity(
            question_embedding.unsqueeze(0).expand(query_embs.shape[0], -1),
            query_embs
        )
        similarity = sims.max().item()
        
        if has_entity:
            if "$name" in q.get("query", q.get("cypher", "")):
                similarity += 0.15
            else:
                similarity -= 0.15  # Penalty for global queries when entity is present
        
        if similarity > best_score:
            best_score = similarity
            best_query = q
    
    if best_query and best_score >= threshold:
        print(f"[MATCH] Semantic match found: Q{best_query['id']} (score: {best_score:.2f})")
        return (best_query, best_score)
    
    print(f"[MATCH] No semantic match above threshold {threshold}")
    return None

# =============================================================================
# KEYWORD-BASED MATCHING
# =============================================================================
def _keyword_based_match(
    question: str,
    queries: List[Dict],
    has_entity: bool = False
) -> Optional[Tuple[Dict, float]]:
    """
    Fast keyword-based matching for structured predefined queries.
    """
    question_lower = question.lower()
    question_words = set(w for w in question_lower.split() if len(w) > 3)
    
    best_query = None
    best_score = 0.0
    
    for q in queries:
        texts = _get_query_texts(q)
        current_best_q_score = 0.0
        
        for text in texts:
            text_lower = text.lower()
            text_words = set(w for w in text_lower.split() if len(w) > 3)
            
            if text_words:
                # Calculate Jaccard similarity (intersection / union)
                intersection = len(question_words & text_words)
                union = len(question_words | text_words)
                jaccard = intersection / union if union > 0 else 0
                
                if jaccard > current_best_q_score:
                    current_best_q_score = jaccard
        
        if has_entity and "$name" in q.get("query", q.get("cypher", "")):
            current_best_q_score += 0.1
        
        if current_best_q_score > best_score:
            best_score = current_best_q_score
            best_query = q
    
    if best_query and best_score >= 0.3:  # Lower threshold for keyword matching
        return (best_query, best_score)
    
    return None

# =============================================================================
# FALLBACK: SEQUENCE MATCHING
# =============================================================================
def find_best_match_sequence(
    question: str,
    queries: List[Dict],
    threshold: float,
    has_entity: bool = False
) -> Optional[Tuple[Dict, float]]:
    question_lower = question.lower()
    best_query = None
    best_score = 0.0

    for q in queries:
        texts = _get_query_texts(q)
        current_best_q_score = 0.0
        
        # PASS 1: Keyword matching (keywords = core words from predefined questions)
        # Extract keywords (words > 3 chars) from predefined texts
        keywords_per_text = []
        for text in texts:
            words = [w for w in text.lower().split() if len(w) > 3 and w.isalpha()]
            keywords_per_text.append(set(words))
        
        # Extract keywords from question
        question_words = set(w for w in question_lower.split() if len(w) > 3 and w.isalpha())
        
        # Check keyword overlap
        for keyword_set in keywords_per_text:
            if keyword_set:  # if predefined text has keywords
                q_stems = {w[:5] for w in question_words}
                overlap = len(q_stems & {w[:5] for w in keyword_set}) / len(keyword_set)
                if overlap > current_best_q_score:
                    current_best_q_score = overlap
        
        # PASS 2: Sequence matching (if keyword match not sufficient)
        if current_best_q_score < 0.5:  # only try sequence if keyword match weak
            for text in texts:
                score = SequenceMatcher(None, question_lower, text.lower()).ratio()
                if score > current_best_q_score:
                    current_best_q_score = score
        
        if has_entity and "$name" in q.get("query", q.get("cypher", "")):
            current_best_q_score += 0.15
            
        if current_best_q_score > best_score:
            best_score = current_best_q_score
            best_query = q

    if best_query and best_score >= threshold:
        return (best_query, best_score)
    return None
# =============================================================================
# SPECIAL QUERY DETECTION
# =============================================================================
def is_follow_up_question(question: str) -> bool:
    """
    Detect if question is a follow-up (asking for details about previous results).
    """
    follow_up_patterns = [
        r"^ποι[εέ][ςσ]",           # ποιες, ποιές
        r"^ποιο[ιί]",              # ποιοι, ποιοί
        r"^ονομαστικ[άα]",         # ονομαστικά
        r"^αναλυτικ[άα]",          # αναλυτικά
        r"^π[εέ]ς μου",            # πες μου
        r"^δ[εέ]ιξε",              # δείξε
        r"^ποι[αά] ε[ίι]ναι",      # ποια είναι
    ]
    
    question_lower = question.lower().strip()
    return any(re.match(pattern, question_lower) for pattern in follow_up_patterns)

def detect_output_type(question: str) -> str:
    """
    Detect desired output type from question.
    
    Returns: "graph", "chart", "report", or "text"
    """
    question_lower = question.lower()
    
    # Graph keywords
    if any(kw in question_lower for kw in ["γράφο", "γραφο", "graph", "δίκτυο", "network"]):
        return "graph"
    
    # Chart keywords
    if any(kw in question_lower for kw in ["διάγραμμα", "διαγραμμα", "chart", "γράφημα", "bar"]):
        return "chart"
    
    # Report keywords
    if any(kw in question_lower for kw in ["έκθεση", "εκθεση", "αναφορά", "αναφορα", "report", "docx"]):
        return "report"
    
    return "text"

def detect_normalized_query_type(question: str) -> Optional[str]:
    """
    Detect if asking for normalized/statistical analysis.
    
    Returns: "robust", "stdev", or None
    """
    question_lower = question.lower()
    
    if any(kw in question_lower for kw in ["robust", "ανθεκτική", "ανθεκτικη"]):
        return "robust"
    
    if any(kw in question_lower for kw in ["stdev", "std", "τυπική απόκλιση", "τυπικη αποκλιση"]):
        return "stdev"
    
    return None
