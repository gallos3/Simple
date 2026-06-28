"""
Simple - Main Engine
Orchestrates all components to answer natural language questions.
"""
import re
from typing import Optional, Dict, Any, Union
from data_access.entity_extractor import normalize_greek

# Authentication State
IS_AUTHENTICATED_AUDITOR = False
PENDING_AUTH = {
    "active": False,
    "authority": None,
    "year": None
}
# =============================================================================
# PREDEFINED FOLLOW-UPS (pattern → προτροπή + query id, με σειρά προτεραιότητας)
# =============================================================================
PREDEFINED_FOLLOWUP_CANDIDATES = {
    "απευθείας αναθέσεις": [
        ("Θέλεις να δεις τους top αναδόχους της αρχής σε απευθείας αναθέσεις", 36),
        ("Θέλεις να δεις τις top 5 αναθέτουσες σε απευθείας αναθέσεις", 6),
    ],
    "συνολική αξία": [
        ("Θέλεις να δεις τη μέση αξία σε απευθείας αναθέσεις", 10),
    ],
    "εταιρείες": [
        ("Θέλεις να δεις τις top 10 εταιρείες", 12),
    ],
    "αναθέτουσες αρχές": [
        ("Θέλεις να δεις τις top 5 σε απευθείας αναθέσεις", 6),
        ("Θέλεις να δεις τις top 10 αναθέτουσες σε απευθείας αναθέσεις", 15),
    ],
}


def _can_run_predefined_query(query: Dict, entity: Optional[Dict], year: str) -> bool:
    """True αν το query μπορεί να τρέξει με το τρέχον context (χωρίς Neo4j)."""
    if not query:
        return False
    cypher = query.get("query") or query.get("cypher") or ""
    if "$name" in cypher and not (entity and entity.get("value")):
        return False
    if "$year" in cypher and not year:
        return False
    return True


def _pick_followup_candidate(
    question: str,
    entity: Optional[Dict],
    year: str,
) -> Optional[tuple]:
    """Επιλέγει (prompt, query_dict) από τα patterns που ταιριάζουν."""
    q_lower = normalize_greek(question)
    for pattern, candidates in PREDEFINED_FOLLOWUP_CANDIDATES.items():
        if normalize_greek(pattern) not in q_lower:
            continue
        for prompt_text, query_id in candidates:
            qdef = get_predefined_query(query_id)
            if _can_run_predefined_query(qdef, entity, year):
                return prompt_text, qdef
    return None

def detect_intent(question: str, entity=None, history: list = None) -> str:
    """Ανιχνεύει το intent της ερώτησης με χρήση normalization."""
    
    # 7. Social (Short-circuited before entity extraction to prevent expensive fallback loops on greetings)
    from utils.social_handler import handle_social_query
    if handle_social_query(question):
        return "social"

    from data_access.entity_extractor import normalize_greek, load_entity_cache, extract_entity_from_question
    
    if isinstance(entity, list):
        history = entity
        entity = None
        
    if entity is None or not isinstance(entity, dict):
        entity_cache = load_entity_cache()
        entity = extract_entity_from_question(question, entity_cache)
        
    q_raw = question.lower()
    q = normalize_greek(q_raw)
    # ---- CPV diagnostic override ------------------------------
    if entity and entity.get("label") == "CPV":
        print("[DEBUG] ✅ Routing to market_diagnostic")
        return "market_diagnostic"
    # -----------------------------------------------------------
    # 1. Έκθεση / report (Απόλυτη προτεραιότητα - γρήγορο check)
    report_keywords = ["εκθεση", "αναφορα", "report", "audit", "pdf", "docx", "κατεβασμα"]
    if any(k in q for k in report_keywords):
        return "report"

    # 2. Simulation / Serious Game (Γρήγορο check πριν το βαρύ entity extraction)
    sim_keywords_en = ["scenario", "simulation", "case study", "training", "exercise", "test me", "start", "new", "serious game"]
    sim_keywords_gr = ["περιστατικο", "σεναριο", "προσομοιωση", "εξετασε με", "ξεκινα", "παιχνιδι", "εκπαιδευση", "μαθημα", "ασκηση"]
    if any(k in q_raw for k in sim_keywords_en) or any(k in q for k in sim_keywords_gr):
        return "procurement_simulation"

    # 3. Evaluation / Report Card
    osce_keywords_en = ["end simulation", "finish", "report card"]
    osce_keywords_gr = ["τελος", "αξιολογηση", "βαθμολογια", "αναφορα"]
    if any(k in q_raw for k in osce_keywords_en) or any(k in q for k in osce_keywords_gr):
        return "procurement_report_card"

    # 4. Maintain Simulation State
    if history:
        for msg in reversed(history):
            if msg.get("role") in ["bot", "assistant"]:
                text = msg.get("text", "")
                if "[SCENARIO]" in text or "[CHALLENGE]" in text or "[QUESTION]" in text or "[OPTIONS]" in text:
                    return "procurement_simulation"
                break

    # 5. DATA-FIRST CHECK: Questions about quantities/rankings are NEVER legal
    # Must come BEFORE legal keywords because words like "συμβάσεις" appear in both contexts.
    data_interrogatives = ["ποια", "ποιος", "ποιες", "ποιοι", "ποιο", "ποσες", "ποσοι", "ποσο", "ποσα",
                           "δειξε", "δείξε", "εμφανισε", "εμφάνισε", "φερε", "φέρε", "λιστα", "λίστα"]
    data_superlatives = ["περισσοτερ", "μεγαλυτερ", "υψηλοτερ", "μικροτερ", "λιγοτερ", "top", "πρωτ", "κορυφ"]
    data_terms = ["συμβασ", "αναθεσ", "αξια", "ποσο", "πληθος", "συνολ"]
    
    has_data_interrogative = any(k in q or k in q_raw for k in data_interrogatives)
    has_data_superlative = any(k in q or k in q_raw for k in data_superlatives)
    has_data_term = any(k in q or k in q_raw for k in data_terms)
    
    # Superlative/ranking + "εταιρ" → always data_simple (e.g. "top 5 εταιρείες", "μεγαλύτερες εταιρείες")
    if any(k in q_raw or k in q for k in ["top", "best", "μεγαλ", "κορυφ"]) and "εταιρ" in q:
        return "data_simple"

    if has_data_interrogative and (has_data_superlative or has_data_term):
        return "data_simple"

    # 5b. Keyword-based Context Detection (fast, no entity extraction needed)
    # Entity extraction happens LATER in streaming_endpoint.py only for intents that need it.
    
    has_law_ref = bool(
        re.search(r"\bν\.?\s*\d{3,5}", q_raw) or 
        re.search(r"νομος\s+\d{3,5}", q) or
        "4412" in q or "5164" in q
    )
    
    diag_keywords = ["διαγνωση", "διάγνωση", "πορισμα", "πόρισμα", "θεραπεια", "θεραπεία", "εντροπια", "εντροπία", "entropy", "ici", "closure"]
    has_diag = any(k in q for k in diag_keywords)
    
    has_legal_keywords = any(
        k in q
        for k in [
            "αρθρο", "παρ.", "παραγραφος", "απροβλεπ", "εκτακτη αναγκη",
            "presetex", "προδικαστικ", "νομολογια", "νομιμο", "παρανομο",
            "νομικ", "νομιμοτητα", "curia", "κυρια", "δικαστηριο", "εαδησυ",
            "επιτρεπεται",
            "διαπραγματευσ", "διαδικασι", "δικαιωμα", "προθεσμι", "ενσταση",
            "προσφυγη", "νομος", "ν.4412", "ν. 4412",
            "διαγωνισμ", "προκηρυξ", "διαφανει"
        ]
    ) or has_diag

    if has_law_ref or has_legal_keywords:
        # Check if they explicitly mentioned an authority by NAME in their question text
        mentions_authority_keyword = any(
            k in q for k in ["δημος", "νοσοκομειο", "αναθετουσα", "περιφερεια", "υπουργειο", "φορεας"]
        )
        
        # If it is a diagnostic query, route to mixed_legal_data (Agent) immediately
        if has_diag:
            return "mixed_legal_data"
            
        # If they mention a specific authority keyword, route to mixed (needs entity later)
        if mentions_authority_keyword:
            return "mixed_legal_data"
        # Pure legal question (no authority) → Legal RAG
        return "legal"

    # 6. Risk / stats
    if any(k in q for k in ["κατατμηση", "τεμαχισμ", "μονοπωλ", "κινδυνος", "risk", "οριο"]):
        return "data_risk"

    if any(k in q for k in ["ποσες", "ποσοι", "ποσο", "ποσα", "οσε", "οσα", "συνολο", "πληθος", "γραφημα", "μεσος ορος"]):
        return "data_simple"

    print(f"[DEBUG] FINAL ENTITY: {entity}")
    return "general"



GREEK_NUMBER_WORDS = {
    "ενα": 1, "ένα": 1, "μια": 1, "μία": 1,
    "δυο": 2, "δύο": 2,
    "τρια": 3, "τρία": 3,
    "τεσσερα": 4, "τέσσερα": 4,
    "πεντε": 5, "πέντε": 5,
    "εξι": 6, "έξι": 6,
    "εφτα": 7, "επτά": 7,
    "οκτω": 8, "οκτώ": 8,
    "εννεα": 9, "εννέα": 9,
    "δεκα": 10, "δέκα": 10,
}

from ai.llm_interface import (
    generate_followup_question,
    generate_cypher_query,
    summarize_query_result,
    answer_general_question,
)
from analytics.report_generator import (
    generate_full_audit_report,
    generate_minimal_audit_report,
    run_illegal_award_checks_and_export_docx,
    get_latest_export_path,
    run_compliance_checks,   # 101108
    get_over_limit_cases,    # refactored
)
from rag.graph_rag import search_graph_corpus  # GraphRAG replaces legal_rag
from data_access.database import run_queries_batch
from typing import Any, Dict, List, Optional, Tuple, Union
from utils.config import (
    SIMILARITY_THRESHOLD, is_dangerous_query,
    DirectContractThresholds, EXCLUDED_CPV_CODES,
    API_HOST, API_PORT,   
)
from data_access.database import (
    execute_cypher, get_predefined_query, get_all_predefined_queries,
    replace_entity_in_query, extract_graph_elements
)
from data_access.entity_extractor import (
    extract_entity_from_question, extract_year_from_question,
    detect_procedure_type, load_entity_cache
)
from data_access.query_matcher import (
    get_query_match, is_follow_up_question, detect_output_type,
    detect_normalized_query_type
)
from utils.procedure_map import PROCEDURE_ALIASES as PROCEDURE_MAP_ALIASES
from ai.agent_modules import (
    generate_data_risk_answer,
    generate_mixed_audit_answer,
    build_compliance_summary
)
# =============================================================================
# STATE
# =============================================================================
_last_query_id = None
_last_entity = None
_last_results = None
# Follow-up conversational state
PENDING_FOLLOWUP = {
    "active": False,
    "question": None,
    "query_id": None,
    "entity": None,
    "year": None,
}
PENDING_DISAMBIGUATION = {
    "active": False,
    "original_question": None,
    "alternatives": [],
}

# Μετά από μήνυμα γράψε ολόκληρη επωνυμία / για ποιο έτος από το illegal_direct_awards playbook
PENDING_ILLEGAL_AWARDS = {
    "active": False,
    "waiting_for_full_authority_name": False,
    "year": "",
    "authority": "",
    "from_voice": False,
}


def clear_pending_illegal_awards() -> None:
    global PENDING_ILLEGAL_AWARDS
    PENDING_ILLEGAL_AWARDS = {
        "active": False,
        "waiting_for_full_authority_name": False,
        "year": "",
        "authority": "",
        "from_voice": False,
    }


def set_pending_illegal_awards_clarification(
    *,
    waiting_for_full_authority_name: bool,
    year: str = "",
    authority: str = "",
    from_voice: bool = False,
) -> None:
    global PENDING_ILLEGAL_AWARDS
    PENDING_ILLEGAL_AWARDS = {
        "active": True,
        "waiting_for_full_authority_name": waiting_for_full_authority_name,
        "year": (year or "").strip(),
        "authority": (authority or "").strip(),
        "from_voice": bool(from_voice),
    }


def merge_pending_illegal_awards_question(question: str, current_from_voice: bool) -> Optional[str]:
    """
    Αν ο χρήστης απαντά με επωνυμία ή έτος μετά από prompt του playbook, χτίζει πλήρη ερώτηση.
    Αποφεύγει το γενικό LLM που αλληθωρίζει σε ονόματα φορέων.
    """
    global PENDING_ILLEGAL_AWARDS
    p = PENDING_ILLEGAL_AWARDS
    if not p.get("active"):
        return None
    wait_auth = bool(p.get("waiting_for_full_authority_name"))
    y_saved = (p.get("year") or "").strip()
    auth_saved = (p.get("authority") or "").strip()
    fv = bool(p.get("from_voice") or current_from_voice)
    q = (question or "").strip()
    clear_pending_illegal_awards()
    base = "έλεγξε μη νόμιμες απευθείας αναθέσεις για"
    if wait_auth:
        if y_saved:
            return f"{base} {q} για το {y_saved}"
        return f"{base} {q}"
    if auth_saved:
        y2 = extract_year_from_question(question, from_voice=fv)
        yr = y2 if y2 else q
        return f"{base} {auth_saved} για το {yr}"
    return None


YEAR_PROMPT_MARKER = "Για ποιο **έτος**"


def _is_bot_role(role: str) -> bool:
    return (role or "") in ("bot", "assistant")


def _is_year_prompt_message(msg: dict) -> bool:
    return _is_bot_role(msg.get("role", "")) and YEAR_PROMPT_MARKER in (msg.get("text") or "")


def merge_pending_year_reply(question: str, history: list = None) -> str:
    """
    Αν ο χρήστης απαντά μόνο με έτος μετά το prompt έτους, ενώνει με την προηγούμενη ερώτηση.
    Το frontend στέλνει role «bot» (όχι «assistant»).
    """
    if not history or len(history) < 2:
        return question
    year = extract_year_from_question(question)
    if not year:
        return question

    last = history[-1]
    prompt_msg = None
    if _is_year_prompt_message(last):
        prompt_msg = last
    elif last.get("role") == "user" and len(history) >= 3 and _is_year_prompt_message(history[-2]):
        prompt_msg = history[-2]

    if not prompt_msg:
        return question

    for msg in reversed(history):
        if msg is prompt_msg:
            continue
        if msg.get("role") == "user":
            original = (msg.get("text") or "").strip()
            if not original or original == question.strip():
                continue
            merged = f"{original} το {year}"
            print(f"[YEAR-REPLY] Merged: {merged}")
            return merged
    return question


def _clear_disambiguation():
    global PENDING_DISAMBIGUATION
    PENDING_DISAMBIGUATION = {"active": False, "original_question": None, "alternatives": []}

def _parse_choice_index(text: str) -> Optional[int]:
    t = (text or "").strip().lower()

    # 1) ψηφία: "2", "το 2", "νούμερο 2"
    m = re.search(r"\b(\d{1,2})\b", t)
    if m:
        try:
            return int(m.group(1))
        except:
            return None

    # 2) λέξεις: "δύο", "το δύο", "νούμερο δύο"
    # normalize (αφαίρεση τόνων) για να πιάσει και "δύο"/"δυο"
    t_norm = normalize_greek(t)
    for w, n in GREEK_NUMBER_WORDS.items():
        if re.search(rf"\b{re.escape(normalize_greek(w))}\b", t_norm):
            return n

    return None


def _is_yes(text: str) -> bool:
    """Ελέγχει αν ο χρήστης απάντησε θετικά."""
    t = text.strip().lower()
    yes_patterns = [
        "ναι", "ναί", "nai",
        "οκ", "ok", "οκέι",
        "εντάξει", "ενταξει",
        "δείξε", "δειξε", "πες μου",
        "θέλω", "θελω",
        "sure", "yes"
    ]
    # Έλεγχος για ακριβή match ή αρχή
    for p in yes_patterns:
        if t == p or t.startswith(p + " ") or t.startswith(p + ",") or t.startswith(p + "."):
            return True
    return False

def _is_no(text: str) -> bool:
    """Ελέγχει αν ο χρήστης απάντησε αρνητικά."""
    t = text.strip().lower()
    no_patterns = [
        "όχι", "οχι", "oxi",
        "no", "nope",
        "δε θέλω", "δεν θέλω",
        "άφησέ", "αφησε", "σταμάτα"
    ]
    for p in no_patterns:
        if t == p or t.startswith(p + " ") or t.startswith(p + ",") or t.startswith(p + "."):
            return True
    return False

def _clear_followup():
    """Καθαρίζει το follow-up state."""
    global PENDING_FOLLOWUP
    PENDING_FOLLOWUP = {
        "active": False,
        "question": None,
        "query_id": None,
        "entity": None,
        "year": None,
    }
    print(f"[FOLLOWUP] State cleared")


def _execute_followup() -> str:
    """Εκτελεί την αποθηκευμένη ερώτηση follow-up με fallback στο LLM."""
    global PENDING_FOLLOWUP
    
    if not PENDING_FOLLOWUP.get("active"):
        return "Δεν έχω κάτι συγκεκριμένο για συνέχεια. Πες μου μια νέα ερώτηση."

    follow_q = PENDING_FOLLOWUP.get("question") or ""
    query_id = PENDING_FOLLOWUP.get("query_id")
    entity = PENDING_FOLLOWUP.get("entity")
    year = PENDING_FOLLOWUP.get("year")
    
    print(f"[FOLLOWUP] Executing query_id={query_id}: {follow_q}")
    _clear_followup()

    # 1) Απευθείας εκτέλεση του αποθηκευμένου predefined query
    if query_id:
        match = get_predefined_query(query_id)
        if match and _can_run_predefined_query(match, entity, year):
            print(f"[FOLLOWUP]  Running stored query: {query_id}")
            return _execute_matched_query(match, entity, year, follow_q or match.get("question", ""))
        return (
            "Δεν μπόρεσα να τρέξω αυτή την πρόταση με τα διαθέσιμα στοιχεία. "
            "Δοκίμασε π.χ. με συγκεκριμένη αναθέτουσα αρχή ή άλλη ερώτηση."
        )

    # 2) Legacy: fuzzy match (μόνο αν δεν υπάρχει query_id)
    match = match_predefined_query(follow_q, has_entity=bool(entity))
    if match and _can_run_predefined_query(match, entity, year):
        print(f"[FOLLOWUP]  Found predefined match: {match.get('id')}")
        return _execute_matched_query(match, entity, year, follow_q)
    
    # 2) Fallback: Δοκίμασε LLM  Cypher
    print(f"[FOLLOWUP] No predefined match, trying LLM...")
    from ai.llm_interface import generate_cypher_query
    generated_cypher = generate_cypher_query(follow_q)
    
    if generated_cypher:
        print(f"[FOLLOWUP] LLM generated Cypher: {generated_cypher[:100]}...")
        
        # Replace entity if present
        if entity and "$name" in generated_cypher:
            from data_access.database import replace_entity_in_query
            generated_cypher = replace_entity_in_query(generated_cypher, entity["value"])
        
        from data_access.database import execute_cypher
        result = execute_cypher(generated_cypher)
        
        # Αν δούλεψε, επέστρεψε το αποτέλεσμα
        if not (isinstance(result, str) and result.startswith("")):
            print(f"[FOLLOWUP]  LLM query succeeded")
            return f" (AI-generated query)\n\n{result}"
        else:
            print(f"[FOLLOWUP]  LLM query failed: {result}")
    
    # 3) Τελευταία λύση: General LLM answer
    print(f"[FOLLOWUP] Falling back to general answer...")
    from ai.llm_interface import answer_general_question
    return answer_general_question(follow_q)

# =============================================================================
# FIX 1: Εξαγωγή άρθρου από την ερώτηση
# =============================================================================
def extract_article_from_question(question: str, entity_value: str) -> Optional[str]:
    """
    Εξάγει το άρθρο (Ο/Η/Το) που χρησιμοποιεί ο χρήστης στην ερώτηση.
    
    Παραδείγματα:
    - "πόσες συμβάσεις έχει το Ιπποκράτειο"  "Το"
    - "δείξε μου του Δήμου Αθηναίων"  "Ο" 
    """
    q_lower = question.lower()
    entity_norm = entity_value.lower()
    
    # Patterns για εύρεση του άρθρου πριν από το όνομα
    patterns = [
        rf'\b(ο|η|το|του|της|στο|στη|στα|στους|στον|στην|τον|την)\s+["\']?{re.escape(entity_norm[:15])}',
    ]
    
    for p in patterns:
        m = re.search(p, q_lower)
        if m:
            art = m.group(1)
            if art in ["του", "στον", "τον"]: return "Ο"
            if art in ["της", "στην", "την", "στη"]: return "Η"
            if art in ["στο", "στα"]: return "Το"
            return art.capitalize()
    
    # Guessing based on keywords in name
    if any(x in entity_norm for x in ["δημος", "οργανισμος", "φορεας", "συνδεσμος"]):
        return "Ο"
    if any(x in entity_norm for x in ["περιφερεια", "εταιρεια", "υπηρεσια", "αρχη", "επιτροπη", "διαχειριση"]):
        return "Η"
    if any(x in entity_norm for x in ["νοσοκομειο", "πανεπιστημιο", "υπουργειο", "ιδρυμα", "κεντρο", "επιμελητηριο", "λιμενικο"]):
        return "Το"
        
    return None
    return None
def detect_playbook_intent(question: str) -> Optional[str]:
    q = normalize_greek((question or "").lower())

    triggers = [
        "μη νομιμε",
        "παρανομε",
        "απευθειας αναθε",
        "καταμηση",
        "κατατμησ",
        "υπέρβαση",
        "υπερβασ",
        "ελεγχος",
        "ελεγξε",
        "risk",
        "irregularity",
        "illegal direct awards",
    ]
    
    irregularity_keywords = ["ενδειξ", "κατατμησ", "καταμησ", "υπερβασ", "ελεγχ", "risk", "irregularity", "μη νομιμε", "παρανομε", "illegal"]
    if not any(k in q for k in irregularity_keywords):
        return None
    # FIX: Αν περιέχει νομικές λέξεις (Curia, νομολογία) ή διαγνωστικές λέξεις, μην το πας σε playbook
    # για να μπορέσει να πάει στο legal RAG / Web search ή στο Diagnostic Engine.
    legal_indicators = [
        "curia", "κυρια", "νομολογια", "δικαστηριο", "νομικ", "επιτρεπ", "κανονες", "διαταξεις",
        "διαγνωση", "διάγνωση", "πορισμα", "πόρισμα", "θεραπεια", "θεραπεία",
        "οριο", "όριο", "ποιο ειναι", "ποιο είναι", "τι ειναι", "τι είναι"
    ]
    if any(k in q for k in legal_indicators):
        return None

    # FIX 2: Αν ζητάει "έκθεση" ή "αναφορά", μην το πας σε playbook. 
    # Θέλουμε να πάει στο formal report generator (intent=report).
    report_keywords = ["εκθεση", "αναφορα", "report", "audit", "pdf", "docx"]
    if any(k in q for k in report_keywords):
        return None

    if any(t in q for t in triggers):
        return "illegal_direct_awards"

    return None

def agent_answer(question: str, previous_question: str = "", from_voice: bool = False, role: str = None, web_search_enabled: bool = True) -> Union[str, Dict[str, Any]]:
    global PENDING_FOLLOWUP, PENDING_DISAMBIGUATION
    from utils.config import ROLE_PERMISSIONS, DEFAULT_ROLE, ROLE_TRAINEE
    from rag.cag_cache import get_cag_cache

    role = role or DEFAULT_ROLE
    print(f"\n [AGENT] Question: {question} | Role: {role}")
    
    # 0) CAG CACHE CHECK (Skip if pending state)
    if not PENDING_DISAMBIGUATION.get("active") and not PENDING_FOLLOWUP.get("active"):
        cached = get_cag_cache().get(question)
        if cached:
            return {"text": cached, "cached": True} if isinstance(cached, str) else cached
    # 0) Αν περιμένουμε αποσαφήνιση και ο χρήστης απαντά "1/2/3..."
    if PENDING_DISAMBIGUATION.get("active"):
        idx = _parse_choice_index(question)
        alts = PENDING_DISAMBIGUATION.get("alternatives") or []
        if idx is not None and 1 <= idx <= len(alts):
            chosen = alts[idx - 1]
            original = PENDING_DISAMBIGUATION.get("original_question") or ""
            _clear_disambiguation()

            # Trick: ξανακάνε την αρχική ερώτηση αλλά "δέσε" μέσα το πλήρες όνομα,
            # ώστε ο entity_extractor να βγάλει unambiguous match.
            rerun_q = f"{original} ({chosen})"
            return agent_answer(rerun_q, previous_question="disambiguation", from_voice=from_voice)

        # Αν είπε κάτι άλλο ή λάθος αριθμό, δώσε καθοδήγηση χωρίς να πέσεις σε LLM.
        if idx is not None and (idx < 1 or idx > len(alts)):
            return f"Δώσε αριθμό από 1 έως {len(alts)}."
        return "Θες να επιλέξεις 1, 2, 3... από τις πιθανές αναθέτουσες;"

    if previous_question == "followup":
        # ΜΗΝ ξαναβάζεις follow-up
        skip_followup = True
    else:
        skip_followup = False

    # 1) Αν υπάρχει εκκρεμής πρόταση και ο χρήστης απαντά "ναι" / "όχι"
    if PENDING_FOLLOWUP.get("active"):
        if _is_yes(question):
            print("   [AGENT] User answered YES to follow-up.")
            return _execute_followup()

        if _is_no(question):
            print("   [AGENT] User answered NO to follow-up.")
            _clear_followup()
            return "Εντάξει. Πες μου τι άλλο θα ήθελες να ελέγξουμε."

        # Οτιδήποτε άλλο: το θεωρούμε νέα, ανεξάρτητη ερώτηση
        print("   [AGENT] Follow-up was active, αλλά ο χρήστης ρώτησε κάτι άλλο. Καθαρίζω follow-up state.")
        _clear_followup()
    # === PLAYBOOK ROUTING (conversation-first, deterministic) ===
    playbook_id = detect_playbook_intent(question)
    print("[PLAYBOOK ROUTER] playbook_id =", playbook_id)

    if playbook_id == "illegal_direct_awards":
        print("[PLAYBOOK ROUTER] ENTER illegal_direct_awards")
        clear_pending_illegal_awards()
        from analytics.playbook_runner import run_illegal_direct_awards_playbook
        out = run_illegal_direct_awards_playbook(question, from_voice=from_voice)
        print("[PLAYBOOK ROUTER] EXIT illegal_direct_awards, returning")
        return out

    merged_illegal = merge_pending_illegal_awards_question(question, from_voice)
    if merged_illegal:
        print(f"[PLAYBOOK ROUTER] pending clarification -> merged: {merged_illegal[:80]}...")
        from analytics.playbook_runner import run_illegal_direct_awards_playbook
        return run_illegal_direct_awards_playbook(merged_illegal, from_voice=from_voice)

    # 2) Κανονικός χειρισμός intent, όπως πριν
    entity = extract_entity_from_question(question, entity_cache)
    intent = detect_intent(question, entity, history)

    print(f"   Detected intent: {intent}")

    # === PERMISSION GUARD ===
    allowed_intents = ROLE_PERMISSIONS.get(role, [])
    if intent not in allowed_intents:
        print(f"   [GUARD] Blocked intent '{intent}' for role '{role}'")
        if role == ROLE_TRAINEE:
            return {
                "text": " **Περιορισμένη Πρόσβαση**: Ως εκπαιδευόμενος, δεν έχετε πρόσβαση σε πραγματικά δεδομένα ελέγχου ή έκδοση εκθέσεων. Παρακαλώ επικεντρωθείτε στο εκπαιδευτικό σας σενάριο ή ρωτήστε γενικές νομικές ερωτήσεις.",
                "role_restricted": True
            }
        return f"Access Denied: Role '{role}' cannot perform '{intent}'."

    # === SIMULATION / SERIOUS GAME ===
    if intent == "procurement_simulation":
        from simulation.procurement_simulation import build_simulation_prompt, SIMULATION_SYSTEM_PROMPT
        from ai.llm_interface import call_llm
        # RAG skipped for simulation (no embedding model needed)
        rag_ctx = ""
        prompt = build_simulation_prompt(question, [], rag_ctx)
        answer = call_llm(prompt, max_tokens=1024, system_prompt=SIMULATION_SYSTEM_PROMPT)
        
        return {
            "text": answer,
            "action": "start_simulation"
        }

    # === EVALUATION / REPORT CARD ===
    if intent == "procurement_report_card":
        from simulation.procurement_simulation import generate_report_card
        import json
        # In a real scenario, history would be passed from the frontend
        history = [] 
        report_json = generate_report_card(history)
        try:
            report_data = json.loads(report_json)
            return {
                "text": " Η αξιολόγησή σας ολοκληρώθηκε.",
                "action": "show_report_card",
                "report": report_data
            }
        except:
            return {
                "text": " Σφάλμα κατά τη δημιουργία της αναφοράς.",
                "raw_report": report_json
            }

    # === LEGAL (RAG) ===
    if intent == "legal":
        passages = search_graph_corpus(question)
        web_results = ""
        if web_search_enabled:
            web_results = search_legal_web(question)
        
        # Merge context
        context_to_use = passages[:]
        if web_results:
            context_to_use.append(f"Web Results (Curia/EAADHSY):\n{web_results}")
            
        answer = generate_legal_answer(question, context_to_use)
        
        # Cache it
        get_cag_cache().add(question, answer, query_type="legal")
        
        return {
            "text": answer,
            "web_sources": web_results
        }

    # Extract authority/year όπως ήδη κάνει το Simple
    entity_cache = load_entity_cache()
    entity = extract_entity_from_question(question, entity_cache)
    entity = disambiguate_authority_by_nuts(entity, question)
    year = extract_year_from_question(question, from_voice=from_voice)

    #  Αν είναι CPV query, ακυρώνουμε το entity για να μην ζητάει disambiguation
    is_cpv_query = bool(re.search(r'cpv\s*\d{4,8}\b', question.lower()) or re.search(r'\b\d{8}\b', question))
    if is_cpv_query:
        entity = None

    if entity and entity.get("ambiguous"):
        # Let the ReAct Agent handle ambiguity if routed there, otherwise block
        if intent not in ["mixed_legal_data", "market_diagnostic", "general"]:
            return (
                "Υπάρχουν περισσότερες από μία αναθέτουσες αρχές με αυτό το όνομα. "
                "Παρακαλώ γράψε ολόκληρη την επωνυμία της αναθέτουσας αρχής."
            )
    
    if intent.startswith("data_") and not entity and not is_cpv_query:
        return "Παρακαλώ όρισε αναθέτουσα αρχή (π.χ. πλήρη επωνυμία)."

    # === 1. REPORT ===
    if intent == "report":
        return _handle_report_request(question, from_voice=from_voice)

    # === 3. MIXED (ΔΗΛΑΔΗ Νομικό + Δεδομένα, ή Διαγνωστικά, ή Agentic) ===
    if intent in ["mixed_legal_data", "market_diagnostic"]:
        authority = entity["value"] if (entity and not entity.get("ambiguous")) else "Ολόκληρη η Αγορά / Απροσδιόριστο"
        
        # Χρήση του νέου ReAct Agent
        from ai.agentic_loop import create_agent
        from rag.cag_cache import get_cag_cache
        
        agent = create_agent()
        # Περνάμε το ερώτημα εμπλουτισμένο με τον φορέα για να έχει context
        enriched_q = f"Για τον φορέα/πλαίσιο '{authority}' (έτος: {year or 'όλα'}): {question}"
        base_answer = agent.run(enriched_q)
        
        # Cache it (data type has shorter TTL)
        get_cag_cache().add(question, base_answer, query_type="data")
        
        return _maybe_attach_followup(question, entity, year, base_answer, intent=intent)


    # === 4. DATA RISK ===
    if intent == "data_risk":
        if not entity:
            return "Ποια αρχή εννοείς;"
        authority = entity["value"]

        compliance = run_compliance_checks(authority, year)
        base_answer = generate_data_risk_answer(
            question, authority, year, compliance
        )
        return _maybe_attach_followup(question, entity, year, base_answer, intent="data_risk")

        # === 5. SIMPLE DATA / PREDEFINED ===
    if intent == "data_simple":
        #  HARDCODED FALLBACK FOR CPV GRAPHS: 
        # Αν έχουμε CPV και ζητάει γράφημα, τρέξε το query 502 απευθείας.
        if is_cpv_query and any(k in question.lower() for k in ["γραφημα", "γράφημα", "γραφου", "γράφου", "graph", "δικτυο"]):
            from data_access.database import get_predefined_query
            match = get_predefined_query(502)
        else:
            match = match_predefined_query(question, has_entity=bool(entity))
            
        if match:
            base_answer = _execute_matched_query(match, entity, year, question)
        else:
            base_answer = _handle_no_match(question, entity, year)

        return _maybe_attach_followup(question, entity, year, base_answer, intent="data_simple")


    # === 5.5 SOCIAL ===
    if intent == "social":
        from utils.social_handler import handle_social_query
        # Try to get user name from history or context if possible
        # For now, we just pass the question
        social_resp = handle_social_query(question)
        if social_resp:
            return social_resp

    # === 6. GENERAL ===
    from ai.llm_interface import answer_general_question
    return answer_general_question(question)
def disambiguate_authority_by_nuts(entity: dict, question: str) -> dict:
    """
    If entity has alternatives, pick the one whose Buyer.NUTS_name matches any token in question.
    """
    if not entity or entity.get("label") != "Buyer":
        return entity
    if entity.get("type") == "buyer_group":
        return entity

    alts = [entity.get("value")] + list(entity.get("alternatives") or [])
    tokens = [normalize_greek(t) for t in re.findall(r"[Α-Ωα-ωΆ-ώ]+", question or "")]
    tokens = [t for t in tokens if len(t) >= 4]  # avoid noise

    try:
        from data_access.database import get_authority_nuts_name
    except Exception:
        return entity

    for name in alts:
        nuts_name = get_authority_nuts_name(name)
        if not nuts_name:
            continue
        n = normalize_greek(nuts_name)
        if any(tok in n for tok in tokens):
            entity["value"] = name
            entity["nuts_name"] = nuts_name
            entity["ambiguous"] = False
            return entity

    return entity
# =============================================================================
# MAIN ENTRY POINT
# =============================================================================
def answer_question(question: str, previous_question: str = "", from_voice: bool = False, role: str = None) -> Any:
    """Κύριο entry point που τώρα περνάει από τον agent."""
    return agent_answer(question, previous_question, from_voice=from_voice, role=role)
# =============================================================================
# REQUEST TYPE DETECTION
# =============================================================================
def _is_report_request(question: str) -> bool:
    """Check if question is asking for an audit report."""
    q_lower = question.lower()
    report_keywords = ["έκθεση", "εκθεση", "αναφορά", "αναφορα", "report", "audit"]
    authority_keywords = ["για", "της", "του", "αρχή", "αρχης"]
    
    has_report = any(kw in q_lower for kw in report_keywords)
    has_authority = any(kw in q_lower for kw in authority_keywords)
    
    return has_report and has_authority

def _is_illegal_awards_report_request(question: str) -> bool:
    """Check if asking for batch illegal awards report."""
    q_lower = question.lower()
    patterns = [
        "συγκεντρωτική έκθεση",
        "συγκεντρωτικη εκθεση",
        "όλες τις παραβάσεις",
        "ολες τις παραβασεις",
        "παράνομες αναθέσεις",
        "παρανομες αναθεσεις",
        "υπερβάσεις ορίου",
        "υπερβασεις οριου"
    ]
    return any(p in q_lower for p in patterns)

# =============================================================================
# HANDLERS
# =============================================================================
import os

API_BASE_URL = f"http://{API_HOST}:{API_PORT}"

def _handle_report_request(question: str, from_voice: bool = False) -> Dict[str, Any]:
    entity_cache = load_entity_cache()
    entity = extract_entity_from_question(question, entity_cache)
    entity = disambiguate_authority_by_nuts(entity, question)
    year = extract_year_from_question(question, from_voice=from_voice)

    if not entity:
        return {
            "text": " Δεν κατάφερα να αναγνωρίσω την αναθέτουσα αρχή. Παρακαλώ διευκρίνισε."
        }

    authority = entity["value"]

    try:
        filepath = generate_full_audit_report(authority, year)
        filename = os.path.basename(filepath)
        download_url = f"{API_BASE_URL}/reports/{filename}"

        return {
            "text": (
                f" Δημιουργήθηκε έκθεση ελέγχου για **{authority}** ({year}).\n\n"
                f" [Κατέβασε την έκθεση]({download_url})"
            ),
            "action": "report_generated",
            "filepath": filename,
            "download_url": download_url,  # optional για το frontend
        }

    except Exception as e:
        return {
            "text": f" Σφάλμα κατά τη δημιουργία της έκθεσης: {str(e)}"
        }
def _handle_illegal_awards_report(question: str, from_voice: bool = False) -> Dict[str, Any]:
    """Handle request for batch illegal awards report."""
    year = extract_year_from_question(question, from_voice=from_voice)
    
    try:
        filepath = run_illegal_award_checks_and_export_docx(year)
        filename = os.path.basename(filepath)
        return {
            "text": f" Δημιουργήθηκε συγκεντρωτική έκθεση παραβάσεων για το {year}.\n\n Χρησιμοποίησε το κουμπί 'Κατέβασε αναφορά' για να την αποθηκεύσεις.",
            "action": "report_generated",
            "filepath": filename
        }
    except Exception as e:
        return {
            "text": f" Σφάλμα: {str(e)}"
        }

def _handle_follow_up(question: str) -> Union[str, Dict[str, Any]]:
    """Handle follow-up questions using previous context."""
    global _last_query_id, _last_entity, _last_results
    
    # Try to get detailed version of last query
    detail_query_id = f"{_last_query_id}_detail"
    detail_query = get_predefined_query(detail_query_id)
    
    if detail_query and _last_entity:
        cypher = detail_query.get("query") or detail_query.get("cypher", "")
        cypher = replace_entity_in_query(cypher, _last_entity["value"])
        result = execute_cypher(cypher)
        return result
    
    # Otherwise return last results
    if _last_results:
        return f" Τα τελευταία αποτελέσματα:\n{_last_results}"
    
    return " Δεν έχω προηγούμενο context. Παρακαλώ κάνε μια νέα ερώτηση."
def _format_table_results(raw_results, max_rows: int = 10) -> str:
    if not isinstance(raw_results, list) or not raw_results:
        return "Δεν βρέθηκαν αποτελέσματα."

    # κρατάμε μόνο dict rows
    rows = [r for r in raw_results if isinstance(r, dict)]
    if not rows:
        return "Δεν βρέθηκαν αποτελέσματα."

    # columns = keys του 1ου row (ή union αν θες)
    cols = list(rows[0].keys())

    lines = []
    for i, row in enumerate(rows[:max_rows], 1):
        parts = []
        for k in cols:
            v = row.get(k)
            if v is None:
                continue
            parts.append(f"{k}: {v}")
        if parts:
            lines.append(f"{i}. " + " | ".join(parts))

    tail = ""
    if len(rows) > max_rows:
        tail = f"\n\n(Εμφανίζονται {max_rows} από {len(rows)} αποτελέσματα.)"

    return "\n".join(lines) + tail

def _summarize_graph_elements(elements: list, authority_name: str = None, year: str = None) -> str:
    """
    Build a concise spoken summary of the graph data.
    Deterministic — no LLM call needed.
    """
    from data_access.entity_extractor import format_authority_name
    
    buyers = []
    winners = []
    awards = []
    total_value = 0.0
    risk_counts = {"low": 0, "medium": 0, "high": 0}
    
    for el in elements:
        d = el.get("data", {})
        group = d.get("group")
        if group == "Buyer":
            buyers.append(d.get("label", ""))
        elif group == "Winner":
            winners.append(d.get("label", ""))
        elif group in ("Award", "Contract"):
            awards.append(d)
            val = d.get("value", 0)
            if val:
                total_value += float(val)
            risk = d.get("risk", "low")
            if risk in risk_counts:
                risk_counts[risk] += 1
    
    if not awards:
        return "Το γράφημα δεν περιέχει δεδομένα συμβάσεων."
    
    # Format authority name
    short_name = format_authority_name(authority_name) if authority_name else "ο φορέας"
    
    # Build parts
    parts = []
    
    # Main count
    year_text = f" για το {year}" if year else ""
    parts.append(f"Το γράφημα δείχνει {len(awards)} συμβάσεις{year_text} με {len(winners)} αναδόχους.")
    
    # Total value
    if total_value > 0:
        if total_value >= 1_000_000:
            val_str = f"{total_value/1_000_000:.1f} εκατ. ευρώ"
        elif total_value >= 1000:
            val_str = f"{total_value/1000:.0f} χιλ. ευρώ"
        else:
            val_str = f"{total_value:.0f} ευρώ"
        parts.append(f"Συνολική αξία: {val_str}.")
    
    # Risk summary
    high = risk_counts.get("high", 0)
    medium = risk_counts.get("medium", 0)
    if high > 0 or medium > 0:
        risk_parts = []
        if high > 0:
            risk_parts.append(f"{high} υψηλού ρίσκου")
        if medium > 0:
            risk_parts.append(f"{medium} μεσαίου ρίσκου")
        parts.append("Από αυτές, " + " και ".join(risk_parts) + ".")
    
    # Top supplier (by frequency in edges — approximate by degree)
    if len(winners) > 0:
        # Count edges per winner
        winner_edge_count = {}
        for el in elements:
            d = el.get("data", {})
            if "source" in d and "target" in d:
                target = d.get("target", "")
                if target in [w_el.get("data", {}).get("id") for w_el in elements if w_el.get("data", {}).get("group") == "Winner"]:
                    lbl = next((w_el.get("data", {}).get("label", "") for w_el in elements if w_el.get("data", {}).get("id") == target), "")
                    winner_edge_count[lbl] = winner_edge_count.get(lbl, 0) + 1
        
        if winner_edge_count:
            top_winner = max(winner_edge_count, key=winner_edge_count.get)
            top_count = winner_edge_count[top_winner]
            if top_count > 1:
                # Clean label (remove "Winner: " prefix)
                clean_name = top_winner.replace("Winner: ", "").strip()
                parts.append(f"Κορυφαίος ανάδοχος: {clean_name} με {top_count} συμβάσεις.")

    return " ".join(parts)

def _execute_matched_query(
    query: Dict,
    entity: Optional[Dict],
    year: str,
    question: str
) -> Union[str, Dict[str, Any]]:
    """Execute a matched predefined query."""
    global _last_query_id, _last_entity, _last_results
    
    query_id = query["id"]
    cypher = query.get("query") or query.get("cypher", "")
    description = query.get("description", "")

    if query_id in (71, 202, 203):
        return (
            "Η βάση δεν περιέχει καταχωρημένο **είδος διαδικασίας ανάθεσης** "
            "(π.χ. ανοικτή, κλειστή, απευθείας ανάθεση). "
            "Δεν είναι δυνατή κατανομή ανά άρθρο 26 ν.4412/2016."
        )

    authority_name = entity["value"] if entity else None

    #  Αν το query δεν χρειάζεται $name, αγνόησε το entity εντελώς
    if "$name" not in cypher:
        entity = None

    authority_name = entity["value"] if entity else None
    # Enrich entity with region from Neo4j (Buyer.NUTS_name)
    authority_location = None
    if entity and entity.get("label") == "Buyer":
        try:
            from data_access.database import get_authority_nuts_name
            authority_location = get_authority_nuts_name(entity.get("value"))
            if authority_location:
                entity["nuts_name"] = authority_location  # attach for later use
        except Exception:
            pass

    print(f"\n EXECUTING QUERY...")

    if "$name" in cypher and not (entity and entity.get("value")):
        return (
            "Για αυτή την ανάλυση χρειάζομαι **αναθέτουσα αρχή** (πλήρη επωνυμία). "
            "Π.χ. «πόσες συμβάσεις έχει ο Δήμος Αθηναίων το 2023»."
        )
    if (query.get("needs_year") or "$year" in cypher) and not year:
        return "Για ποιο έτος θέλεις να τρέξω το ερώτημα;"
    
    # Replace placeholders για authority name
    _group_names = None
    if entity and "$name" in cypher:
        if entity.get("type") == "buyer_group":
            members = list(dict.fromkeys(entity["members"]))  # deduplicate
            # Primary: toLower(var) = toLower($name) → var IN $names (canonical match)
            new_cypher = re.sub(
                r'toLower\(\s*(\w+)\s*\)\s*=\s*toLower\(\s*\$name\s*\)',
                r'\1 IN $names',
                cypher
            )
            if new_cypher != cypher:
                cypher = new_cypher
                _group_names = members  # canonical names, no lowercasing
            else:
                # Fallback: var.name = $name → var.name IN $names
                new_cypher = re.sub(r'(\w+\.name)\s*=\s*\$name', r'\1 IN $names', cypher)
                if new_cypher != cypher:
                    cypher = new_cypher
                    _group_names = members  # canonical names
                else:
                    # Last resort: use first member only
                    from data_access.database import replace_entity_in_query
                    cypher = replace_entity_in_query(cypher, members[0])
            _last_entity = entity
            n = len(members)
            print(f"   [GROUP] $name → IN $names ({n} members)")
        else:
            from data_access.database import replace_entity_in_query
            cypher = replace_entity_in_query(cypher, entity["value"])
            _last_entity = entity
            print(f"   Replaced $name with: {entity['value']}")
    
    # Replace $cpv placeholder
    if "$cpv" in cypher:
        m_cpv = re.search(r'(?:cpv)?\s*(\d{4,8})\b', question.lower())
        cpv_val = m_cpv.group(1) if m_cpv else "45" # default to Works if not found
        cypher = cypher.replace("$cpv", f'"{cpv_val}"')
        print(f"   Replaced $cpv with: {cpv_val}")

    # Prepare Cypher parameters — always rebuild from final cypher state
    query_params = {}
    if "$year" in cypher or query.get("needs_year"):
        query_params["year"] = str(year)
        print(f"   Added year parameter: {year}")
    if entity and entity.get("type") == "buyer_group":
        query_params["names"] = list(dict.fromkeys(entity["members"]))
        print(f"   Added names parameter: {len(query_params['names'])} members")

    # Replace $top_n placeholder (number of top entities to return)
    if "$top_n" in cypher:
        _GREEK_NUMS = {
            "ενα": 1, "ένα": 1, "μία": 1, "μια": 1, "έναν": 1, "εναν": 1,
            "δύο": 2, "δυο": 2,
            "τρεις": 3, "τρία": 3, "τρια": 3,
            "τέσσερεις": 4, "τέσσερα": 4, "τεσσερα": 4,
            "πέντε": 5, "πεντε": 5,
            "έξι": 6, "εξι": 6,
            "επτά": 7, "επτα": 7,
            "οκτώ": 8, "οκτω": 8, "οκτό": 8,
            "εννέα": 9, "εννεα": 9,
            "δέκα": 10, "δεκα": 10,
            "είκοσι": 20, "εικοσι": 20,
        }
        top_n = 1  # default: top 1
        # Try digit first
        m_num = re.search(r'\b(\d+)\b', question)
        if m_num:
            top_n = int(m_num.group(1))
        else:
            # Try Greek number words
            q_lower = question.lower()
            for word, val in _GREEK_NUMS.items():
                if word in q_lower:
                    top_n = val
                    break
        top_n = max(1, min(top_n, 50))  # clamp 1-50
        cypher = cypher.replace("$top_n", str(top_n))
        print(f"   Replaced $top_n with: {top_n}")

    # Replace $procedure placeholder
    if "$procedure" in cypher:
        from utils.procedure_map import PROCEDURE_ALIASES as PROCEDURE_MAP_ALIASES
        from data_access.entity_extractor import detect_procedure_type
        
        q_lower = question.lower()
        procedure_value = None

        # 1) Δοκίμασε τα aliases από procedure_map
        for key, value in PROCEDURE_MAP_ALIASES.items():
            if key.lower() in q_lower:
                procedure_value = value
                break

        # 2) Fallback: detect_procedure_type
        if procedure_value is None:
            detected = detect_procedure_type(question)
            if detected:
                procedure_value = detected

        # 3) SUPERfallback για όλες τις παραλλαγές "απευθείας"
        if procedure_value is None:
            if any(sub in q_lower for sub in ["απευθε", "απευθ", "απευθυ"]):
                procedure_value = "direct award"

        # 4) Default
        if procedure_value is None:
            print(" Δεν εντόπισα τύπο διαδικασίας  default σε direct award")
            procedure_value = "direct award"

        cypher = cypher.replace("$procedure", f'"{procedure_value}"')
        print(f"   Replaced $procedure with: {procedure_value}")            
    
    # Detect output type -  Respect predefined action if present
    from data_access.query_matcher import detect_output_type
    output_type = query.get("action") or detect_output_type(question)
    
    # Force graph if keywords present
    if any(k in question.lower() for k in ["γράφημα", "γραφημα", "γράφου", "γραφου", "graph"]):
        output_type = "graph"

    if output_type == "show_graph": output_type = "graph" # normalize
    if output_type == "show_chart": output_type = "chart" # normalize
    
    print(f"   Output type: {output_type}")
    
    # Safety check: ensure all $params in cypher have matching query_params
    _required = re.findall(r'\$(\w+)', cypher)
    _missing = [p for p in _required if p not in query_params
                and p not in ('name',)]  # $name is string-replaced, not parameterized
    if _missing:
        print(f"   ⚠️  MISSING PARAMS: {_missing} not in query_params {list(query_params.keys())}")
        print(f"   ⚠️  Final cypher: {cypher[:300]}")

    print(f"   QUERY PARAMS: {list(query_params.keys())}")

    # Execute query
    from data_access.database import execute_cypher, extract_graph_elements
    from utils.debug_logger import update_trace
    try:
        results = execute_cypher(cypher, params=query_params)
        update_trace(cypher_executed=cypher, db_results_raw=results)
    except Exception as e:
        print(f" Error executing Cypher or updating trace: {e}")
        results = []
    if output_type == "graph":
        raw_results = execute_cypher(cypher, params=query_params, format_output=False)
        if isinstance(raw_results, list):
            elements = extract_graph_elements(raw_results)
            num_nodes = len(elements.get('nodes', [])) if isinstance(elements, dict) else len(elements)
            print(f"    Graph result: {num_nodes} elements")
            if num_nodes == 0:
                # Friendly fallback when no graph data found
                entity_name = authority_name or "τον φορέα"
                return f"Δεν βρέθηκαν δεδομένα γραφήματος για {entity_name}. Δοκίμασε με διαφορετικό φορέα ή έτος."
            
            # Build a concise spoken summary of the graph
            graph_summary = _summarize_graph_elements(elements, authority_name, year)
            
            # Generate dynamic follow-up suggestions
            suggestions = []
            if authority_name:
                y = year if year else "2023"
                suggestions = [
                    {"label": f"📊 Ραβδόγραμμα με top 10 αναδόχους ({y})", "query": f"δείξε μου σε ραβδόγραμμα τις 10 εταιρείες με τις περισσότερες συμβάσεις για {authority_name} το {y}"},
                    {"label": f"📅 Το ίδιο γράφημα για το {int(y)-1}", "query": question.replace(str(y), str(int(y)-1)) if str(y) in question else f"{question} το {int(y)-1}"},
                    {"label": f"🚧 Απευθείας Αναθέσεις ανά CPV ({y})", "query": f"πόσες απευθείας αναθέσεις έκανε η {authority_name} ανά CPV το {y};"},
                ]
            else:
                suggestions = [
                    {"label": "🏛️ Ποια είναι η αρχή με τις περισσότερες συμβάσεις;", "query": "Ποια είναι η αναθέτουσα αρχή με τις περισσότερες συμβάσεις;"},
                    {"label": "📉 Δείξε ραβδόγραμμα με top αναθέτουσες", "query": "Ραβδόγραμμα με τις 10 αναθέτουσες αρχές με τις περισσότερες απευθείας αναθέσεις"}
                ]
            
            return {
                "action": "show_graph",
                "data": elements,
                "text": graph_summary,
                "suggestions": suggestions
            }
    
    if output_type == "chart":
        raw_results = execute_cypher(cypher, params=query_params, format_output=False)
        if isinstance(raw_results, list):
            print(f"    Chart result: {len(raw_results)} data points")
            return {
                "action": "show_chart",
                "data": raw_results,
                "text": f" {description}"
            }
    
    # Default: text result
    raw_results = execute_cypher(cypher, params=query_params, format_output=False)
    _last_results = raw_results

    # Αν γύρισε string, είναι πιθανότατα μήνυμα λάθους
    if isinstance(raw_results, str):
        print(f"    Text result (raw string): {raw_results}")
        return raw_results

    # ----------------------------------------------------
    #  FAST PATH με χρήση άρθρου από την ερώτηση
    # ----------------------------------------------------
    if (
        isinstance(raw_results, list) and
        len(raw_results) == 1 and
        isinstance(raw_results[0], dict) and
        len(raw_results[0]) == 1
    ):
        row = raw_results[0]
        value = next(iter(row.values()))

        # Εξαγωγή noun phrase
        noun_phrase = None
        if isinstance(description, str) and description.startswith("πόσες "):
            rest = description[len("πόσες "):]
            rest = rest.split(" έχω")[0]
            noun_phrase = rest.strip(" ;?")
        
        if not noun_phrase:
            ql = (question or "").lower()
            if "απευθε" in ql and ("ανάθεσ" in ql or "αναθεσ" in ql):
                noun_phrase = "απευθείας αναθέσεις"
            elif "συμβάσ" in ql or "συμβα" in ql:
                noun_phrase = "συμβάσεις"
            else:
                key = next(iter(row.keys()))
                noun_phrase = str(key).replace("_", " ")
        
        #  Χρήση άρθρου από την ερώτηση του χρήστη
        if entity and authority_name:
            if entity.get("type") == "buyer_group":
                n_members = len(entity.get("members", []))
                sample = entity["members"][:3]
                sample_str = ", ".join(sample)
                if n_members > 3:
                    sample_str += f" ... (+{n_members - 3})"
                answer = (
                    f"**Aggregated entity: {authority_name} "
                    f"({n_members} sub-entities)**\n"
                    f"_{sample_str}_\n\n"
                    f"Συνολικά {value} {noun_phrase}."
                )
            else:
                user_article = extract_article_from_question(question, authority_name)
                if user_article:
                    answer = f"{user_article} {authority_name} έχει {value} {noun_phrase}."
                else:
                    answer = f"Η αναθέτουσα αρχή {authority_name} έχει {value} {noun_phrase}."
        elif noun_phrase:
            answer = f"Βρέθηκαν {value} {noun_phrase}."
        else:
            answer = f"{value}"

        # Τελικό grammar check
        answer = answer.replace("συμβάσσεις", "συμβάσεις")
        
        print(f"    Simple count answer: {answer}")
        return answer
        # ----------------------------------------------------
    # ----------------------------------------------------
    #  TABLE PATH: deterministic formatting για λίστες
    # ----------------------------------------------------
    if isinstance(raw_results, list) and raw_results and all(isinstance(r, dict) for r in raw_results):
        ql = (question or "").lower()

        # default rows
        max_rows = 10

        # αν ο χρήστης ζήτησε "top 5" κ.λπ., σεβάσου το
        m = re.search(r"\b(\d{1,2})\b", ql)
        if m and any(tok in ql for tok in ["top", "κορυφ", "πρώτ", "πρωτ"]):
            max_rows = max(1, min(int(m.group(1)), 50))

        # ειδικά για top ανάδοχοι προτίμησε max_rows=5 αν δεν έδωσε αριθμό
        if ("αναδοχ" in ql or "εταιρ" in ql) and ("top" in ql or "κορυφ" in ql) and not m:
            max_rows = 5

        table_text = _format_table_results(raw_results, max_rows=max_rows)
        if entity and entity.get("type") == "buyer_group":
            n_members = len(entity.get("members", []))
            sample = entity["members"][:3]
            sample_str = ", ".join(sample)
            if n_members > 3:
                sample_str += f" ... (+{n_members - 3})"
            table_text = (
                f"**Aggregated entity: {authority_name} "
                f"({n_members} sub-entities)**\n"
                f"_{sample_str}_\n\n"
                + table_text
            )
        return table_text


    # ----------------------------------------------------
    # SLOW PATH: LLM summariser
    # ----------------------------------------------------
    from ai.llm_interface import summarize_query_result
    summary = summarize_query_result(question, raw_results)
    print(f"    Summary: {str(summary)[:200]}...")
    return summary
# =============================================================================
# HELPER ΓΙΑ ΠΡΟΚΑΘΟΡΙΣΜΕΝΑ QUERIES (AGENT)
# =============================================================================
from typing import Optional, Dict, Tuple

def match_predefined_query(question: str, has_entity: bool) -> Optional[Dict]:
    """
    Μικρό wrapper γύρω από get_query_match ώστε να το χρησιμοποιεί ο agent
    όταν το intent είναι 'data_simple'.
    Επιστρέφει το dict του matched query ή None.
    """
    # Φόρτωσε όλα τα predefined
    queries = get_all_predefined_queries()
    print(f" [agent] Loaded {len(queries)} predefined queries")

    # Χρησιμοποιούμε τον ίδιο matcher, αλλά του λέμε αν υπάρχει αναθέτουσα
    match_result: Optional[Tuple[Dict, float]] = get_query_match(
        question,
        queries,
        has_entity=has_entity,
        threshold=SIMILARITY_THRESHOLD
    )
    if match_result:
        matched_query, score = match_result
        print(
            f" [agent] MATCH FOUND: "
            f"Query ID: {matched_query.get('id')}  Score: {score:.3f}"
        )
        return matched_query

    print(" [agent] No predefined query match found")
    return None

def _handle_no_match(
    question: str,
    entity: Optional[Dict],
    year: str
) -> str:
    """Handle case when no predefined query matches."""
    print(f"[NO MATCH] No predefined query matched for: {question[:60]}...")
    
    # For data queries, don't try LLM generation (it can't access the database reliably)
    # Just return a helpful message
    if entity:
        # Entity was extracted, so it's a data query about a specific authority
        answer = f"[?] Δεν κατάφερα να βρω μια ακριβή απάντηση για την αναθέτουσα αρχή **{entity['value']}** το {year}.\n\nΜπορώ να σας βοηθήσω με:\n- Πόσες συμβάσεις έχει;\n- Ποια είναι η συνολική αξία των συμβάσεών της;\n- Ποιες είναι οι top αναδόχοι της;"
        print(f"[NO MATCH] Returning entity-based fallback message")
        return answer
    else:
        # No entity - generic data question
        answer = "[?] Δεν κατάφερα να βρω μια ακριβή απάντηση. Μπορείτε να:\n- Ζητήσετε σχετικά με μια συγκεκριμένη αναθέτουσα αρχή\n- Ρωτήσετε για στατιστικά (πόσες συμβάσεις, συνολική αξία, κτλ.)\n- Ζητήσετε έκθεση ελέγχου"
        print(f"[NO MATCH] Returning generic fallback message")
        return answer
def _maybe_attach_followup(
    question: str,
    entity: Optional[Dict],
    year: str,
    base_answer: Union[str, Dict[str, Any]],
    intent: str = "",
    skip_followup: bool = False
) -> Union[str, Dict[str, Any]]:
    """
    Προσθέτει follow-up πρόταση στην απάντηση.
    
    ΣΕΙΡΑ ΠΡΟΤΕΡΑΙΟΤΗΤΑΣ:
    1. Predefined follow-ups (instant, no LLM)
    2. LLM-generated follow-ups (αν διαθέσιμο)
    """
    global PENDING_FOLLOWUP
    
    print(f"\n[FOLLOWUP] ========== Checking for follow-up ==========")
    print(f"[FOLLOWUP] Question: {question[:50]}...")
    print(f"[FOLLOWUP] Intent: {intent}")
    if skip_followup:
        return base_answer

    # 1) Πάρε κείμενο της απάντησης
    if isinstance(base_answer, dict):
        text = str(base_answer.get("text", ""))
    else:
        text = str(base_answer)

    if not text.strip():
        print(f"[FOLLOWUP] Empty answer, skipping")
        return base_answer

    print(f"[FOLLOWUP] Base answer (first 100): {text[:100]}...")
    # 2) ΠΡΩΤΑ: predefined follow-up μόνο αν υπάρχει εκτελέσιμο query
    picked = _pick_followup_candidate(question, entity, year)
    if picked:
        prompt_text, query_def = picked
        qid = query_def.get("id")
        print(f"[FOLLOWUP]  Runnable follow-up Q{qid}: {prompt_text}")

        PENDING_FOLLOWUP["active"] = True
        PENDING_FOLLOWUP["query_id"] = qid
        PENDING_FOLLOWUP["question"] = (
            query_def.get("question")
            if isinstance(query_def.get("question"), str)
            else (query_def.get("question") or [""])[0]
        )
        PENDING_FOLLOWUP["entity"] = entity
        PENDING_FOLLOWUP["year"] = year
        prompt_line = f"\n\n{prompt_text}; Πες **ναι** ή κάνε άλλη ερώτηση."
        full_text = text + prompt_line

        if isinstance(base_answer, dict):
            base_answer["text"] = full_text
            return base_answer
        return full_text

    # 3) ΔΕΥΤΕΡΟΝ: Δοκίμασε LLM follow-up
    if intent in ("data_simple", "data_risk"):
        # Για data intents μόνο predefined follow-ups  το LLM δεν ξέρει τα δεδομένα
        print(f"[FOLLOWUP] Skipping LLM for intent={intent}")
        return base_answer

    # LLM follow-up μόνο για general/legal
    print(f"[FOLLOWUP] No predefined match, trying LLM...")
    
    try:
        from ai.llm_interface import generate_followup_question
        follow_q = generate_followup_question(question, text, intent or "data")
        
        if follow_q:
            print(f"[FOLLOWUP]  LLM generated: {follow_q}")
            
            PENDING_FOLLOWUP["active"] = True
            PENDING_FOLLOWUP["question"] = follow_q
            PENDING_FOLLOWUP["entity"] = entity
            PENDING_FOLLOWUP["year"] = year
            prompt_line = (
                f"\n\nΑν θέλεις, μπορώ να ελέγξω: {follow_q} "
                f"Πες ναι ή γράψε κάτι άλλο."
            )
            full_text = text + prompt_line
            
            if isinstance(base_answer, dict):
                base_answer["text"] = full_text
                return base_answer
            return full_text
        else:
            print(f"[FOLLOWUP] LLM returned None")
            
    except Exception as e:
        print(f"[FOLLOWUP] LLM error: {e}")

    # 4) Κανένα follow-up
    print(f"[FOLLOWUP] No follow-up attached")
    return base_answer
# =============================================================================
# UTILITY FUNCTIONS (for backward compatibility)
# =============================================================================
def get_query_ranking(query_id: int, norm_type: str = "robust") -> str:
    """Get ranking results for a specific query type."""
    # Implementation depends on your ranking data structure
    return "Ranking functionality - to be implemented based on your data"

def get_normalized_results(norm_type: str = "robust") -> str:
    """Get normalized ranking results."""
    return "Normalized results - to be implemented based on your data"

def answer_question(question: str, previous: str = "", from_voice: bool = False, role: str = None, web_search_enabled: bool = True) -> Union[str, Dict[str, Any]]:
    return agent_answer(question, previous, from_voice=from_voice, role=role, web_search_enabled=web_search_enabled)

# =============================================================================
# EXPORTS (for server.py compatibility)
# =============================================================================
__all__ = [
    'answer_question',
    'generate_full_audit_report',
    'generate_minimal_audit_report',
    'run_illegal_award_checks_and_export_docx',
    'get_latest_export_path',
    'get_query_ranking',
    'get_normalized_results'
]
