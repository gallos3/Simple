"""
Simple - Entity Extractor (IMPROVED)

Βελτιώσεις:
1. Disambiguation όταν υπάρχουν πολλά matches
2. Composite matching (π.χ. "Ιπποκράτειο Θεσσαλονίκης" → ψάχνει ΚΑΙ τα δύο)
3. Επιστρέφει το canonical name από τη βάση
4. Καλύτερο scoring με βάρη στις λέξεις-κλειδιά
"""

import os
import sys
import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import difflib

# Fix Windows console encoding for Greek + emoji output
if sys.stdout.encoding and sys.stdout.encoding.lower() in ('cp1253', 'cp1252', 'mbcs'):
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
# =============================================================================
# CONSTANTS
# =============================================================================
GREEK_STOP_WORDS = {
    # Ρήματα / εντολές
    'δωσε', 'δώσε', 'ελεγξε', 'ελέγξε', 'βρες', 'εμφανισε', 'εμφάνισε',
    # Άρθρα / προθέσεις / αριθμητικά
    'για', 'με', 'μη', 'τις', 'τον', 'την', 'του', 'των', 'στον', 'στην',
    'στο', 'απο', 'από', 'και', 'στα', 'τα', 'οι', 'τους', 'να', 'σε',
    'ενα', 'ένα', 'ενας', 'ένας', 'μια', 'μία',
    # Λέξεις domain που δεν είναι μέρος ονόματος αρχής
    'εκθεση', 'έκθεση', 'ελεγχου', 'ελέγχου', 'νομιμες', 'νόμιμες', 'νομιμη', 'νόμιμη', 'νομιμο', 'νόμιμο',
    'απευθειας', 'απευθείας', 'αναθεσεις', 'αναθέσεις', 'αναθεση', 'ανάθεση',
    'συμβαση', 'συμβάσεις', 'συμβάσεων', 'συμβασεις', 'συμβαση', 'σύμβαση',
    'παρανομες', 'παράνομες', 'μη', 'υπερβαση', 'υπέρβαση',
    'κατατμηση', 'κατάτμηση', 'πιθανη', 'πιθανή', 'υπαρχει', 'υπάρχει', 'ετος', 'έτος',
    'γραφο', 'γράφου', 'γραφου', 'γραφημα', 'γράφημα', 'δικτυο', 'δίκτυο',
    'προμηθεια', 'προμήθεια', 'προμηθειες', 'προμήθειες', 'χαρτιου', 'χαρτιού', 'χαρτι', 'χάρτι',
    'ποσο', 'ποσό', 'ποσα', 'ποσά', 'ευρω', 'ευρώ', 'οριο', 'όριο', 'ορια', 'όρια',
    'επιτρεπεται', 'επιτρέπεται', 'νομιμοτητα', 'νομιμότητα', 'παρανομια', 'παρανομία'
}
def normalize_token(token: str) -> str:
    # Αφαίρεση τόνων + κεφαλαία
    return unicodedata.normalize('NFD', token)\
        .encode('ascii', 'ignore')\
        .decode('utf-8')\
        .upper()\
        .strip()
# =============================================================================
# PATHS
# =============================================================================
ENTITY_CACHE_PATH = Path(__file__).parent / "entity_cache.json"

# =============================================================================
# NORMALIZATION
# =============================================================================
def normalize_greek(s: str) -> str:
    """Normalize Greek-ish text for matching (casefold, strip diacritics, and fix common Latin lookalikes)."""
    if not s:
        return ""
    s = str(s).lower()
    # Fix common Latin lookalikes that appear in Greek datasets (e.g., ΙΠΠΟΚΡΑΤΕΙO with Latin 'O')
    confusables = str.maketrans({
        'a': 'α', 'b': 'β', 'e': 'ε', 'h': 'η', 'i': 'ι', 'k': 'κ', 'm': 'μ', 'n': 'ν',
        'o': 'ο', 'p': 'ρ', 't': 'τ', 'u': 'υ', 'x': 'χ', 'y': 'γ', 'v': 'ν',
        'A': 'α', 'B': 'β', 'E': 'ε', 'H': 'η', 'I': 'ι', 'K': 'κ', 'M': 'μ', 'N': 'ν',
        'O': 'ο', 'P': 'ρ', 'T': 'τ', 'U': 'υ', 'X': 'χ', 'Y': 'γ', 'V': 'ν',
    })
    s = s.translate(confusables)
    # Remove Greek diacritics
    s = re.sub(r"[άά]", "α", s)
    s = re.sub(r"[έέ]", "ε", s)
    s = re.sub(r"[ήή]", "η", s)
    s = re.sub(r"[ίϊΐί]", "ι", s)
    s = re.sub(r"[όό]", "ο", s)
    s = re.sub(r"[ύϋΰύ]", "υ", s)
    s = re.sub(r"[ώώ]", "ω", s)
    # Keep only Greek letters, digits and spaces
    s = re.sub(r"[^α-ω0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def tokenize(text: str) -> List[str]:
    """Σπάει το κείμενο σε tokens."""
    # Αφαίρεσε ειδικούς χαρακτήρες
    text = re.sub(r"['\"\-\(\)\[\]\.,:;!?]", " ", text)
    tokens = text.split()
    # Φιλτράρισμα πολύ μικρών tokens
    return [t for t in tokens if len(t) >= 2]

def normalize_location_token(tok: str) -> str:
    """Normalizes Greek location tokens (e.g., genitive → nominative) for matching."""
    t = normalize_greek(tok)

    mappings = {
        "αθηνας": "αθηνα",
        "αθηναιων": "αθηνα",
        "θεσσαλονικης": "θεσσαλονικη",
        "πειραιως": "πειραια",
        "πατρας": "πατρα",
        "πατρεων": "πατρα",
        "λαρισας": "λαρισα",
        "λαρισαιων": "λαρισα",
        "ηρακλειου": "ηρακλειο",
        "ιωαννινων": "ιωαννινα",
        "καβαλας": "καβαλα",
        "σερρων": "σερρες",
        "σερραιων": "σερρες",
        "βολου": "βολος",
        "τρικαλων": "τρικαλα",
        "τρικκαιων": "τρικαλα",
        "χανιων": "χανια",
        "ροδου": "ροδος",
        "ροδιων": "ροδος",
    }
    if t in mappings:
        return mappings[t]

    # Heuristic fallbacks (best-effort)
    if t.endswith("ης") and len(t) > 3:
        return t[:-1]
    if t.endswith("ας") and len(t) > 3:
        return t[:-1]
    if t.endswith("ου") and len(t) > 3:
        return t[:-2] + "ο"
    if t.endswith("ων") and len(t) > 3:
        return t[:-2] + "α"

    return t



# =============================================================================
# ENTITY CACHE LOADING
# =============================================================================
_entity_cache = None
_entity_index = None  # Token -> List of Indices
_normalized_cache = [] # List of (original_name, tokens_set)

def load_entity_cache() -> Dict[str, List[str]]:
    """Φορτώνει το entity cache και χτίζει ευρετήριο."""
    global _entity_cache, _entity_index, _normalized_cache
    if _entity_cache is not None:
        return _entity_cache
    
    try:
        with open(ENTITY_CACHE_PATH, 'r', encoding='utf-8') as f:
            _entity_cache = json.load(f)
        
        authorities = _entity_cache.get("Buyer.name", [])
        
        # Try loading from pickle cache first
        pickle_path = ENTITY_CACHE_PATH.with_suffix(".index.pkl")
        if os.path.exists(pickle_path) and os.path.getmtime(pickle_path) > os.path.getmtime(ENTITY_CACHE_PATH):
            import pickle
            with open(pickle_path, 'rb') as f:
                _entity_index, _normalized_cache = pickle.load(f)
            print(f"[CACHE] Loaded entity index from pickle cache")
            return _entity_cache

        print(f"[CACHE] Building index for {len(authorities)} authorities... (this may take a few seconds)")
        
        # Build inverted index for speed
        _entity_index = {}
        _normalized_cache = []
        for i, name in enumerate(authorities):
            norm = normalize_greek(name)
            raw_tokens = tokenize(norm)
            tokens = set()
            for t in raw_tokens:
                tokens.add(t)
                loc_t = normalize_location_token(t)
                if loc_t: tokens.add(loc_t)
            
            _normalized_cache.append((name, tokens, raw_tokens))
            for t in tokens:
                if t not in _entity_index:
                    _entity_index[t] = []
                _entity_index[t].append(i)
        
        # Save to pickle for next time
        try:
            import pickle
            with open(pickle_path, 'wb') as f:
                pickle.dump((_entity_index, _normalized_cache), f)
        except: pass
                
    except Exception as e:
        print(f"[WARN] Could not load entity cache: {e}")
        _entity_cache = {"Buyer.name": []}
        _entity_index = {}
        _normalized_cache = []
    
    return _entity_cache


# =============================================================================
# STOPWORDS - λέξεις που αγνοούμε στο matching
# =============================================================================
STOPWORDS = {normalize_greek(w) for w in {
    "το", "τα", "η", "ο", "οι", "του", "της", "των", "τις", "τον", "την",
    "στο", "στη", "μου", "σου", "μας", "σας", "τους","στα", "στις", "στους", "στον", "στην",
    "για", "μη", "με", "σε", "και", "ή", "αλλά", "όμως",
    "πόσες", "ποσες", "πόσα", "ποσα", "πόσοι", "ποσοι",
    "είχε", "ειχε", "έχει", "δώσε", "εχει", "έκανε", "εκανε",
    "αναθέσεις", "αναθεσεις", "συμβάσεις", "συμβασεις",
    "απευθείας", "απευθειας", "νομιμες", "στο",
    "αναθέτουσες", "αναθετουσες", "αναθέτουσα", "αναθετουσα",
    "έκθεση", "ελεγχου", "ελεγξε", "γραφο", "γραφου", "γραφημα", "γράφημα",
    "αρχές", "αρχες", "αρχή", "αρχη",
    "φορείς", "φορεις", "φορέας", "φορεας",
    "υπηρεσίες", "υπηρεσιες", "υπηρεσία", "υπηρεσια",
    "εταιρίες", "εταιριες", "εταιρείες", "εταιρειες",
    "εταιρεία", "εταιρεια", "εταιρείας", "εταιρειας", "εταιρείο", "εταιρειο",
    "ανάδοχος", "αναδοχος", "αναδόχου", "αναδοχου", "ανάδοχοι", "αναδοχοι",
    "πλήθος", "πληθος", "περισσότερες", "περισσοτερες", "αριθμό", "αριθμο", "αριθμός", "αριθμος",
    "δημόσιους", "δημοσιους", "δημόσιες", "δημοσιες",
    "έχω", "εχω", "ποιες", "ποια", "ποιοι", "πόσους", "ποσους",
    "ενα", "ενας", "μια", "ενα", "ενας", "ενα", "ένα", "ένας", "μια", "μία",
    "διαγνωση", "διάγνωση", "πορισμα", "πόρισμα", "θεραπεία", "θεραπεια", "δώσε", "δωσε", "ωσε",
    "νομιμη", "νόμιμη", "νομιμο", "νόμιμο", "νομιμοτητα", "νομιμότητα", "επιτρεπεται", "επιτρέπεται",
    "προμηθεια", "προμήθεια", "προμηθειες", "προμήθειες", "χαρτιου", "χαρτιού", "χαρτι", "χάρτι",
    "αναθεση", "ανάθεση", "αναθέσεις", "αναθεσεις",
    "συμβάσεων", "συμβασεων", "έτος", "ετος", "υπάρχει", "υπαρχει", "πιθανή", "πιθανη", "κατάτμηση", "κατατμηση", "υπέρβαση", "υπερβαση",
    "ποσο", "ποσό", "ευρω", "ευρώ", "οριο", "όριο", "ορια", "όρια", "νομο", "νομος"
}}
# =============================================================================
# MAIN EXTRACTION FUNCTION
# =============================================================================
def extract_entity_tokens(query: str) -> list:
    tokens = [normalize_token(t) for t in query.split()]
    # Φίλτρο: > 3 chars, όχι stop word (σύγκριση σε normalized μορφή)
    stop_normalized = {normalize_token(w) for w in GREEK_STOP_WORDS}
    return [t for t in tokens if len(t) > 3 and t not in stop_normalized]
def extract_cpv_from_question(question: str) -> Optional[str]:
    """Detect CPV codes in a natural‑language question.

    Supported patterns:
    - "CPV 33100" or "cpv33100"
    - plain 5–8 digit numbers (e.g. "33100")
    - known Greek domain phrases (e.g. "ιατρικές συσκευές" → "33100")
    Returns the CPV code as a string or ``None`` if no match is found.
    """
    # Normalise the question (strip accents, lower‑case)
    q = normalize_greek(question).lower()

    # 1. Explicit "cpv <digits>" pattern
    m = re.search(r"\\bcpv\\s*(\\d{5,8})\\b", q)
    if m:
        return m.group(1)

    # 2. Stand‑alone numeric CPV (5‑8 digits)
    m = re.search(r"\\b(\\d{5,8})\\b", q)
    if m:
        return m.group(1)

    # 3. Simple keyword‑to‑code mappings (extendable)
    known_mappings = {
        "ιατρικές συσκευές": "33100",
        "medical devices": "33100",
    }
    for phrase, code in known_mappings.items():
        if phrase in q:
            return code
    return None    
    print(f"[SEARCH] Searching for entity in: '{question}'")
    print(f"   Tokens: {q_tokens}")
    
    # Βρες matches
    matches = []
    
    for auth_name in authorities:
        auth_normalized = normalize_greek(auth_name)
        auth_tokens = tokenize(auth_normalized)
        
        # Μέτρησε πόσα tokens της ερώτησης υπάρχουν στο authority name
        matched_tokens = []
        for qt in q_tokens:
            # Έλεγχος αν το token υπάρχει σε κάποιο token του authority
            for at in auth_tokens:
                if len(qt) > 3 and (qt == at or at == qt): # Exact match for short, or mutual inclusion for long
                    matched_tokens.append(qt)
                    break
                elif qt == at: # Exact match
                    matched_tokens.append(qt)
                    break
        
        if matched_tokens:
            # Score = αριθμός matched tokens / συνολικά tokens ερώτησης
            # + bonus αν ταιριάζουν πολλά tokens
            score = len(matched_tokens) / len(q_tokens)
            
            # Bonus για πιο συγκεκριμένα matches (πολλά tokens)
            if len(matched_tokens) >= 2:
                score += 0.2
            if len(matched_tokens) >= 3:
                score += 0.2
            
            # Penalty αν το authority name είναι πολύ γενικό
            if len(auth_tokens) <= 2:
                score -= 0.1
            
            matches.append({
                "name": auth_name,
                "score": score,
                "matched_tokens": matched_tokens
            })
    
    if not matches:
        print("   ❌ No matches found")
        return None
    
    # Ταξινόμηση κατά score (descending)
    matches.sort(key=lambda x: x["score"], reverse=True)
    
    # Πάρε τα top matches
    best = matches[0]
    
    print(f"   [OK] Best match (score {best['score']:.1f}): '{best['name']}'")
    print(f"      Matched tokens: {best['matched_tokens']}")
    
    # Έλεγχος για disambiguation
    # Αν υπάρχουν πολλά matches με παρόμοιο score, ζήτα διευκρίνιση
    similar_matches = [m for m in matches[:5] if m["score"] >= best["score"] - 0.2]
    
    if len(similar_matches) > 1:
        # Έλεγχος αν πρόκειται για διαφορετικές οντότητες ή απλά παραλλαγές
        unique_entities = set()
        for m in similar_matches:
            # Απλοποίηση για σύγκριση
            simplified = normalize_greek(m["name"])
            # Αφαίρεσε κοινά prefixes
            simplified = re.sub(r"^(περ\.?γεν\.?|γενικ[οό]|νομ\.?γεν\.?)\s*", "", simplified)
            simplified = re.sub(r"\s*(νοσοκομει[οό]|δημος|περιφερεια)\s*", " ", simplified)
            unique_entities.add(simplified.strip())
        
        # Αν υπάρχουν πραγματικά διαφορετικές οντότητες
        if len(similar_matches) > 1 and best["score"] < 1.5:
            alternatives = [m["name"] for m in similar_matches[:3]]
            print(f"   [WARN] Multiple similar matches: {alternatives}")
            
            return {
                "label": "Buyer",
                "property": "name",
                "value": best["name"],
                "score": best["score"],
                "ambiguous": True,
                "alternatives": alternatives
            }
    
    return {
        "label": "Buyer",
        "property": "name",
        "value": best["name"],
        "score": best["score"],
        "ambiguous": False,
        "alternatives": []
    }


# =============================================================================
# COMPOSITE MATCHING - για "Ιπποκράτειο Θεσσαλονίκης"
# =============================================================================
def extract_entity_composite(
    question: str,
    entity_cache: Dict[str, List[str]]
) -> Optional[Dict]:
    """
    Βελτιωμένη εξαγωγή που χειρίζεται composite ονόματα.
    
    Π.χ. "Ιπποκράτειο Θεσσαλονίκης" → ψάχνει entities που περιέχουν ΚΑΙ τα δύο
    """
    authorities = entity_cache.get("Buyer.name", [])
    if not authorities:
        return None
    
    q_normalized = normalize_greek(question)
    q_tokens = tokenize(q_normalized)
    q_tokens = [t for t in q_tokens if t not in STOPWORDS and normalize_greek(t) not in STOPWORDS and not t.isdigit()]
    
    if not q_tokens:
        return None
    
    # Normalize Greek noun suffixes (genitive/accusative → nominative)
    # "δημου" → "δημος", "θεσσαλονικης" → "θεσσαλονικη", etc.
    def _stem_greek(token):
        """Crude Greek stemmer: genitive/accusative → nominative."""
        stems = [token]
        if token.endswith("ου"):
            stems.append(token[:-2] + "ος")  # δημου → δημος
            stems.append(token[:-2] + "ο")   # ιπποκρατειου → ιπποκρατειο
        elif token.endswith("ης"):
            stems.append(token[:-2] + "η")   # θεσσαλονικης → θεσσαλονικη
        elif token.endswith("ων"):
            stems.append(token[:-2] + "ες")  # αθηνων → αθηνες
            stems.append(token[:-2] + "α")   # ιωαννινων → ιωαννινα
        elif token.endswith("ας"):
            stems.append(token[:-2] + "α")   # λαρισας → λαρισα
        elif token.endswith("ιου"):
            stems.append(token[:-3] + "ιο")  # υπουργειου → υπουργειο
        return stems
    
    print(f"[COMPOSITE] Searching: '{question}'")
    print(f"   Tokens: {q_tokens}")
    
    # Priority keywords - αυτά έχουν μεγαλύτερο βάρος
    priority_keywords = {
        "ιπποκρατειο": 3.0,
        "ιπποκρατειου": 3.0,
        "ευαγγελισμος": 3.0,
        "παπαγεωργιου": 3.0,
        "αχεπα": 3.0,
        "θεαγενειο": 3.0,
        "αλεξανδρα": 2.0,
        "λαικο": 2.0,
        "σωτηρια": 2.0,
        "αριστοτελειο": 4.0,
        "αριστοτελειου": 4.0,
        "πανεπιστημιο": 2.0,
        "δημος": 2.0,
        "νοσοκομειο": 2.0,
    }
    
    # Location keywords - δευτερεύον βάρος
    location_keywords = {
        "αθηνα", "θεσσαλονικη", "πειραια", "πατρα", "λαρισα", "ηρακλειο",
        "ιωαννινα", "καβαλα", "σερρες", "βολος",
    }

    
    # 1. Βρες υποψήφια indices μέσω του index
    candidate_indices = set()
    
    # Διαχώρισε tokens σε κοινά και σπάνια
    common_tokens = {"δημος", "νοσοκομειο", "υπουργειο", "περιφερεια", "πανεπιστημιο", "εταιρεια"}
    
    q_tokens_normalized = []
    for qt in q_tokens:
        q_norm = normalize_greek(qt)
        q_loc = normalize_location_token(qt)
        # Generate all stem variants for this token
        stems = _stem_greek(q_norm)
        if q_loc != q_norm:
            stems.extend(_stem_greek(q_loc))
        q_tokens_normalized.append((q_norm, q_loc, list(set(stems))))

    specific_hits = set()
    for q_norm, q_loc, stems in q_tokens_normalized:
        if q_norm not in common_tokens and q_loc not in common_tokens:
            for s in stems:
                if s in _entity_index: specific_hits.update(_entity_index[s])
    
    if specific_hits:
        # Αν βρήκαμε σπάνια tokens, ψάχνουμε ΜΟΝΟ σε αυτά (δραστική μείωση χρόνου)
        candidate_indices = specific_hits
    else:
        # Αλλιώς ψάχνουμε στα πάντα
        for q_norm, q_loc, stems in q_tokens_normalized:
            for s in stems:
                if s in _entity_index: candidate_indices.update(_entity_index[s])
    
    if not candidate_indices:
        # Fallback: Fuzzy match in index keys for long words (typos)
        index_keys = list(_entity_index.keys())
        for q_norm, q_loc, stems in q_tokens_normalized:
            for s in stems:
                if len(s) >= 5:
                    close_keys = difflib.get_close_matches(s, index_keys, n=1, cutoff=0.8)
                    if close_keys:
                        candidate_indices.update(_entity_index[close_keys[0]])
        
        if not candidate_indices:
            return None

    matches = []
    for idx in candidate_indices:
        auth_name, auth_tokens_set, auth_tokens_list = _normalized_cache[idx]
        
        total_score = 0
        matched_priority = []
        matched_location = []
        matched_other = []

        for q_norm, q_loc, stems in q_tokens_normalized:

            # Token-level match (including stemmed variants)
            token_hit = (q_norm in auth_tokens_set) or (q_loc in auth_tokens_set)
            if not token_hit:
                token_hit = any(s in auth_tokens_set for s in stems)
            
            if not token_hit:
                # Substring match (πιο αργό, μόνο αν q_norm > 3 χαρακτήρες)
                if len(q_norm) > 3:
                    token_hit = any(q_norm in at for at in auth_tokens_set)
                    if not token_hit:
                        token_hit = any(s in at for s in stems for at in auth_tokens_set if len(s) > 3)
            
            # Fuzzy match (για τυπογραφικά) - μόνο αν το q_norm είναι μεγάλο (αποφυγή false positives)
            if not token_hit and len(q_norm) >= 5:
                # Χρησιμοποιούμε difflib για να βρούμε λέξεις που μοιάζουν με cutoff 0.8
                close_tokens = difflib.get_close_matches(q_norm, auth_tokens_list, n=1, cutoff=0.8)
                if close_tokens:
                    token_hit = True
                    q_norm = close_tokens[0]  # Χρησιμοποιούμε τη λέξη που ταιριάξαμε για το υπόλοιπο loop (π.χ. location match)
            
            if not token_hit:
                continue

            # Check priority/location against stems too
            priority_match = q_norm in priority_keywords or any(s in priority_keywords for s in stems)
            location_match = q_loc in location_keywords or q_norm in location_keywords or any(s in location_keywords for s in stems)
            
            if priority_match:
                score_key = q_norm if q_norm in priority_keywords else next((s for s in stems if s in priority_keywords), q_norm)
                total_score += priority_keywords.get(score_key, 2.0)
                matched_priority.append(q_norm)
            elif location_match:
                total_score += 1.5
                matched_location.append(q_norm)
            else:
                total_score += 1.0
                matched_other.append(q_norm)
        
        if total_score > 0:
            auth_normalized = normalize_greek(auth_name)
            # Bonus αν έχουμε ΚΑΙ priority ΚΑΙ location
            if matched_priority and matched_location:
                total_score *= 1.5  # 50% bonus
            
            # Bonus για Κύριους Φορείς (Μόνο αν ταιριάζει και το όνομα, όχι μόνο το είδος)
            is_main_entity = any(k in auth_normalized for k in ["πανεπιστημιο", "δημος", "νοσοκομειο", "περιφερεια"])
            is_subsidiary = any(k in auth_normalized for k in [" αε", "εταιρεια", "συλλογος", "επιτροπη", "λογαριασμος"])
            if is_main_entity and not is_subsidiary and (len(matched_priority) > 0 or len(matched_other) > 0):
                total_score += 1.0
            
            # Bonus αν ο αριθμός matched tokens καλύπτει >50% του authority name
            coverage = len(matched_priority) + len(matched_location) + len(matched_other)
            auth_len = len(auth_tokens_list)
            if auth_len <= 3 and coverage >= auth_len:
                total_score += 1.0  # bonus για σύντομα, ακριβή ονόματα
            
            matches.append({
                "name": auth_name,
                "score": total_score,
                "matched_priority": matched_priority,
                "matched_location": matched_location,
                "matched_other": matched_other
            })
    
    if not matches:
        print("   ❌ No matches found")
        return None
    
    # Ταξινόμηση
    matches.sort(key=lambda x: x["score"], reverse=True)
    best = matches[0]
    
    print(f"   ✅ Best match (score {best['score']:.1f}): '{best['name']}'")
    
    # Disambiguation check
    alternatives = []
    if len(matches) > 1:
        # Αυστηρότερο threshold (90%)
        similar_matches = [m for m in matches if m["score"] >= best["score"] * 0.90]
        if len(similar_matches) > 1:
            alternatives = [m["name"] for m in similar_matches[:5]]
            print(f"   [COMPOSITE] Multiple matches: {alternatives}")
    
    return {
        "label": "Buyer",
        "property": "name",
        "value": best["name"],
        "score": best["score"],
        "ambiguous": len(alternatives) > 1,
        "alternatives": alternatives
    }


# =============================================================================
# YEAR EXTRACTION
# =============================================================================
def _normalize_spoken_year_digits(text: str) -> str:
    """
    Ενώνει ψηφία που το STT συχνά χωρίζει: «20 24» → «2024», «20  2 4» → «2024».
    """
    if not text:
        return ""
    t = text
    # 20 + διαχωριστικά + ακριβώς 2 ψηφία (όχι 3η ψηφία — αποφεύγει CPV κλπ)
    t = re.sub(r"20[\s./\-_]+(\d)\s*(\d)(?!\d)", r"20\1\2", t)
    return t


def _voice_misheard_twenties_greek(normalized_lower: str) -> str:
    """
    STT συχνά ακούει «είκοσι» ως «δέκα» σε «δύο χιλιάδες είκοσι τέσσερα» → μεταγραφή σαν 2014.
    Εφαρμόζεται μόνο για είσοδο από μικρόφωνο (from_voice).
    """
    if "δυο χιλιαδες δεκατεσσερα" in normalized_lower:
        return "2024"
    if "δυο χιλιαδες δεκατρισ" in normalized_lower or "δυο χιλιαδες δεκατρια" in normalized_lower:
        return "2023"
    if "δυο χιλιαδες δεκαδυο" in normalized_lower or "δυο χιλιαδες δωδεκα" in normalized_lower:
        return "2022"
    if "δυο χιλιαδες δεκαεννια" in normalized_lower:
        return "2029"
    return ""


def _apply_voice_stt_decade_fix(year: str) -> str:
    """
    Όταν το STT γράφει 2013/2014 αλλά ο χρήστης είπε 2023/2024 (σύγχυση δεκάδας).
    Δεν αγγίζουμε 2018/2019 — συχνά είναι πραγματικά έτη ελέγχου.
    """
    fix = {
        # STT systematically mishears the 2020s as 2010s.
        # In a procurement system used in 2026, nobody queries 2010-era data via voice.
        "2010": "2020",
        "2011": "2021",
        "2012": "2022",
        "2013": "2023",
        "2014": "2024",
        "2015": "2025",
        "2016": "2026",
        "2017": "2027",
    }
    return fix.get(year, year)


def _greek_verbal_year(normalized_lower: str) -> str:
    """
    Συχνές εκφράσεις για έτη 2020–2029 (μετά normalize_greek).
    """
    verbal = [
        ("δυο χιλιαδες εικοσι", "2020"),
        ("δυο χιλιαδες εικοσι ενα", "2021"),
        ("δυο χιλιαδες εικοσι δυο", "2022"),
        ("δυο χιλιαδες εικοσι τρια", "2023"),
        ("δυο χιλιαδες εικοσι τεσσερα", "2024"),
        ("δυο χιλιαδες εικοσι πεντε", "2025"),
        ("δυο χιλιαδες εικοσι εξι", "2026"),
        ("δυο χιλιαδες εικοσι επτα", "2027"),
        ("δυο χιλιαδες εικοσι οκτω", "2028"),
        ("δυο χιλιαδες εικοσι εννια", "2029"),
        ("δισχιλια εικοσι τεσσερα", "2024"),
        ("δισχιλια εικοσι πεντε", "2025"),
    ]
    for phrase, yr in verbal:
        if phrase in normalized_lower:
            return yr
    return ""


def extract_year_from_question(question: str, from_voice: bool = False) -> str:
    """Εξάγει το έτος από την ερώτηση (αντέχει STT: κενά ανάμεσα σε ψηφία, πολλαπλά έτη)."""
    if not question or not str(question).strip():
        return ""

    raw = str(question).strip()
    q = _normalize_spoken_year_digits(raw)

    # Keywords για φέτος/πέρσι (πριν τα ψηφία — «φέτος» χωρίς αριθμό)
    low = raw.lower()
    if any(w in low for w in ["φέτος", "φετος", "τρέχον", "τρεχον"]):
        from datetime import datetime
        return str(datetime.now().year)

    if any(w in low for w in ["πέρσι", "περσι", "περυσι", "πέρυσι"]):
        from datetime import datetime
        return str(datetime.now().year - 1)

    ng = normalize_greek(q)
    if from_voice:
        vfix = _voice_misheard_twenties_greek(ng)
        if vfix:
            return vfix

    # Προφορικά ελληνικά έτη (π.χ. «δύο χιλιάδες είκοσι τέσσερα»)
    verbal = _greek_verbal_year(ng)
    if verbal:
        return verbal

    # 4ψήφιο έτος 2000–2039. Προτιμούμε το **τελευταίο** (όχι το πρώτο): το STT συχνά
    # βάζει θόρυβο νωρίς, ενώ το έτος λέγεται στο τέλος («… για το 2024»).
    year_re = re.compile(r"\b(20[0-3][0-9])\b")
    matches = list(year_re.finditer(q))
    if not matches:
        return ""
    y = matches[-1].group(1)
    if from_voice:
        y = _apply_voice_stt_decade_fix(y)
    return y


# =============================================================================
# PROCEDURE TYPE DETECTION
# =============================================================================
PROCEDURE_PATTERNS = {
    "direct award": [
        "απευθείας", "απευθειας", "απ' ευθείας", "απ ευθειας",
        "direct", "χωρίς διαγωνισμό", "χωρις διαγωνισμο"
    ],
    "open": [
        "ανοικτός", "ανοικτος", "ανοιχτός", "ανοιχτος",
        "open", "δημόσιος διαγωνισμός", "δημοσιος διαγωνισμος"
    ],
    "negotiated": [
        "διαπραγμάτευση", "διαπραγματευση", "negotiated",
        "με διαπραγμάτευση"
    ],
    "restricted": [
        "κλειστός", "κλειστος", "restricted", "περιορισμένος"
    ]
}

def detect_procedure_type(question: str) -> Optional[str]:
    """Ανιχνεύει τον τύπο διαδικασίας από την ερώτηση."""
    q_lower = question.lower()
    
    for proc_type, patterns in PROCEDURE_PATTERNS.items():
        for pattern in patterns:
            if pattern in q_lower:
                return proc_type
    
    return None


# =============================================================================
# WRAPPER - επιλέγει την καλύτερη μέθοδο
# =============================================================================
def extract_entity_smart(
    question: str,
    entity_cache: Dict[str, List[str]]
) -> Optional[Dict]:
 
    # --- CPV detection FIRST (raw question, no normalization) ---
    raw_q = question.lower()

    m = re.search(r"cpv\s*(\d{5})", raw_q)
    if m:
        code = m.group(1)
        print(f"[DEBUG] ✅ CPV detected (raw): {code}")
        return {
            "label": "CPV",
            "property": "code",
            "value": code,
            "score": 5.0,
            "alternatives": [],
        }
# ------------------------------------------------------------
   # ---- CPV DETECTION (ADD THIS BLOCK FIRST) -------------------
    cpv_code = extract_cpv_from_question(question)
    if cpv_code:
        print(f"[DEBUG] ✅ CPV detected: {cpv_code}")
        return {
            "label": "CPV",
            "property": "code",
            "value": cpv_code,
            "score": 3.0,
            "alternatives": [],
        }
# -------------------------------------------------------------
    """
    Smart wrapper που επιλέγει την καλύτερη μέθοδο extraction.
    """
    # Πρώτα δοκίμασε composite (καλύτερο για σύνθετα ονόματα)
    result = extract_entity_composite(question, entity_cache)
    
    if result and result["score"] >= 2.0:
        return result
    
    # Fallback στην απλή μέθοδο
    simple_result = extract_entity_from_question(question, entity_cache)
    
    # Επέλεξε το καλύτερο
    best = None
    if result and simple_result:
        best = result if result["score"] >= simple_result["score"] else simple_result
    elif result:
        best = result
    else:
        best = simple_result
        
    if best and best["score"] < 1.5:
        print(f"   [SMART] Best match score too low ({best['score']:.1f}), ignoring.")
        return None
        
    return best


# =============================================================================
# FORMATTING & GRAMMAR UTILITIES
# =============================================================================

def format_authority_name(name: str) -> str:
    """Prettifies uppercase authority names from Neo4j."""
    if not name: return ""
    
    # 1. Βασική μετατροπή σε Title Case (αλλά προσέχουμε τα αρκτικόλεξα)
    # Αν είναι όλο κεφαλαία, το κάνουμε πιο ευανάγνωστο
    words = name.split()
    pretty_words = []
    for w in words:
        if len(w) <= 3: # Πιθανό αρκτικόλεξο
            pretty_words.append(w.upper())
        else:
            pretty_words.append(w.capitalize())
    
    res = " ".join(pretty_words)
    
    # 2. Ειδικές περιπτώσεις
    res = res.replace("Απθ", "ΑΠΘ")
    res = res.replace("Εαδησυ", "ΕΑΔΗΣΥ")
    res = res.replace("Πγνθ", "ΠΓΝΘ")
    res = res.replace("Αχεπα", "ΑΧΕΠΑ")
    
    return res

def get_article(name: str) -> str:
    """Returns the correct Greek article (Ο/Η/Το) for an authority name."""
    n = normalize_greek(name).lower()
    
    # Θηλυκά (Η)
    if any(n.startswith(p) for p in ["εταιρεια", "υπηρεσια", "επιτροπη", "περιφερεια", "διευθυνση"]):
        return "Η"
    # Ουδέτερα (Το)
    if any(n.startswith(p) for p in ["πανεπιστημιο", "νοσοκομειο", "υπουργειο", "επιμελητηριο", "ιδρυμα", "κεντρο", "αχεπα", "πγνθ"]):
        return "Το"
    # Αρσενικά (Ο)
    if any(n.startswith(p) for p in ["δημος", "οργανισμος", "φορεας"]):
        return "Ο"
        
    # Default based on suffix
    if n.endswith("ος"): return "Ο"
    if n.endswith("α") or n.endswith("η"): return "Η"
    if n.endswith("ο"): return "Το"
    
    return "Η αναθέτουσα αρχή" # Safety fallback

def extract_article_from_question(question: str, entity_name: str) -> Optional[str]:
    """Attempts to extract the article used by the user for a specific entity."""
    q = normalize_greek(question).lower()
    words = q.split()
    
    # Ψάξε για το όνομα της αρχής στην ερώτηση
    entity_norm = normalize_greek(entity_name).lower()
    first_word_entity = entity_norm.split()[0] if entity_norm.split() else ""
    
    if not first_word_entity: return None
    
    try:
        idx = words.index(first_word_entity)
        if idx > 0:
            prev_word = words[idx-1]
            if prev_word in ["ο", "η", "το", "του", "της", "των", "στον", "στην", "στο"]:
                # Μετατροπή σε ονομαστική άρθρου
                art_map = {
                    "ο": "Ο", "τον": "Ο", "στον": "Ο",
                    "η": "Η", "την": "Η", "της": "Η", "στην": "Η",
                    "το": "Το", "στο": "Το",
                    "του": "Ο", # Default αρσενικό αν είναι "του"
                }
                return art_map.get(prev_word)
    except:
        pass
        
    return None
def extract_entity_from_question(question: str, entity_cache: dict):
    """
    Backward-compatible wrapper for existing code.
    Routes to extract_entity_smart.
    """
    return extract_entity_smart(question, entity_cache)