"""
Simple_Federated - Entity Resolver
====================================
Υπεύθυνο για τη σωστή ταυτοποίηση οντοτήτων (Entity Resolution & Linking).

Κεντρικό πρόβλημα: Η ίδια αναθέτουσα αρχή ή εταιρεία μπορεί να εμφανίζεται
με διαφορετικό όνομα στο TED και στο ΚΗΜΔΗΣ. Π.χ.:
  - KIMDIS: "ΔΗΜΟΣ ΑΘΗΝΑΙΩΝ"
  - TED:    "Municipality of Athens" ή "DIMOS ATHINAION"

Χρησιμοποιούμε πολλαπλά σήματα ταυτοποίησης:
  1. Exact Match (ΑΦΜ/VAT Number) — 100% σιγουριά
  2. Fuzzy String Match (ονόματα) — Score-based
  3. Composite Match (Αναθέτουσα + Ποσό + Ημερομηνία) — Για awards
"""

import re
import unicodedata
from typing import Optional, Tuple, List, Dict, Any


# =============================================================================
# TEXT NORMALIZATION
# =============================================================================

def normalize_text(text: str) -> str:
    """
    Κανονικοποίηση κειμένου για σύγκριση.
    - Αφαίρεση τόνων
    - Πεζά γράμματα
    - Αφαίρεση ειδικών χαρακτήρων
    - Κανονικοποίηση κενών
    """
    if not text:
        return ""

    # Lowercase
    text = text.lower().strip()

    # Αφαίρεση τόνων (decompose -> remove combining marks -> compose)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = unicodedata.normalize("NFC", text)

    # Αφαίρεση ειδικών χαρακτήρων (κράτα γράμματα, αριθμούς, κενά)
    text = re.sub(r"[^\w\s]", " ", text)

    # Κανονικοποίηση πολλαπλών κενών
    text = re.sub(r"\s+", " ", text).strip()

    return text


def normalize_greek_name(name: str) -> str:
    """
    Εξειδικευμένη κανονικοποίηση για ελληνικά ονόματα φορέων.
    Αφαιρεί κοινά prefixes/suffixes που δεν βοηθούν στο matching.
    """
    name = normalize_text(name)

    # Αφαίρεση κοινών prefixes
    prefixes_to_strip = [
        "ο ", "η ", "το ",
        "δημος ", "νομαρχια ", "περιφερεια ",
        "γενικο νοσοκομειο ", "πανεπιστημιακο γενικο νοσοκομειο ",
        "υπουργειο ",
    ]
    for prefix in prefixes_to_strip:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break

    return name.strip()


# =============================================================================
# SIMILARITY SCORING
# =============================================================================

def levenshtein_distance(s1: str, s2: str) -> int:
    """Υπολογισμός Levenshtein distance (edit distance)."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]


def similarity_score(name_a: str, name_b: str) -> float:
    """
    Υπολογίζει score ομοιότητας μεταξύ δύο ονομάτων (0.0 - 1.0).
    Χρησιμοποιεί normalized Levenshtein distance.
    """
    a = normalize_text(name_a)
    b = normalize_text(name_b)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    max_len = max(len(a), len(b))
    distance = levenshtein_distance(a, b)

    return 1.0 - (distance / max_len)


def token_overlap_score(name_a: str, name_b: str) -> float:
    """
    Υπολογίζει score βάσει κοινών tokens (Jaccard similarity).
    Πιο ανθεκτικό σε αναδιατάξεις λέξεων.
    """
    tokens_a = set(normalize_text(name_a).split())
    tokens_b = set(normalize_text(name_b).split())

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b

    return len(intersection) / len(union)


# =============================================================================
# ENTITY MATCHING (CORE)
# =============================================================================

# Confidence thresholds
EXACT_MATCH_THRESHOLD = 1.0    # VAT / identifier match
HIGH_CONFIDENCE = 0.90         # Auto-merge
MEDIUM_CONFIDENCE = 0.75       # Staging (Human review)
LOW_CONFIDENCE = 0.60          # Likely different, but flag

# Weights for composite matching
WEIGHTS = {
    "name":   0.50,   # Όνομα αναθέτουσας/εταιρείας
    "value":  0.25,   # Ποσό σύμβασης
    "date":   0.15,   # Ημερομηνία
    "cpv":    0.10,   # CPV κωδικός
}


class MatchResult:
    """Αποτέλεσμα ταυτοποίησης μεταξύ δύο οντοτήτων."""

    def __init__(self, score: float, match_type: str, details: str = ""):
        self.score = score
        self.match_type = match_type  # "exact", "high", "medium", "low", "no_match"
        self.details = details

    @property
    def is_match(self) -> bool:
        return self.score >= MEDIUM_CONFIDENCE

    @property
    def needs_review(self) -> bool:
        return MEDIUM_CONFIDENCE <= self.score < HIGH_CONFIDENCE

    @property
    def auto_merge(self) -> bool:
        return self.score >= HIGH_CONFIDENCE

    def __repr__(self):
        return f"MatchResult(score={self.score:.3f}, type='{self.match_type}', details='{self.details}')"


def match_by_vat(vat_a: str, vat_b: str) -> Optional[MatchResult]:
    """
    Ταυτοποίηση μέσω ΑΦΜ/VAT Number. Αν ταιριάζουν → 100%.
    """
    if not vat_a or not vat_b:
        return None

    # Κανονικοποίηση: αφαίρεση "EL", "GR", κενών κ.λπ.
    clean_a = re.sub(r"[^0-9]", "", str(vat_a))
    clean_b = re.sub(r"[^0-9]", "", str(vat_b))

    if len(clean_a) < 5 or len(clean_b) < 5:
        return None

    if clean_a == clean_b:
        return MatchResult(
            score=EXACT_MATCH_THRESHOLD,
            match_type="exact",
            details=f"VAT match: {clean_a}"
        )

    return MatchResult(score=0.0, match_type="no_match", details="VAT mismatch")


def match_buyers(
    buyer_a: Dict[str, Any],
    buyer_b: Dict[str, Any],
) -> MatchResult:
    """
    Ταυτοποίηση αναθετουσών αρχών (Buyers).

    Χρησιμοποιεί:
      1. VAT match (αν υπάρχει) → instant 100%
      2. Name similarity (Levenshtein + Token overlap) → weighted score
      3. NUTS code match → bonus

    Args:
        buyer_a: {"name": "...", "vat": "...", "nuts_code": "..."}
        buyer_b: {"name": "...", "vat": "...", "nuts_code": "..."}
    """
    # 1. VAT match (instant resolution)
    vat_result = match_by_vat(
        buyer_a.get("vat") or buyer_a.get("vat_number"),
        buyer_b.get("vat") or buyer_b.get("vat_number"),
    )
    if vat_result and vat_result.score == EXACT_MATCH_THRESHOLD:
        return vat_result

    # 2. Name matching (combined score)
    name_a = buyer_a.get("name", "")
    name_b = buyer_b.get("name", "")

    lev_score = similarity_score(name_a, name_b)
    tok_score = token_overlap_score(name_a, name_b)

    # Weighted: Levenshtein 60%, Token overlap 40%
    name_score = (lev_score * 0.6) + (tok_score * 0.4)

    # 3. NUTS bonus (αν ίδια περιοχή, αυξάνεται η εμπιστοσύνη)
    nuts_a = buyer_a.get("nuts_code", "")
    nuts_b = buyer_b.get("nuts_code", "")
    nuts_bonus = 0.0
    if nuts_a and nuts_b:
        if nuts_a == nuts_b:
            nuts_bonus = 0.05  # Ίδια ακριβώς περιοχή
        elif nuts_a[:3] == nuts_b[:3]:
            nuts_bonus = 0.02  # Ίδια ευρύτερη περιοχή

    final_score = min(name_score + nuts_bonus, 1.0)

    # Determine match type
    if final_score >= HIGH_CONFIDENCE:
        match_type = "high"
    elif final_score >= MEDIUM_CONFIDENCE:
        match_type = "medium"
    elif final_score >= LOW_CONFIDENCE:
        match_type = "low"
    else:
        match_type = "no_match"

    return MatchResult(
        score=final_score,
        match_type=match_type,
        details=f"name_lev={lev_score:.3f}, name_tok={tok_score:.3f}, nuts_bonus={nuts_bonus:.3f}"
    )


def match_awards(
    award_a: Dict[str, Any],
    award_b: Dict[str, Any],
    buyer_match: Optional[MatchResult] = None,
) -> MatchResult:
    """
    Ταυτοποίηση συμβάσεων (Awards) μεταξύ TED και ΚΗΜΔΗΣ.

    Χρησιμοποιεί composite matching:
      - Buyer name similarity (50%)
      - Value proximity (25%)
      - Year match (15%)
      - CPV match (10%)

    Args:
        award_a: {"buyer_name": "...", "value": 1234, "year": 2024, "cpv_code": "..."}
        award_b: {"buyer_name": "...", "value": 1234, "year": 2024, "cpv_code": "..."}
        buyer_match: Αν έχει ήδη γίνει ταυτοποίηση του buyer, χρησιμοποιείται
    """
    total_score = 0.0

    # 1. Buyer name similarity (50%)
    if buyer_match:
        buyer_score = buyer_match.score
    else:
        buyer_score = similarity_score(
            award_a.get("buyer_name", ""),
            award_b.get("buyer_name", "")
        )
    total_score += buyer_score * WEIGHTS["name"]

    # 2. Value proximity (25%)
    val_a = float(award_a.get("value", 0) or 0)
    val_b = float(award_b.get("value", 0) or 0)
    if val_a > 0 and val_b > 0:
        # Σχετική διαφορά: αν < 5% → πλήρες score
        max_val = max(val_a, val_b)
        diff_pct = abs(val_a - val_b) / max_val
        if diff_pct <= 0.05:
            value_score = 1.0
        elif diff_pct <= 0.15:
            value_score = 0.7
        elif diff_pct <= 0.30:
            value_score = 0.3
        else:
            value_score = 0.0
        total_score += value_score * WEIGHTS["value"]

    # 3. Year match (15%)
    year_a = award_a.get("year")
    year_b = award_b.get("year")
    if year_a and year_b:
        if int(year_a) == int(year_b):
            total_score += 1.0 * WEIGHTS["date"]
        elif abs(int(year_a) - int(year_b)) == 1:
            total_score += 0.5 * WEIGHTS["date"]  # ±1 χρόνο (καθυστερημένη δημοσίευση)

    # 4. CPV match (10%)
    cpv_a = str(award_a.get("cpv_code", ""))[:5]
    cpv_b = str(award_b.get("cpv_code", ""))[:5]
    if cpv_a and cpv_b and cpv_a == cpv_b:
        total_score += 1.0 * WEIGHTS["cpv"]

    # Determine match type
    if total_score >= HIGH_CONFIDENCE:
        match_type = "high"
    elif total_score >= MEDIUM_CONFIDENCE:
        match_type = "medium"
    elif total_score >= LOW_CONFIDENCE:
        match_type = "low"
    else:
        match_type = "no_match"

    return MatchResult(
        score=total_score,
        match_type=match_type,
        details=(
            f"buyer={buyer_score:.3f}, "
            f"value=({val_a:.0f} vs {val_b:.0f}), "
            f"year=({year_a} vs {year_b}), "
            f"cpv=({cpv_a} vs {cpv_b})"
        )
    )


# =============================================================================
# BATCH ENTITY RESOLUTION
# =============================================================================

def find_best_match(
    entity: Dict[str, Any],
    candidates: List[Dict[str, Any]],
    entity_type: str = "buyer",
) -> Optional[Tuple[int, MatchResult]]:
    """
    Βρίσκει τον καλύτερο ταίριασμα για μια οντότητα μέσα σε λίστα υποψηφίων.

    Args:
        entity: Η οντότητα προς ταυτοποίηση
        candidates: Λίστα υποψήφιων ταιριασμάτων
        entity_type: "buyer" ή "winner"

    Returns:
        (index, MatchResult) ή None αν δεν βρεθεί αρκετά καλό match
    """
    best_idx = None
    best_result = None

    for idx, candidate in enumerate(candidates):
        if entity_type == "buyer":
            result = match_buyers(entity, candidate)
        else:
            # Για winners (εταιρείες), χρησιμοποιούμε το ίδιο matching
            result = match_buyers(entity, candidate)

        if best_result is None or result.score > best_result.score:
            best_idx = idx
            best_result = result

    if best_result and best_result.score >= LOW_CONFIDENCE:
        return (best_idx, best_result)

    return None
