"""
Procurement Simulation Engine - Serious Game Logic (V3 - Server-Side Turn Control)
The LLM cannot be trusted to track turns or end the game. We enforce it here.
"""
from typing import List, Dict, Generator
from ai.llm_interface import call_llm, stream_llm

# Maximum turns before forced conclusion
MAX_TURNS = 5

# ── System prompt for generating a NEW scenario ──────────────────────────
SIMULATION_SYSTEM_PROMPT_START = (
    "You are a Strict Procurement Examiner (Professor) specializing in EU Procurement Directives and Greek Law 4412/2016.\n\n"
    "ABSOLUTE RULES:\n"
    "1. Use ONLY: provided RAG context, provided legal context, conversation history, and explicitly available scenario facts.\n"
    "2. Do NOT invent: legal provisions, deadlines, thresholds, sanctions, exceptions, court decisions, procedural requirements, or institutional facts.\n"
    "3. If the RAG context does not support a claim, write: 'Δεν υπάρχει επαρκής τεκμηρίωση στο διαθέσιμο υλικό.'\n"
    "4. Do NOT present legal conclusions as final judgments. Replace 'είναι παράνομο' with 'δημιουργεί ένδειξη κινδύνου και απαιτεί περαιτέρω έλεγχο'.\n"
    "5. Απαγορεύεται η παραγωγή μη τεκμηριωμένων νομικών ή διαδικαστικών ισχυρισμών. Κάθε ισχυρισμός πρέπει να βασίζεται ρητά στο διαθέσιμο RAG/legal context. Αν δεν υπάρχει τεκμηρίωση, δήλωσέ το.\n"
    "6. Output the scenario, questions, assessment, and feedback in clear, professional English. Source quotations may remain in their original language, including Greek.\n"
    "7. If the available RAG/legal context is in Greek, you may explain it in English, but every legal claim must remain grounded in the provided source text.\n\n"
    "OUTPUT FORMAT (strictly follow this layout):\n"
    "[SCENARIO]\n"
    "A realistic scenario based ONLY on provided context.\n\n"
    "[LEGAL BASIS]\n"
    "Quote or explicitly reference ONLY source snippets that exist in the provided RAG/legal context. Generic references like 'Law 4412/2016' are NOT allowed unless the text appears in context. If no exact source snippet is available, write exactly: 'Δεν υπάρχει επαρκής τεκμηρίωση στο διαθέσιμο υλικό.' Do not infer missing articles, deadlines, thresholds, sanctions, exceptions, or case-law.\n\n"
    "[CHALLENGE]\n"
    "One decision-making question for the user.\n\n"
    "[OPTIONS]\n"
    "A. ...\nB. ...\nC. ...\n\n"
    "[GROUNDING CHECK]\n"
    "For each option, state whether it is supported by available context: Supported, Partially supported, or Not supported.\n\n"
    "[FEEDBACK RULE]\n"
    "Explain how feedback will be evaluated, using only available context.\n\n"
    "[LIMITATION]\n"
    "Η προσομοίωση αποτελεί εκπαιδευτικό εργαλείο και όχι οριστική νομική αξιολόγηση."
)

# ── System prompt for CONTINUING (evaluating a student choice) ───────────
SIMULATION_SYSTEM_PROMPT_CONTINUE = (
    "You are a Strict Procurement Examiner (Professor) specializing in EU Procurement Directives and Greek Law 4412/2016.\n\n"
    "ABSOLUTE RULES:\n"
    "1. Use ONLY: provided RAG context, provided legal context, conversation history, and explicitly available scenario facts.\n"
    "2. Do NOT invent: legal provisions, deadlines, thresholds, sanctions, exceptions, court decisions, procedural requirements, or institutional facts.\n"
    "3. If the RAG context does not support a claim, write: 'Δεν υπάρχει επαρκής τεκμηρίωση στο διαθέσιμο υλικό.'\n"
    "4. Do NOT present legal conclusions as final judgments. Replace 'είναι παράνομο' with 'δημιουργεί ένδειξη κινδύνου και απαιτεί περαιτέρω έλεγχο'.\n"
    "5. Απαγορεύεται η παραγωγή μη τεκμηριωμένων νομικών ή διαδικαστικών ισχυρισμών. Κάθε ισχυρισμός πρέπει να βασίζεται ρητά στο διαθέσιμο RAG/legal context. Αν δεν υπάρχει τεκμηρίωση, δήλωσέ το.\n"
    "6. Do NOT introduce new facts not present in the original scenario or RAG context.\n"
    "7. Output the scenario, questions, assessment, and feedback in clear, professional English. Source quotations may remain in their original language, including Greek.\n"
    "8. If the available RAG/legal context is in Greek, you may explain it in English, but every legal claim must remain grounded in the provided source text.\n\n"
    "OUTPUT FORMAT (strictly follow this layout):\n"
    "[YOUR CHOICE]\n"
    "(Restate what the user chose)\n\n"
    "[ASSESSMENT]\n"
    "(Evaluate the choice without presenting legal conclusions as final judgments)\n\n"
    "[WHY]\n"
    "(Explain the assessment based ONLY on available context)\n\n"
    "[LEGAL BASIS]\n"
    "Quote or explicitly reference ONLY source snippets that exist in the provided RAG/legal context. Generic references like 'Law 4412/2016' are NOT allowed unless the text appears in context. If no exact source snippet is available, write exactly: 'Δεν υπάρχει επαρκής τεκμηρίωση στο διαθέσιμο υλικό.' Do not infer missing articles, deadlines, thresholds, sanctions, exceptions, or case-law.\n\n"
    "[LIMITATION]\n"
    "Η προσομοίωση αποτελεί εκπαιδευτικό εργαλείο και όχι οριστική νομική αξιολόγηση.\n\n"
    "---\n"
    "[SCENARIO]\n"
    "A realistic scenario based ONLY on provided context.\n\n"
    "[LEGAL BASIS]\n"
    "Quote or explicitly reference ONLY source snippets that exist in the provided RAG/legal context. Generic references like 'Law 4412/2016' are NOT allowed unless the text appears in context. If no exact source snippet is available, write exactly: 'Δεν υπάρχει επαρκής τεκμηρίωση στο διαθέσιμο υλικό.' Do not infer missing articles, deadlines, thresholds, sanctions, exceptions, or case-law.\n\n"
    "[CHALLENGE]\n"
    "One decision-making question for the user.\n\n"
    "[OPTIONS]\n"
    "A. ...\nB. ...\nC. ...\n\n"
    "[GROUNDING CHECK]\n"
    "For each option, state whether it is supported by available context: Supported, Partially supported, or Not supported.\n\n"
    "[FEEDBACK RULE]\n"
    "Explain how feedback will be evaluated, using only available context.\n\n"
    "[LIMITATION]\n"
    "Η προσομοίωση αποτελεί εκπαιδευτικό εργαλείο και όχι οριστική νομική αξιολόγηση."
)

# ── System prompt for CONCLUSION (forced ending) ────────────────────────
SIMULATION_SYSTEM_PROMPT_CONCLUSION = (
    "You are a Strict Procurement Examiner (Professor) specializing in EU Procurement Directives and Greek Law 4412/2016.\n\n"
    "The simulation is now ENDING. Evaluate the student's final choice and provide a conclusion.\n\n"
    "ABSOLUTE RULES:\n"
    "1. Use ONLY: provided RAG context, provided legal context, conversation history, and explicitly available scenario facts.\n"
    "2. Do NOT invent: legal provisions, deadlines, thresholds, sanctions, exceptions, court decisions, procedural requirements, or institutional facts.\n"
    "3. If the RAG context does not support a claim, write: 'Δεν υπάρχει επαρκής τεκμηρίωση στο διαθέσιμο υλικό.'\n"
    "4. Do NOT present legal conclusions as final judgments. Replace 'είναι παράνομο' with 'δημιουργεί ένδειξη κινδύνου και απαιτεί περαιτέρω έλεγχο'.\n"
    "5. Απαγορεύεται η παραγωγή μη τεκμηριωμένων νομικών ή διαδικαστικών ισχυρισμών. Κάθε ισχυρισμός πρέπει να βασίζεται ρητά στο διαθέσιμο RAG/legal context. Αν δεν υπάρχει τεκμηρίωση, δήλωσέ το.\n"
    "6. Output the scenario, questions, assessment, and feedback in clear, professional English. Source quotations may remain in their original language, including Greek.\n"
    "7. If the available RAG/legal context is in Greek, you may explain it in English, but every legal claim must remain grounded in the provided source text.\n\n"
    "OUTPUT FORMAT (strictly follow this layout):\n"
    "[YOUR CHOICE]\n"
    "(Restate what the user chose)\n\n"
    "[ASSESSMENT]\n"
    "(Evaluate the choice without presenting legal conclusions as final judgments)\n\n"
    "[WHY]\n"
    "(Explain the assessment based ONLY on available context)\n\n"
    "[LEGAL BASIS]\n"
    "Quote or explicitly reference ONLY source snippets that exist in the provided RAG/legal context. Generic references like 'Law 4412/2016' are NOT allowed unless the text appears in context. If no exact source snippet is available, write exactly: 'Δεν υπάρχει επαρκής τεκμηρίωση στο διαθέσιμο υλικό.' Do not infer missing articles, deadlines, thresholds, sanctions, exceptions, or case-law.\n\n"
    "[LIMITATION]\n"
    "Η προσομοίωση αποτελεί εκπαιδευτικό εργαλείο και όχι οριστική νομική αξιολόγηση.\n\n"
    "---\n"
    "[CONCLUSION]\n"
    "Summarize the final outcome of the entire procurement process using only available facts.\n\n"
    "[SCORE]\n"
    "Grade 0-100 with justification."
)

FALLBACK_SYSTEM_PROMPT_START = (
    "You are an Educational Procurement Trainer. The RAG context is insufficient, so you must create a generic fallback scenario.\n\n"
    "ABSOLUTE RULES:\n"
    "1. Do NOT use specific legal articles, thresholds, deadlines, sanctions, case-law, or procedural obligations.\n"
    "2. Do NOT present legal conclusions (e.g., avoid 'this is illegal').\n"
    "3. Use safe wording: 'risk indicator', 'requires further review', 'requires checking against applicable rules', 'educational example'.\n"
    "4. You MAY include fictional authorities, fictional procurement needs, fictional supplier interactions, and generic dilemmas.\n"
    "5. Output in clear, professional English.\n\n"
    "OUTPUT FORMAT (strictly follow this layout):\n"
    "[SIMULATION MODE]\n"
    "Educational fallback — not legally grounded\n\n"
    "[SCENARIO]\n"
    "A fictional procurement training scenario without legal claims.\n\n"
    "[LEGAL BASIS]\n"
    "Δεν υπάρχει επαρκής τεκμηρίωση στο διαθέσιμο υλικό.\n\n"
    "[CHALLENGE]\n"
    "One practical decision-making question.\n\n"
    "[OPTIONS]\n"
    "A. ...\nB. ...\nC. ...\n\n"
    "[GROUNDING CHECK]\n"
    "A. Not legally grounded — educational option only.\n"
    "B. Not legally grounded — educational option only.\n"
    "C. Not legally grounded — educational option only.\n\n"
    "[FEEDBACK RULE]\n"
    "Feedback will evaluate reasoning quality only, not legal correctness.\n\n"
    "[LIMITATION]\n"
    "Η προσομοίωση είναι γενικό εκπαιδευτικό σενάριο και όχι οριστική νομική αξιολόγηση."
)

FALLBACK_SYSTEM_PROMPT_CONTINUE = (
    "You are an Educational Procurement Trainer evaluating the student's choice in a generic fallback scenario.\n\n"
    "ABSOLUTE RULES:\n"
    "1. Do NOT use specific legal articles, thresholds, deadlines, sanctions, case-law, or procedural obligations.\n"
    "2. Do NOT present legal conclusions (e.g., avoid 'this is illegal').\n"
    "3. Use safe wording: 'risk indicator', 'requires further review', 'requires checking against applicable rules', 'educational example'.\n"
    "4. Output in clear, professional English.\n\n"
    "OUTPUT FORMAT (strictly follow this layout):\n"
    "[SIMULATION MODE]\n"
    "Educational fallback — not legally grounded\n\n"
    "[YOUR CHOICE]\n"
    "(Restate what the user chose)\n\n"
    "[ASSESSMENT]\n"
    "(Evaluate the choice based on general logic and risk management, using safe wording)\n\n"
    "[WHY]\n"
    "(Explain the logic without citing laws)\n\n"
    "[LEGAL BASIS]\n"
    "Δεν υπάρχει επαρκής τεκμηρίωση στο διαθέσιμο υλικό.\n\n"
    "[LIMITATION]\n"
    "Η προσομοίωση είναι γενικό εκπαιδευτικό σενάριο και όχι οριστική νομική αξιολόγηση.\n\n"
    "---\n"
    "[SCENARIO]\n"
    "A new fictional procurement training scenario step without legal claims.\n\n"
    "[LEGAL BASIS]\n"
    "Δεν υπάρχει επαρκής τεκμηρίωση στο διαθέσιμο υλικό.\n\n"
    "[CHALLENGE]\n"
    "One practical decision-making question.\n\n"
    "[OPTIONS]\n"
    "A. ...\nB. ...\nC. ...\n\n"
    "[GROUNDING CHECK]\n"
    "A. Not legally grounded — educational option only.\n"
    "B. Not legally grounded — educational option only.\n"
    "C. Not legally grounded — educational option only.\n\n"
    "[FEEDBACK RULE]\n"
    "Feedback will evaluate reasoning quality only, not legal correctness.\n\n"
    "[LIMITATION]\n"
    "Η προσομοίωση είναι γενικό εκπαιδευτικό σενάριο και όχι οριστική νομική αξιολόγηση."
)

FALLBACK_SYSTEM_PROMPT_CONCLUSION = (
    "You are an Educational Procurement Trainer concluding a generic fallback scenario.\n\n"
    "ABSOLUTE RULES:\n"
    "1. Do NOT use specific legal articles, thresholds, deadlines, sanctions, case-law, or procedural obligations.\n"
    "2. Do NOT present legal conclusions (e.g., avoid 'this is illegal').\n"
    "3. Use safe wording: 'risk indicator', 'requires further review', 'requires checking against applicable rules', 'educational example'.\n"
    "4. Output in clear, professional English.\n\n"
    "OUTPUT FORMAT (strictly follow this layout):\n"
    "[SIMULATION MODE]\n"
    "Educational fallback — not legally grounded\n\n"
    "[YOUR CHOICE]\n"
    "(Restate what the user chose)\n\n"
    "[ASSESSMENT]\n"
    "(Evaluate the choice based on general logic and risk management)\n\n"
    "[WHY]\n"
    "(Explain the logic without citing laws)\n\n"
    "[LEGAL BASIS]\n"
    "Δεν υπάρχει επαρκής τεκμηρίωση στο διαθέσιμο υλικό.\n\n"
    "[LIMITATION]\n"
    "Η προσομοίωση είναι γενικό εκπαιδευτικό σενάριο και όχι οριστική νομική αξιολόγηση.\n\n"
    "---\n"
    "[CONCLUSION]\n"
    "Summarize the final outcome based on general logic.\n\n"
    "[SCORE]\n"
    "Grade 0-100 with justification based on reasoning quality."
)


def _count_student_turns(history: List[Dict]) -> int:
    """Count how many times the student has answered (excluding 'start' commands)."""
    count = 0
    start_words = {"start", "new", "scenario", "simulation", "ξεκίνα", "σεναριο", "σενάριο", "παιχνίδι", "προσομοίωση", "προσομοιωση", "serious game"}
    for msg in history:
        if msg.get("role") == "user":
            text = msg.get("text", "").strip().lower()
            # Don't count the initial "start" command
            if not any(w in text for w in start_words):
                count += 1
    return count


def build_simulation_prompt(question: str, history: List[Dict], rag_ctx: str, is_conclusion: bool = False) -> str:
    is_start = any(w in question.lower() for w in ["start", "ξεκίνα", "σεναριο", "σενάριο", "παιχνίδι", "εκπαίδευση", "scenario", "simulation", "new", "προσομοίωση", "προσομοιωση", "serious game"])
    
    if is_start:
        # Extract specific focus if possible (anything after the start keywords)
        focus = question
        for w in ["start", "ξεκίνα", "σεναριο", "σενάριο", "παιχνίδι", "εκπαίδευση", "scenario", "simulation", "new", "προσομοίωση", "προσομοιωση", "serious game"]:
            focus = focus.lower().replace(w, "").strip()
            
        prompt = (
            f"GENERATE A BRAND NEW, UNIQUE PROCUREMENT TRAINING SCENARIO focused on: '{focus if focus else 'General Procurement'}'.\n"
            "Domain: Public Procurement (EU Directives / Greek Law 4412/2016).\n"
            "Create a realistic situation with specific (fictional) entities and amounts in €.\n"
        )
        if rag_ctx:
            prompt += f"\nBase the scenario on this legal context:\n{rag_ctx[:3000]}\n"
        return prompt

    # Extract last professor scenario and student's choice letter
    last_professor_text = ""
    for msg in reversed(history):
        if msg.get("role") in ["bot", "assistant"]:
            last_professor_text = msg.get("text", "")
            break
    
    # Build a minimal prompt to avoid confusing the small LLM
    prompt = f"PREVIOUS SCENARIO:\n{last_professor_text[:500]}\n\n"
    prompt += f"The student chose: '{question}'\n\n"
    
    if rag_ctx:
        prompt += f"LEGAL CONTEXT:\n{rag_ctx[:3000]}\n\n"
    
    if is_conclusion:
        prompt += "This is the FINAL TURN. Follow the STRICT OUTPUT FORMAT for CONCLUSION."
    else:
        prompt += "Evaluate the choice. Then present a NEW, DIFFERENT challenge. Follow the STRICT OUTPUT FORMAT for CONTINUING."
    
    return prompt


def stream_simulation(question: str, history: List[Dict], rag_ctx: str):
    ctx_len = len(rag_ctx.strip()) if rag_ctx else 0
    print(f"[SIMULATION] rag_ctx length: {ctx_len}", flush=True)

    is_fallback = ctx_len < 50
    if is_fallback:
        print("[SIMULATION] mode: educational fallback", flush=True)
    else:
        print("[SIMULATION] mode: RAG-grounded", flush=True)

    is_start = any(w in question.lower() for w in ["start", "ξεκίνα", "σεναριο", "σενάριο", "παιχνίδι", "εκπαίδευση", "scenario", "simulation", "new", "προσομοίωση", "προσομοιωση", "serious game"])
    
    # Count student turns to decide if we should force a conclusion
    student_turns = _count_student_turns(history)
    is_conclusion = (not is_start) and (student_turns >= MAX_TURNS)
    
    if is_conclusion:
        print(f"[SIMULATION] Forcing conclusion after {student_turns} student turns", flush=True)
    
    prompt = build_simulation_prompt(question, history, rag_ctx, is_conclusion=is_conclusion)
    
    if is_fallback:
        if is_start:
            sys_prompt = FALLBACK_SYSTEM_PROMPT_START
        elif is_conclusion:
            sys_prompt = FALLBACK_SYSTEM_PROMPT_CONCLUSION
        else:
            sys_prompt = FALLBACK_SYSTEM_PROMPT_CONTINUE
    else:
        if is_start:
            sys_prompt = SIMULATION_SYSTEM_PROMPT_START
        elif is_conclusion:
            sys_prompt = SIMULATION_SYSTEM_PROMPT_CONCLUSION
        else:
            sys_prompt = SIMULATION_SYSTEM_PROMPT_CONTINUE
    
    yield from stream_llm(prompt, max_tokens=600, temperature=0.7, system_prompt=sys_prompt)


def generate_report_card(history: List[Dict]):
    from llm_interface import call_llm_json
    
    # Extract only the relevant parts
    transcript = ""
    for msg in history:
        role = "Student" if msg.get("role") == "user" else "Professor"
        transcript += f"{role}: {msg.get('text', '')[:300]}\n"
    
    prompt = (
        "Evaluate this procurement simulation transcript.\n"
        "The student was tested on EU Procurement Directives and Greek Law 4412/2016.\n\n"
        "Return a JSON object with:\n"
        '- "Legal_Knowledge": score 0-100,\n'
        '- "Risk_Assessment": score 0-100,\n'
        '- "Decision_Making": score 0-100,\n'
        '- "Overall_Grade": score 0-100,\n'
        '- "Summary": a brief 2-3 sentence assessment of the student\'s performance,\n'
        '- "Key_Mistakes": list of key mistakes (if any),\n'
        '- "Recommendation": what the student should study next.\n\n'
        f"TRANSCRIPT:\n{transcript[-2000:]}"
    )
    return call_llm_json(prompt, max_tokens=1000)
