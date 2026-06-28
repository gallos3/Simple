"""
Simple - Agent Modules (FIXED v2)

Fixes:
- max_tokens: 100 → 150 (αρκετά για 2 ολοκληρωμένες προτάσεις)
- Εξαγωγή αριθμού νόμου από ερώτηση → στο prompt
- Καλύτερο post-processing για ολοκληρωμένες προτάσεις
"""

from typing import Any, Dict, List, Optional, Generator
import re
from ai.llm_interface import get_llm


# =============================================================================
# CONSTANTS
# =============================================================================
MAX_TOKENS = 120          # Αυξημένο για ολοκληρωμένες προτάσεις
MAX_CONTEXT = 500
TEMPERATURE = 0.1


# =============================================================================
# HELPERS
# =============================================================================
def _extract_law_number(text: str) -> Optional[str]:
    """
    Εξάγει αριθμό νόμου από κείμενο.
    π.χ. "ν.5164" → "5164", "νόμος 4412" → "4412"
    """
    patterns = [
        r'ν\.?\s*(\d{4})',           # ν.5164, ν 5164
        r'νόμο[ςυ]?\s*(\d{4})',      # νόμος 5164, νόμου 5164
        r'Ν\.?\s*(\d{4})',           # Ν.5164
        r'\b(\d{4})/\d{2,4}\b',      # 5164/24
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def _truncate_context(text: str, max_chars: int = MAX_CONTEXT) -> str:
    """Κόβει context σε τέλος πρότασης."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_period = truncated.rfind('.')
    if last_period > max_chars * 0.5:
        return truncated[:last_period + 1]
    return truncated


def _ensure_complete(text: str) -> str:
    """
    Διασφαλίζει ολοκληρωμένες προτάσεις.
    Κόβει στην ΤΕΛΕΥΤΑΙΑ τελεία/ερωτηματικό.
    """
    text = text.strip()
    
    # Αφαίρεση artifacts
    text = re.sub(r'^\s*(Απάντηση|Συμπέρασμα)\s*[:\-]\s*', '', text, flags=re.I)
    text = re.sub(r'^\s*\d+[\.\)]\s*', '', text)
    
    # Αν τελειώνει σωστά, OK
    if text and text[-1] in '.!?':
        return text
    
    # Βρες την τελευταία τελεία
    last_period = text.rfind('.')
    last_question = text.rfind('?')
    last_exclaim = text.rfind('!')
    
    cut_point = max(last_period, last_question, last_exclaim)
    
    if cut_point > len(text) * 0.3:  # Αν είναι αρκετά μέσα στο κείμενο
        return text[:cut_point + 1]
    
    # Fallback: πρόσθεσε τελεία
    text = text.rstrip(',;:- ')
    return text + '.' if text else text


# =============================================================================
# LEGAL ANSWER - STREAMING
# =============================================================================
# =============================================================================
# LEGAL ANSWER - STREAMING
# =============================================================================
def generate_legal_answer_stream(
    question: str, 
    legal_passages: List[str]
) -> Generator[str, None, None]:
    """
    Νομική απάντηση με streaming και αυστηρή τεκμηρίωση.
    Χρησιμοποιεί chat format για να μην μπερδεύει τις οδηγίες.
    """
    llm = get_llm()
    
    if not llm:
        yield "Το LLM δεν είναι διαθέσιμο."
        return

    if not legal_passages:
        yield "Δεν βρέθηκαν σχετικά αποσπάσματα νομοθεσίας ή νομολογίας."
        return

    # Combine top 2 passages to ensure we get substantial context, not just one snippet
    top_passages = legal_passages[:2]
    combined_context = "\n---\n".join(top_passages)
    # Increase context significantly (Llama 3 has 4096 token limit, 5000 chars is safe)
    context = _truncate_context(combined_context, max_chars=5000)
    
    law_num = _extract_law_number(question)
    law_hint = f"Αναφέρσου στον νόμο {law_num} αν υπάρχει. " if law_num else ""

    system_prompt = f"""Είσαι ΑΥΣΤΗΡΟΣ νομικός ελεγκτής δημοσίων συμβάσεων.
Βασίσου ΑΠΟΚΛΕΙΣΤΙΚΑ στο παρακάτω νομοθετικό κείμενο.
Αν το κείμενο δεν περιέχει την απάντηση, πες: «Δεν προκύπτει από τη διαθέσιμη νομοθεσία.»
ΑΠΑΓΟΡΕΥΕΤΑΙ ΝΑ:
- Δώσεις συμβουλές, οδηγίες ή προτάσεις.
- Προσθέσεις δικά σου παραδείγματα, σενάρια ή λίστες.
- Συνεχίσεις να γράφεις αφού δώσεις την απάντηση.
ΠΡΕΠΕΙ να είσαι απολύτως τηλεγραφικός: Δώσε ΜΟΝΟ την τελική νομική απάντηση (1 έως 2 μικρές προτάσεις το πολύ).

ΝΟΜΟΘΕΣΙΑ/ΝΟΜΟΛΟΓΙΑ:
{context}"""

    # Chat Template format for Llama models
    prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\nΕΡΩΤΗΣΗ: {question}\n{law_hint}<|im_end|>\n<|im_start|>assistant\n"

    try:
        for chunk in llm(
            prompt,
            max_tokens=120,
            temperature=0.0,
            stop=["<|im_end|>", "ΕΡΩΤΗΣΗ:", "user", "assistant", "Οι προτάσεις", "1.", "\n\n"],
            stream=True
        ):
            token = chunk["choices"][0]["text"]
            if token:
                yield token
                
    except Exception as e:
        print(f"[agent] streaming error: {e}", flush=True)
        yield "Σφάλμα κατά την επεξεργασία της νομικής απάντησης."



def generate_legal_answer(question: str, legal_passages: List[str]) -> str:
    """Non-streaming version."""
    chunks = list(generate_legal_answer_stream(question, legal_passages))
    text = "".join(chunks)
    return _ensure_complete(text)


# =============================================================================
# DATA RISK - STREAMING
# =============================================================================
def generate_data_risk_answer_stream(
    question: str,
    authority: str,
    year: Optional[str],
    compliance: Dict[int, List[Dict]]
) -> Generator[str, None, None]:
    """Risk analysis με streaming."""
    
    llm = get_llm()
    summary = build_compliance_summary(authority, year, compliance)
    s = summary["over_limit_summary"]
    
    if not llm:
        if s["total_cases"] == 0:
            yield f"Για «{authority}» δεν εντοπίστηκαν υπερβάσεις ορίων."
        else:
            yield f"Για «{authority}» εντοπίστηκαν {s['total_cases']} υπερβάσεις."
        return

    data = f"Υπερβάσεις: {s['total_cases']}, Ποσό: {s['total_amount']:,.0f}€"

    prompt = f"""Ελεγκτής δημοσίων συμβάσεων.

Φορέας: {authority}
Στοιχεία: {data}

Απάντησε σε 2 ΟΛΟΚΛΗΡΩΜΕΝΕΣ προτάσεις για κίνδυνο κατάτμησης. Κάθε πρόταση με τελεία.

Απάντηση:"""

    try:
        for chunk in llm(
            prompt,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            stop=["\n\n", "Φορέας:"],
            stream=True
        ):
            token = chunk["choices"][0]["text"]
            if token:
                yield token

    except Exception as e:
        yield f"Για «{authority}» απαιτείται περαιτέρω έλεγχος."


def generate_data_risk_answer(
    question: str,
    authority: str,
    year: Optional[str],
    compliance: Dict[int, List[Dict]]
) -> str:
    """Non-streaming version."""
    chunks = list(generate_data_risk_answer_stream(question, authority, year, compliance))
    text = "".join(chunks)
    return _ensure_complete(text)


# =============================================================================
# MIXED AUDIT - STREAMING
# =============================================================================
def generate_mixed_audit_answer_stream(
    question: str,
    authority: str,
    year: Optional[str],
    compliance: Dict[int, List[Dict]],
    legal_passages: List[str],
    diag_data: Dict,
    diagnosis_text: str = ""
) -> Generator[str, None, None]:
    """
    Advanced Hybrid Reasoning: Matches Law (RAG) with Facts (Graph).
    """
    llm = get_llm()
    summary = build_compliance_summary(authority, year, compliance)
    s = summary["over_limit_summary"]

    if not llm:
        yield f"⚠️ Για «{authority}» εντοπίστηκαν {s['total_cases']} πιθανές υπερβάσεις."
        return

    # Yield only the pre-calculated diagnosis sections (ends at Προτεινόμενη Θεραπεία)
    # The ΝΟΜΙΚΗ ΕΚΤΙΜΗΣΗ section has been removed intentionally.
    yield diagnosis_text


def generate_mixed_audit_answer(
    question: str,
    authority: str,
    year: Optional[str],
    compliance: Dict[int, List[Dict]],
    legal_passages: List[str],
    diag_data: Dict
) -> str:
    """Non-streaming version."""
    chunks = list(generate_mixed_audit_answer_stream(
        question, authority, year, compliance, legal_passages, diag_data, ""
    ))
    text = "".join(chunks)
    return _ensure_complete(text)


# =============================================================================
# COMPLIANCE SUMMARY
# =============================================================================
def _to_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(str(value).replace(".", "").replace(",", "."))
    except:
        return 0.0


def _filter_by_authority(rows: Optional[List[Dict]], authority: str) -> List[Dict]:
    if not rows:
        return []
    want = authority.lower()
    out = []
    for r in rows:
        name = r.get("Αναθέτουσα_Αρχή") or r.get("αναθέτουσα_αρχή")
        if name is None:
            continue
        ns = str(name).lower()
        if want in ns or ns in want or ns == want:
            out.append(r)
    return out


def build_compliance_summary(
    authority: str,
    year: Optional[str],
    compliance: Dict[int, List[Dict]]
) -> Dict[str, Any]:
    """Builds compliance summary."""
    
    over_30 = _filter_by_authority(compliance.get(101), authority)
    over_60 = _filter_by_authority(compliance.get(102), authority)
    cpv_30 = _filter_by_authority(compliance.get(103), authority)
    cpv_60 = _filter_by_authority(compliance.get(104), authority)
    cpv5_30 = _filter_by_authority(compliance.get(105), authority)
    cpv5_60 = _filter_by_authority(compliance.get(106), authority)
    contractor_30 = _filter_by_authority(compliance.get(107), authority)
    contractor_60 = _filter_by_authority(compliance.get(108), authority)

    over_cases = over_30 + over_60
    
    return {
        "authority": authority,
        "year": year,
        "over_limit_summary": {
            "total_cases": len(over_cases),
            "total_amount": sum(_to_float(r.get("Ποσό", 0)) for r in over_cases),
        },
        "over_limit_cases": over_cases,
        "cpv_over_limit": cpv_30 + cpv_60,
        "cpv_class_over_limit": cpv5_30 + cpv5_60,
        "contractor_over_limit": contractor_30 + contractor_60,
    }
