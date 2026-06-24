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
    "1. Use clear, professional ENGLISH.\n"
    "2. STOP generating IMMEDIATELY after listing option C. Do NOT reveal the correct answer.\n"
    "3. Reference specific legal articles (e.g. Art. 32(2)(c) of Law 4412/2016) in [CHALLENGE].\n"
    "4. SOURCE HIERARCHY: Law > Court/Authority Decisions > EU Guidelines.\n"
    "5. STYLE MIMICRY: If the provided context contains previous scenario examples, use their narrative structure, tone, and complexity level as a template for the new one.\n\n"
    "OUTPUT FORMAT (nothing else):\n"
    "[SCENARIO]: A realistic procurement case with specific entities and amounts in €.\n"
    "[CHALLENGE]: The legal dilemma. Cite the relevant article.\n"
    "[QUESTION]: One clear question.\n"
    "[OPTIONS]:\n"
    "A) ...\nB) ...\nC) ..."
)

# ── System prompt for CONTINUING (evaluating a student choice) ───────────
SIMULATION_SYSTEM_PROMPT_CONTINUE = (
    "You are a Strict Procurement Examiner (Professor) specializing in EU Procurement Directives and Greek Law 4412/2016.\n\n"
    "ABSOLUTE RULES:\n"
    "1. Use clear, professional ENGLISH.\n"
    "2. STOP generating IMMEDIATELY after listing option C.\n"
    "3. Cite specific legal articles when evaluating.\n"
    "4. SOURCE HIERARCHY: Law > Court/Authority Decisions > EU Guidelines.\n"
    "5. If the student chose correctly, ACKNOWLEDGE IT and advance to a NEW phase of the procurement.\n"
    "6. If the student chose incorrectly, explain WHY with a legal citation and present a consequence.\n"
    "7. Each turn must present a DIFFERENT challenge — do NOT repeat the same issue.\n"
    "8. STYLE CONSISTENCY: Maintain the narrative tone and complexity level found in the initial scenario or provided examples.\n\n"
    "OUTPUT FORMAT (nothing else):\n"
    "[CONSEQUENCE]: Was the choice correct or wrong? What happens next? Cite the law.\n"
    "[NEW CHALLENGE]: A new, different obstacle in this procurement.\n"
    "[QUESTION]: One clear question.\n"
    "[OPTIONS]:\n"
    "A) ...\nB) ...\nC) ..."
)

# ── System prompt for CONCLUSION (forced ending) ────────────────────────
SIMULATION_SYSTEM_PROMPT_CONCLUSION = (
    "You are a Strict Procurement Examiner (Professor) specializing in EU Procurement Directives and Greek Law 4412/2016.\n\n"
    "The simulation is now ENDING. Evaluate the student's final choice and provide a conclusion.\n\n"
    "ABSOLUTE RULES:\n"
    "1. Use clear, professional ENGLISH.\n"
    "2. Cite specific legal articles.\n"
    "3. SOURCE HIERARCHY: Law > Court/Authority Decisions > EU Guidelines.\n\n"
    "OUTPUT FORMAT (nothing else):\n"
    "[CONSEQUENCE]: Evaluate the student's final choice. Cite the law.\n"
    "[CONCLUSION]: Summarize the final outcome of the entire procurement process. Was the procurement successful or did it fail? What were the key decisions?\n"
    "[SCORE]: Grade 0-100 with justification."
)


def _count_student_turns(history: List[Dict]) -> int:
    """Count how many times the student has answered (excluding 'start' commands)."""
    count = 0
    start_words = {"start", "new", "scenario", "simulation", "ξεκίνα", "σεναριο", "σενάριο", "παιχνίδι"}
    for msg in history:
        if msg.get("role") == "user":
            text = msg.get("text", "").strip().lower()
            # Don't count the initial "start" command
            if not any(w in text for w in start_words):
                count += 1
    return count


def build_simulation_prompt(question: str, history: List[Dict], rag_ctx: str, is_conclusion: bool = False) -> str:
    is_start = any(w in question.lower() for w in ["start", "ξεκίνα", "σεναριο", "σενάριο", "παιχνίδι", "εκπαίδευση", "scenario", "simulation", "new"])
    
    if is_start:
        # Extract specific focus if possible (anything after the start keywords)
        focus = question
        for w in ["start", "ξεκίνα", "σεναριο", "σενάριο", "παιχνίδι", "εκπαίδευση", "scenario", "simulation", "new"]:
            focus = focus.lower().replace(w, "").strip()
            
        prompt = (
            f"GENERATE A BRAND NEW, UNIQUE PROCUREMENT TRAINING SCENARIO focused on: '{focus if focus else 'General Procurement'}'.\n"
            "Domain: Public Procurement (EU Directives / Greek Law 4412/2016).\n"
            "Create a realistic situation with specific (fictional) entities and amounts in €.\n"
        )
        if rag_ctx:
            prompt += f"\nBase the scenario on this legal context:\n{rag_ctx[:800]}\n"
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
        prompt += f"LEGAL CONTEXT:\n{rag_ctx[:400]}\n\n"
    
    if is_conclusion:
        prompt += "This is the FINAL TURN. Provide [CONSEQUENCE], [CONCLUSION], and [SCORE]."
    else:
        prompt += "Evaluate the choice. Then present a NEW, DIFFERENT challenge. Output: [CONSEQUENCE], [NEW CHALLENGE], [QUESTION], [OPTIONS] A/B/C."
    
    return prompt


def stream_simulation(question: str, history: List[Dict], rag_ctx: str):
    is_start = any(w in question.lower() for w in ["start", "ξεκίνα", "σεναριο", "σενάριο", "παιχνίδι", "εκπαίδευση", "scenario", "simulation", "new"])
    
    # Count student turns to decide if we should force a conclusion
    student_turns = _count_student_turns(history)
    is_conclusion = (not is_start) and (student_turns >= MAX_TURNS)
    
    if is_conclusion:
        print(f"[SIMULATION] Forcing conclusion after {student_turns} student turns", flush=True)
    
    prompt = build_simulation_prompt(question, history, rag_ctx, is_conclusion=is_conclusion)
    
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
