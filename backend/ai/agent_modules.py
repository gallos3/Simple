from typing import Any, Dict, List, Optional, Generator
import re
from ai.llm_interface import get_llm, stream_llm

# =============================================================================
# CONSTANTS
# =============================================================================

MAX_CONTEXT = 500
TEMPERATURE = 0.1

# =============================================================================
# HELPERS
# =============================================================================

def _extract_law_number(text: str) -> Optional[str]:
    patterns = [
        r'ν\.?\s*(\d{4})',
        r'νόμο[ςυ]?\s*(\d{4})',
        r'Ν\.?\s*(\d{4})',
        r'\b(\d{4})/\d{2,4}\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def _truncate_context(text: str, max_chars: int = MAX_CONTEXT) -> str:
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    last_period = truncated.rfind('.')

    if last_period > max_chars * 0.5:
        return truncated[:last_period + 1]

    return truncated


def _ensure_complete(text: str) -> str:
    text = text.strip()

    last = max(
        text.rfind("."),
        text.rfind("?"),
        text.rfind("!")
    )

    if last != -1:
        return text[:last + 1]

    return text

# =============================================================================
# LEGAL ANSWER
# =============================================================================

def generate_legal_answer_stream(
    question: str,
    legal_passages: List[str]
) -> Generator[str, None, None]:

    context = "\n\n".join(legal_passages)
    context = _truncate_context(context)

    law_number = _extract_law_number(question) or "Άγνωστος"

    system_prompt = f"""
Είσαι ΑΥΣΤΗΡΟΣ νομικός ελεγκτής δημοσίων συμβάσεων.

Αναφερόμενος νόμος: {law_number}

Βασίσου ΑΠΟΚΛΕΙΣΤΙΚΑ στο παρακάτω κείμενο.
Αν δεν προκύπτει απάντηση, πες:
«Δεν προκύπτει από τη διαθέσιμη νομοθεσία.»

ΑΠΑΓΟΡΕΥΕΤΑΙ:
- συμβουλές
- ανάλυση
- παραδείγματα

ΜΟΝΟ τελική απάντηση (1–2 προτάσεις).

ΝΟΜΟΘΕΣΙΑ:
{context}
"""

    prompt = f"""
ΕΡΩΤΗΣΗ:
{question}
"""

    for token in stream_llm(
        prompt=prompt,
        max_tokens=180,
        temperature=0.1,
        system_prompt=system_prompt
    ):
        yield token

def generate_legal_answer(question: str, legal_passages: List[str]) -> str:
    chunks = list(generate_legal_answer_stream(question, legal_passages))
    text = "".join(chunks)
    return _ensure_complete(text)

# =============================================================================
# DATA RISK
# =============================================================================

def generate_data_risk_answer_stream(
    question: str,
    authority: str,
    year: Optional[str],
    compliance: Dict[int, List[Dict]]
) -> Generator[str, None, None]:

    llm = get_llm()

    system_prompt = f"""
Είσαι ελεγκτής δημοσίων συμβάσεων.

Φορέας: {authority}
Έτος: {year}

Απάντησε ΑΥΣΤΗΡΑ σε 2 ολοκληρωμένες προτάσεις:
- Εκτίμηση κινδύνου κατάτμησης
- Μόνο τελικό συμπέρασμα

Χωρίς ανάλυση, χωρίς παραδείγματα.
"""

    response = llm.stream([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question}
    ])

    for chunk in response:
        if hasattr(chunk, "content") and chunk.content:
            yield chunk.content


def generate_data_risk_answer(
    question: str,
    authority: str,
    year: Optional[str],
    compliance: Dict[int, List[Dict]]
) -> str:
    chunks = list(generate_data_risk_answer_stream(question, authority, year, compliance))
    text = "".join(chunks)
    return _ensure_complete(text)

# =============================================================================
# MIXED AUDIT (LAW + DATA)
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

    llm = get_llm()

    context = "\n\n".join(legal_passages)
    context = _truncate_context(context)

    summary = build_compliance_summary(authority, year, compliance)
    summary_text = summary.get("summary", "")

    system_prompt = f"""
Είσαι ΑΥΣΤΗΡΟΣ ελεγκτής.

Συνδύασε:
- Νομοθεσία
- Δεδομένα φορέα

Φορέας: {authority}
Έτος: {year}

ΣΥΝΟΨΗ ΔΕΔΟΜΕΝΩΝ:
{summary_text}

ΝΟΜΟΘΕΣΙΑ:
{context}

Απάντησε με 1–2 σύντομες προτάσεις.
Χωρίς ανάλυση, χωρίς παραδείγματα.
"""

    response = llm.stream([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question}
    ])

    for chunk in response:
        if hasattr(chunk, "content") and chunk.content:
            yield chunk.content


def generate_mixed_audit_answer(
    question: str,
    authority: str,
    year: Optional[str],
    compliance: Dict[int, List[Dict]],
    legal_passages: List[str],
    diag_data: Dict
) -> str:
    chunks = list(generate_mixed_audit_answer_stream(
        question, authority, year, compliance, legal_passages, diag_data
    ))
    text = "".join(chunks)
    return _ensure_complete(text)

# =============================================================================
# COMPLIANCE SUMMARY (MINIMAL SAFE VERSION)
# =============================================================================

def _to_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(str(value).replace(".", "").replace(",", "."))
    except:
        return 0.0


def build_compliance_summary(
    authority: str,
    year: Optional[str],
    compliance: Dict[int, List[Dict]]
) -> Dict[str, Any]:

    total = 0.0
    count = 0

    for _, rows in compliance.items():
        for r in rows:
            amount = _to_float(r.get("ποσό") or r.get("amount"))
            total += amount
            count += 1

    return {
        "summary": f"{count} συμβάσεις, συνολικό ποσό {total:.2f} ευρώ."
    }