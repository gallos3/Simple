# =====================================================================
# Simple - LLM Interface
# Backend: llama-cpp-python
# Model: Qwen2.5-3B-Instruct Q4_K_M
# =====================================================================

import json
from typing import Optional, Generator, Any
from llama_cpp import Llama
from utils.config import MODEL_PATH

# -----------------------------------------------------------
# MODEL INIT
# -----------------------------------------------------------

_llm_instance = None

def get_llm() -> Llama:
    """Lazy-load the LLM"""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = Llama(
            model_path=MODEL_PATH,
            n_ctx=4096,
            n_threads=6,
            n_gpu_layers=0,
            verbose=False
        )
    return _llm_instance

# -----------------------------------------------------------
# SYSTEM PROMPT
# -----------------------------------------------------------

HYBRID_SYSTEM_PROMPT = """Είσαι υβριδικός agent με δύο ιδιότητες:
(Α) ΝΟΜΙΚΟΣ ΕΜΠΕΙΡΟΓΝΩΜΟΝΑΣ:
- Δεν επινοείς νόμους ή στοιχεία
- Αν δεν προκύπτει: «Δεν προκύπτει από διαθέσιμες πηγές»

(Β) ΕΚΠΑΙΔΕΥΤΗΣ:
- Δημιουργείς σενάρια μόνο όταν ζητηθεί

ΓΕΝΙΚΑ:
- Απαντάς σε σωστά ελληνικά
"""

STOP_SEQUENCES = ["###", "Ερώτηση:", "ΑΠΑΝΤΗΣΗ:", "<im_end>"]

# -----------------------------------------------------------
# HELPER
# -----------------------------------------------------------

def ensure_sentence(t: str) -> str:
    if not t:
        return t
    t = t.strip()
    if t.endswith(('.', ';', '?', '!')):
        return t
    return t + '.'

# -----------------------------------------------------------
# CORE CALL
# -----------------------------------------------------------

def call_llm(prompt: str, max_tokens: int = 256, temperature: float = 0.0, system_prompt: str = None) -> str:
    try:
        sys_p = system_prompt or HYBRID_SYSTEM_PROMPT

        full_prompt = f"""<|im_start|>system
{sys_p}
<|im_end|>
<|im_start|>user
{prompt}
<|im_end|>
<|im_start|>assistant
"""

        resp = get_llm()(
            full_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=STOP_SEQUENCES,
        )

        text = resp["choices"][0]["text"].strip()
        return ensure_sentence(text)

    except Exception as e:
        return f"[LLM Error: {e}]"

# -----------------------------------------------------------
# STREAMING
# -----------------------------------------------------------

def stream_llm(prompt: str, max_tokens: int = 256, temperature: float = 0.0, system_prompt: str = None) -> Generator:
    try:
        sys_p = system_prompt or HYBRID_SYSTEM_PROMPT

        full_prompt = f"""<|im_start|>system
{sys_p}
<|im_end|>
<|im_start|>user
{prompt}
<|im_end|>
<|im_start|>assistant
"""

        stream = get_llm()(
            full_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=STOP_SEQUENCES,
            stream=True
        )

        for chunk in stream:
            token = chunk["choices"][0]["text"]
            if token:
                yield token

    except Exception as e:
        yield f"[Streaming Error: {e}]"

# -----------------------------------------------------------
# SIMPLE HELPERS (fixed syntax only)
# -----------------------------------------------------------

def generate_legal_answer(question: str, passages: list) -> str:
    context = passages[0][:600] if passages else "(κανένα διαθέσιμο απόσπασμα)"
    prompt = f"""
Απάντησε ΜΟΝΟ βάσει του αποσπάσματος.

ΑΠΟΣΠΑΣΜΑ:
{context}

ΕΡΩΤΗΣΗ:
{question}
"""
    return call_llm(prompt, 200)


def summarize_query_result(question: str, results: Any) -> str:
    if isinstance(results, str):
        return results
    if not results:
        return "Δεν βρέθηκαν αποτελέσματα."

    prompt = f"""
Ερώτηση:
{question}

Δεδομένα:
{results}
"""
    return call_llm(prompt, 150)


def answer_general_question(question: str) -> str:
    prompt = f"""
Ερώτηση:
{question}

Απάντηση (χωρίς επινοήσεις):
"""
    system_prompt = "Απάντησε με ακρίβεια και χωρίς επινοήσεις."
    return call_llm(prompt, 200, system_prompt=system_prompt)


def answer_general_question_stream(question: str) -> Generator:
    system_prompt = "Απάντησε με ακρίβεια και χωρίς επινοήσεις."
    return stream_llm(f"Ερώτηση:\n{question}", 200, system_prompt=system_prompt)


def generate_followup_question(user_q: str, base_answer: str, intent: str) -> Optional[str]:
    prompt = f"""
Διατύπωσε ΜΙΑ σύντομη επόμενη ερώτηση.

Ερώτηση χρήστη:
{user_q}

Απάντηση:
{base_answer}

Επόμενη ερώτηση:
"""
    t = call_llm(prompt, 60)
    t = t.strip()
    return t if len(t) > 2 else None

# -----------------------------------------------------------
# CYPHER GENERATION - BACKWARDS COMPATIBILITY
# -----------------------------------------------------------

SCHEMA = """
Nodes:
- LegalEntity(name)
- Buyer(name)
- Winner(name)
- Award(id,title,original_id,value,submission_date,cpv_code)

Rels:
- (LegalEntity)<-[BELLONGS_TO]-(Buyer)-[:AWARDS]->(Award)-[:WON_BY]->(Winner)

Note: CPV is stored directly on Award as: award.cpv_code
"""

def generate_cypher_query(question: str) -> str:
    return ""