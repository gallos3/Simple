# =====================================================================
# Simple - LLM Interface
# Backend: llama-cpp-python
# Model: Qwen2.5-3B-Instruct Q4_K_M
# =====================================================================

import json
from typing import Optional, Generator, Any
from llama_cpp import Llama

from config import MODEL_PATH

# -----------------------------------------------------------
# MODEL INIT
# -----------------------------------------------------------

_llm_instance = None

def get_llm() -> Llama:
    """Lazy-load the LLM to prevent startup stdout conflicts with Flask/colorama"""
    global _llm_instance
    if _llm_instance is None:
        print("[LLM] Initializing Llama-cpp (Lazy Load)...", flush=True)
        _llm_instance = Llama(
            model_path=MODEL_PATH,
            n_ctx=4096,
            n_threads=6,      # Ryzen 5700U - 8 threads, κράτα 6 για το σύστημα
            n_gpu_layers=0,   # Integrated GPU - όλα στη CPU
            verbose=False
        )
    return _llm_instance

# -----------------------------------------------------------
# HYBRID STRICT SYSTEM PROMPT
# -----------------------------------------------------------
HYBRID_SYSTEM_PROMPT = """Είσαι υβριδικός agent με δύο ιδιότητες:

(Α) ΝΟΜΙΚΟΣ ΕΜΠΕΙΡΟΓΝΩΜΟΝΑΣ (ύφος ΣτΕ / ΕΑΑΔΗΣΥ):
- Απολύτως ακριβής στα νομικά θέματα.
- Δεν επινοείς νόμους, άρθρα, ΦΕΚ ή ημερομηνίες.
- Αν κάτι δεν προκύπτει από επίσημες πηγές, δηλώνεις: «Δεν προκύπτει από διαθέσιμες πηγές».

(Β) ΕΚΠΑΙΔΕΥΤΗΣ / ΚΑΘΗΓΗΤΗΣ (για σενάρια προσομοίωσης):
- Όταν ο χρήστης ζητά «σενάριο», «εκπαίδευση» ή «άσκηση», λειτουργείς ως Καθηγητής.
- Σε αυτή την κατάσταση, ΔΗΜΙΟΥΡΓΕΙΣ ρεαλιστικά σενάρια βασισμένα στο νομικό πλαίσιο (Ν.4412/2016) για εκπαιδευτικούς σκοπούς.
- Τα σενάρια πρέπει να είναι προκλητικά και να περιέχουν διλήμματα.

ΓΕΝΙΚΟΙ ΚΑΝΟΝΕΣ:
1. Μη δίνεις τη λύση αμέσως στα σενάρια. Ρώτα τον φοιτητή.
2. Απαντάς πάντα σε άρτια ελληνικά.
3. Όταν λείπουν δεδομένα για ΠΡΑΓΜΑΤΙΚΕΣ υποθέσεις λες «Απαιτείται διευκρίνιση»."""

STOP_SEQUENCES = ["###", "Ερώτηση:", "ΑΠΑΝΤΗΣΗ:", "<|im_end|>"]

# -----------------------------------------------------------
# ΒΟΗΘΗΤΙΚΗ ΣΥΝΑΡΤΗΣΗ ΓΙΑ ΠΛΗΡΗ ΠΡΟΤΑΣΗ
# -----------------------------------------------------------
def ensure_sentence(t: str) -> str:
    if not t:
        return t
    t = t.strip()
    if t.endswith(('.', ';', '?', '!')):
        return t
    return t + '.'

# -----------------------------------------------------------
# ΒΑΣΙΚΗ ΚΛΗΣΗ LLM
# -----------------------------------------------------------
def call_llm(prompt: str, max_tokens: int = 256, temperature: float = 0.0, system_prompt: str = None) -> str:
    try:
        sys_p = system_prompt or HYBRID_SYSTEM_PROMPT
        full_prompt = f"<|im_start|>system\n{sys_p}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
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

def call_llm_json(prompt: str, max_tokens: int = 512, temperature: float = 0.1, system_prompt: str = None, retries: int = 3) -> str:
    """
    Calls the LLM and ensures the output is a valid JSON string.
    Useful for scoring and structured reports.
    """
    sys_p = system_prompt if system_prompt else HYBRID_SYSTEM_PROMPT
    sys_p += "\nIMPORTANT: You must return valid JSON only. No markdown formatting, no explanations."
    
    for attempt in range(retries):
        try:
            full_prompt = f"<|im_start|>system\n{sys_p}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
            resp = get_llm()(
                full_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=STOP_SEQUENCES,
            )
            text = resp["choices"][0]["text"].strip()
            
            # Attempt to parse to ensure it's valid JSON
            if "{" in text and "}" in text:
                start = text.index("{")
                end = text.rindex("}") + 1
                json_str = text[start:end]
                json.loads(json_str)  # Verify validity
                return json_str
            else:
                raise ValueError("No JSON object found in output.")
                
        except Exception as e:
            print(f"[LLM JSON Error - Attempt {attempt+1}/{retries}]: {e}")
            if attempt == retries - 1:
                return "{}"
    return "{}"

# -----------------------------------------------------------
# STREAMING
# -----------------------------------------------------------
def stream_llm(prompt: str, max_tokens: int = 256, temperature: float = 0.0, system_prompt: str = None) -> Generator:
    try:
        sys_p = system_prompt or HYBRID_SYSTEM_PROMPT
        full_prompt = f"<|im_start|>system\n{sys_p}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
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
        print("\n[LLM] Stream complete.", flush=True)
    except Exception as e:
        print(f"\n[LLM] Streaming Error: {e}")
        yield f"[Streaming Error: {e}]"

# -----------------------------------------------------------
# SCHEMA ΓΙΑ CYPHER (διατηρείται για backwards compatibility)
# -----------------------------------------------------------
SCHEMA = """
Nodes:
- Authority(name)
- Company(name)
- Contract(id,title,initial_value,final_value,signed_date)
- ProcedureType(description)
- CPV(code,description)
- NUTS(code,description)

Rels:
- (Authority)-[:AWARDS]->(Contract)
- (Company)-[:WON_BY]->(Contract)
- (Contract)-[:OF_TYPE]->(ProcedureType)
- (Contract)-[:HAS_CPV]->(CPV)
- (Contract)-[:IN_REGION]->(NUTS)
"""

# -----------------------------------------------------------
# CYPHER GENERATION - ΔΕΝ ΧΡΗΣΙΜΟΠΟΙΕΙΤΑΙ (predefined queries)
# Διατηρείται μόνο για backwards compatibility με engine.py
# -----------------------------------------------------------
def generate_cypher_query(question: str) -> str:
    return ""   # Επιστρέφει κενό — το engine πέφτει στο fallback

# -----------------------------------------------------------
# LEGAL RAG RESPONSE
# -----------------------------------------------------------
def generate_legal_answer(question: str, passages: list) -> str:
    context = passages[0][:600] if passages else "(κανένα διαθέσιμο απόσπασμα)"
    prompt = f"""Απάντησε ΜΟΝΟ βάσει του αποσπάσματος. Όχι επινοήσεις νόμων ή άρθρων.

ΑΠΟΣΠΑΣΜΑ:
{context}

ΕΡΩΤΗΣΗ:
{question}"""
    return call_llm(prompt, 200)

# -----------------------------------------------------------
# SUMMARY
# -----------------------------------------------------------
def summarize_query_result(question: str, results: Any) -> str:
    if isinstance(results, str):
        return results
    if not results:
        return "Δεν βρέθηκαν αποτελέσματα."

    subset = json.dumps(results[:5], ensure_ascii=False)
    prompt = f"""Σύνθεση 1–2 προτάσεων, καθαρή και διοικητική.

Ερώτηση: {question}
Δεδομένα: {subset}"""
    return call_llm(prompt, 150)

# -----------------------------------------------------------
# GENERAL Q/A
# -----------------------------------------------------------
def answer_general_question(question: str) -> str:
    prompt = f"Ερώτηση: {question}\n\nΑπάντηση (χωρίς επινοήσεις):"
    system_prompt = "Είσαι βοηθός για τις δημόσιες συμβάσεις. Απάντησε με ακρίβεια και συντομία. Δεν επινοείς δεδομένα."
    return call_llm(prompt, 200, system_prompt=system_prompt)

def answer_general_question_stream(question: str) -> Generator:
    system_prompt = "Είσαι βοηθός για τις δημόσιες συμβάσεις. Απάντησε με ακρίβεια και συντομία. Δεν επινοείς δεδομένα."
    return stream_llm(f"Απάντησε χωρίς επινοήσεις:\n{question}", 200, system_prompt=system_prompt)

# -----------------------------------------------------------
# FOLLOW-UP SUGGESTION
# -----------------------------------------------------------
def generate_followup_question(user_q: str, base_answer: str, intent: str) -> Optional[str]:
    prompt = f"""Διατύπωσε ΜΙΑ σύντομη, λογική επόμενη ερώτηση, χωρίς επινοήσεις.

Ερώτηση χρήστη: {user_q}
Απάντηση: {base_answer}

Επόμενη ερώτηση:"""
    t = call_llm(prompt, 60)
    t = t.strip()
    return t if len(t) > 2 else None

# -----------------------------------------------------------
# BACKWARDS COMPATIBILITY
# -----------------------------------------------------------
    return get_llm()
