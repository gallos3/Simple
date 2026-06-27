"""
Procurement Simulation Engine - Serious Game Logic (V3 - Server-Side Turn Control)
The LLM cannot be trusted to track turns or end the game. We enforce it here.
"""
import re
import os
import json
import glob
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

SCENARIO_PATTERNS = {
    "direct_award_fragmentation": {
        "name": "Fragmentation / repeated low-value purchase risk pattern",
        "scenario": "A hospital department has several similar supply needs during the same financial year. Different units propose separate low-value purchases from the same supplier family. The procurement officer must decide how to document the estimated value, market research, and whether the needs should be examined together before proceeding.",
        "challenge": "Which option best addresses the fragmentation risk and creates the strongest audit trail without causing undue operational delays?",
        "options": "A. Proceed with separate purchases immediately but document the urgent need.\nB. Consolidate the requests to assess the total estimated value before proceeding.\nC. Ask each unit to provide a separate market research memo, then process them individually.",
        "learning_focus": "A. Tests awareness of artificial fragmentation versus speed.\nB. Tests understanding of estimated value aggregation and consolidation rules.\nC. Tests documentation quality and whether isolated memos cure fragmentation risk.",
        "feedback": {
            "A": "Option A is fast, but it treats similar needs as isolated requests. This may weaken estimated-value reasoning and create a weak audit trail.",
            "B": "Option B is the strongest response. It consolidates similar needs for review, supports estimated-value reasoning, and creates a clearer audit trail before any award decision.",
            "C": "Option C improves documentation at unit level, but separate memos do not fully address the fragmentation risk if the needs are similar and should be examined together."
        }
    },
    "urgent_need_justification": {
        "name": "Urgent need justification risk pattern",
        "scenario": "A critical system failure requires immediate replacement parts. The technical team insists on bypassing standard procedures due to the emergency, but the initial failure occurred three months ago and was left unresolved until now.",
        "challenge": "Which option provides the most appropriate balance between addressing the urgency and maintaining a defensible audit trail?",
        "options": "A. Authorize immediate purchase based on unforeseen extreme urgency.\nB. Request a detailed timeline demonstrating why the delay was unforeseeable before authorizing.\nC. Use a more structured supplier comparison route, accepting the operational downtime.",
        "learning_focus": "A. Tests identification of the 'unforeseeable' requirement for true urgency.\nB. Tests documentation of causal links and risk of internal delays masking as emergencies.\nC. Tests proportionality and operational risk awareness.",
        "feedback": {
            "A": "Option A relies purely on speed but lacks evidence that the delay was unforeseeable. This may create an audit concern regarding the justification of extreme urgency.",
            "B": "Option B is the strongest response. It requires a documented timeline to separate operational delays from genuinely unforeseeable events, supporting a strong evidence trail.",
            "C": "Option C ensures maximum supplier comparison but may cause disproportionate operational harm. It highlights the tension between planning and emergency response."
        }
    },
    "technical_specifications_bias": {
        "name": "Technical specifications bias risk pattern",
        "scenario": "A requesting department submits technical specifications for new IT equipment that perfectly match the proprietary brochure of a single manufacturer, including specific trademarked features not essential to the core functionality.",
        "challenge": "Which option best mitigates the risk of restricted competition while meeting the operational need?",
        "options": "A. Publish the specifications as provided to avoid delaying the IT upgrade.\nB. Add 'or equivalent' to the specifications but keep the trademarked features.\nC. Return the specifications to the department, requiring them to define needs based on performance and functional requirements.",
        "learning_focus": "A. Tests awareness of competition restriction and bias indicators.\nB. Tests superficial compliance vs. genuine equivalence.\nC. Tests the principle of functional specification and broad market access.",
        "feedback": {
            "A": "Option A prioritizes speed but risks introducing strong bias. Publishing proprietary features without functional necessity creates a weak audit trail for open competition.",
            "B": "Option B provides superficial improvement by adding 'or equivalent', but retaining trademarked features still strongly points to a specific vendor, requiring further review.",
            "C": "Option C is the strongest response. It requires the department to define needs functionally, removing bias indicators and supporting transparency safeguards."
        }
    },
    "general_risk": {
        "name": "General procurement risk pattern",
        "scenario": "A professional procurement scenario based on a predefined risk pattern.",
        "challenge": "Which option best mitigates procurement risk while ensuring transparency and value for money?",
        "options": "A. Fastest action, weak documentation.\nB. Balanced action with written comparison and internal review.\nC. Delayed action with stronger planning but operational risk.",
        "learning_focus": "A. Tests speed-versus-documentation trade-off.\nB. Tests whether justification is supported by evidence and records.\nC. Tests transparency, review, and audit-trail reasoning.",
        "feedback": {
            "A": "Option A is fast but produces a weak evidence trail, which may create an audit concern.",
            "B": "Option B is the strongest response. It balances operational action with documented comparison and internal review, supporting value-for-money reasoning.",
            "C": "Option C provides stronger documentation but may introduce disproportionate operational risk if the delay is unwarranted."
        }
    }
}
def get_scenario_pattern(question: str) -> dict:
    q = question.lower()
    if any(k in q for k in ["direct award", "απευθείας ανάθεση", "απευθείας αναθέσεις"]):
        return SCENARIO_PATTERNS["direct_award_fragmentation"]
    if any(k in q for k in ["urgent", "urgency", "κατεπείγον", "κατεπείγουσα"]):
        return SCENARIO_PATTERNS["urgent_need_justification"]
    if any(k in q for k in ["technical specifications", "φωτογραφικές", "specifications"]):
        return SCENARIO_PATTERNS["technical_specifications_bias"]
    return SCENARIO_PATTERNS["general_risk"]

def build_fallback_start(pattern: dict) -> str:
    return f"""You are an Educational Procurement Trainer. The RAG context is insufficient, so you must create a professional training scenario.

ABSOLUTE RULES:
1. Do NOT use specific legal articles, Greek Law 4412/2016, EU directive numbers, thresholds, deadlines, sanctions, case-law, or procedural obligations.
2. Do NOT present legal conclusions (e.g., avoid 'this is illegal').
3. Use safe wording: 'risk indicator', 'requires documented justification', 'requires verification against applicable rules', 'may create audit concern', 'requires further review', 'weak audit trail', 'transparency safeguard', 'value-for-money reasoning'.
4. Do NOT say 'not legally grounded'.
5. Output in clear, professional English.
6. The number of options and the number of learning focuses must match exactly.
7. Do NOT ask whether something is legally compliant. Instead, ask practical risk management questions.
8. Do NOT invent regulatory bodies, registers, certifications, official lists, acronyms, or authorities (e.g., no ENBs).
9. Do NOT mention: Greek Law 4412/2016, EU Directives, legal articles, notified bodies, ENBs, thresholds, deadlines, sanctions, or formal procedures.
10. Do NOT use 'direct award' as a legal mechanism in fallback mode.

OUTPUT FORMAT (strictly follow this layout):
[SIMULATION MODE]
Professional Procurement Training Mode

[SCENARIO]
{pattern['scenario']}

[RISK PATTERN]
{pattern['name']}

[TRAINING OBJECTIVE]
Practice identifying procurement risk indicators, documentation gaps, and appropriate audit safeguards.

[CHALLENGE]
{pattern['challenge']}
Do NOT ask if it is legal or compliant.

[OPTIONS]
Provide exactly three options:
{pattern['options']}

[LEARNING FOCUS]
{pattern['learning_focus']}

[FEEDBACK RULE]
Feedback will evaluate:
- identification of risk indicators
- quality of documentation reasoning
- transparency safeguards
- evidence trail
- value-for-money reasoning
- proportionality
- whether further legal verification is needed

[LIMITATION]
This is a professional training simulation. It is not legal advice and does not constitute a final legal assessment."""

def build_fallback_continue(pattern: dict) -> str:
    return f"""You are an Educational Procurement Trainer evaluating the student's choice in a professional fallback scenario.

ABSOLUTE RULES:
1. Do NOT use specific legal articles, Greek Law 4412/2016, EU directive numbers, thresholds, deadlines, sanctions, case-law, or procedural obligations.
2. Do NOT present legal conclusions (e.g., avoid 'this is illegal').
3. Use safe wording: 'risk indicator', 'requires documented justification', 'requires verification against applicable rules', 'may create audit concern', 'requires further review', 'weak audit trail', 'transparency safeguard', 'value-for-money reasoning'.
4. Do NOT say 'not legally grounded'.
5. Output in clear, professional English.
6. The number of options and the number of learning focuses must match exactly.
7. Do NOT ask whether something is legally compliant. Instead, ask practical risk management questions.
8. Do NOT invent regulatory bodies, registers, certifications, official lists, acronyms, or authorities (e.g., no ENBs).
9. Do NOT mention: Greek Law 4412/2016, EU Directives, legal articles, notified bodies, ENBs, thresholds, deadlines, sanctions, or formal procedures.
10. Do NOT use 'direct award' as a legal mechanism in fallback mode.

OUTPUT FORMAT (strictly follow this layout):
[SIMULATION MODE]
Professional Procurement Training Mode

[YOUR CHOICE]
(Restate what the user chose)

[ASSESSMENT]
(Evaluate the choice based on general logic and risk management, using safe wording)

[WHY]
(Explain the logic without citing laws)

[RISK PATTERN]
{pattern['name']}

[TRAINING OBJECTIVE]
Practice identifying procurement risk indicators, documentation gaps, and appropriate audit safeguards.

[LIMITATION]
This is a professional training simulation. It is not legal advice and does not constitute a final legal assessment.

---
[SCENARIO]
A new professional procurement training scenario step related to the {pattern['name']}.

[RISK PATTERN]
{pattern['name']}

[TRAINING OBJECTIVE]
Practice identifying procurement risk indicators, documentation gaps, and appropriate audit safeguards.

[CHALLENGE]
Provide a follow-up professional decision-making question. Do NOT ask if it is legal or compliant.

[OPTIONS]
Provide exactly three options:
A. ...
B. ...
C. ...

[LEARNING FOCUS]
Explain the professional reasoning skill tested by each option.

[FEEDBACK RULE]
Feedback will evaluate:
- identification of risk indicators
- quality of documentation reasoning
- transparency safeguards
- evidence trail
- value-for-money reasoning
- proportionality
- whether further legal verification is needed

[LIMITATION]
This is a professional training simulation. It is not legal advice and does not constitute a final legal assessment."""

def build_fallback_conclusion(pattern: dict) -> str:
    return f"""You are an Educational Procurement Trainer concluding a professional fallback scenario.

ABSOLUTE RULES:
1. Do NOT use specific legal articles, Greek Law 4412/2016, EU directive numbers, thresholds, deadlines, sanctions, case-law, or procedural obligations.
2. Do NOT present legal conclusions (e.g., avoid 'this is illegal').
3. Use safe wording: 'risk indicator', 'requires documented justification', 'requires verification against applicable rules', 'may create audit concern', 'requires further review', 'weak audit trail', 'transparency safeguard', 'value-for-money reasoning'.
4. Do NOT say 'not legally grounded'.
5. Output in clear, professional English.
6. Do NOT invent regulatory bodies, registers, certifications, official lists, acronyms, or authorities (e.g., no ENBs).
7. Do NOT mention: Greek Law 4412/2016, EU Directives, legal articles, notified bodies, ENBs, thresholds, deadlines, sanctions, or formal procedures.
8. Do NOT use 'direct award' as a legal mechanism in fallback mode.

OUTPUT FORMAT (strictly follow this layout):
[SIMULATION MODE]
Professional Procurement Training Mode

[YOUR CHOICE]
(Restate what the user chose)

[ASSESSMENT]
(Evaluate the choice based on general logic and risk management)

[WHY]
(Explain the logic without citing laws)

[RISK PATTERN]
{pattern['name']}

[TRAINING OBJECTIVE]
Practice identifying procurement risk indicators, documentation gaps, and appropriate audit safeguards.

[LIMITATION]
This is a professional training simulation. It is not legal advice and does not constitute a final legal assessment.

---
[CONCLUSION]
Summarize the final outcome based on professional risk management and audit principles.

[SCORE]
Grade 0-100 with justification based on reasoning quality."""


def render_professional_training_start(pattern: dict) -> str:
    return f"""[SIMULATION MODE]
Professional Procurement Training Mode

[SCENARIO]
{pattern['scenario']}

[RISK PATTERN]
{pattern['name']}

[TRAINING OBJECTIVE]
Practice identifying procurement risk indicators, documentation gaps, and appropriate audit safeguards.

[CHALLENGE]
{pattern['challenge']}

[OPTIONS]
{pattern['options']}

[LEARNING FOCUS]
{pattern['learning_focus']}

[FEEDBACK RULE]
Feedback will evaluate:
- identification of risk indicators
- quality of documentation reasoning
- transparency safeguards
- evidence trail
- value-for-money reasoning
- proportionality
- whether further legal verification is needed

[LIMITATION]
This is a professional training simulation. It is not legal advice and does not constitute a final legal assessment."""

def stream_static_text(text: str, chunk_size: int = 10, delay: float = 0.05):
    import time
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]
        if delay > 0:
            time.sleep(delay)



def get_scenario_pattern_from_history(history: list) -> dict:
    for msg in reversed(history):
        if msg.get("role") in ["bot", "assistant"]:
            text = msg.get("text", "")
            if "[RISK PATTERN]" in text:
                if "Fragmentation / repeated low-value purchase risk pattern" in text:
                    return SCENARIO_PATTERNS["direct_award_fragmentation"]
                elif "Urgent need justification risk pattern" in text:
                    return SCENARIO_PATTERNS["urgent_need_justification"]
                elif "Technical specifications bias risk pattern" in text:
                    return SCENARIO_PATTERNS["technical_specifications_bias"]
                break
    return SCENARIO_PATTERNS["general_risk"]

def render_professional_training_feedback(pattern: dict, choice: str) -> str:
    return f"""[SIMULATION MODE]
Professional Procurement Training Mode

[YOUR CHOICE]
{choice}

[RISK PATTERN]
{pattern['name']}

[ASSESSMENT]
{pattern['feedback'][choice]}

[WHY]
{pattern['learning_focus']}

[FEEDBACK RULE]
Feedback evaluates:
- identification of risk indicators
- documentation quality
- transparency safeguards
- evidence trail
- value-for-money reasoning
- proportionality
- whether further legal verification is needed

[NEXT STEP]
You can ask for another professional scenario, or answer "next" to continue with a new risk pattern.

[LIMITATION]
This is a professional training simulation. It is not legal advice and does not constitute a final legal assessment."""

def validate_scenario_graph(graph: dict) -> tuple[bool, list[str]]:
    errors = []
    
    # 1. Required top-level fields
    required_keys = ["scenario_id", "title", "validation_status", "start_node", "max_steps", "nodes"]
    for k in required_keys:
        if k not in graph:
            errors.append(f"Missing required key: {k}")
            
    if errors:
        return False, errors
        
    # 2. validation_status
    if graph["validation_status"] not in ["draft", "needs_review", "approved", "active"]:
        errors.append(f"Invalid validation_status: {graph['validation_status']}")
        
    # 3. review.approval_status
    review = graph.get("review", {})
    if review.get("approval_status") not in ["needs_review", "approved"]:
        errors.append(f"Invalid review.approval_status: {review.get('approval_status')}")
        
    # 4. start_node
    start_node = graph["start_node"]
    nodes = graph["nodes"]
    if start_node not in nodes:
        errors.append(f"start_node '{start_node}' not found in nodes")
        
    # 5, 6, 7, 8. Nodes and Options
    for node_id, node in nodes.items():
        for nk in ["text", "challenge", "options"]:
            if nk not in node:
                errors.append(f"Node '{node_id}' missing {nk}")
        if "options" in node:
            options = node["options"]
            if set(options.keys()) != {"A", "B", "C"}:
                errors.append(f"Node '{node_id}' options must be exactly A, B, C")
            for opt_key, opt in options.items():
                for ok in ["text", "next_node", "score_delta", "time_delta", "audit_risk_delta", "admin_burden_delta", "value_for_money_risk_delta", "feedback", "expert_log"]:
                    if ok not in opt:
                        errors.append(f"Node '{node_id}' Option '{opt_key}' missing {ok}")
                
                if "next_node" in opt:
                    nn = opt["next_node"]
                    if nn != "END" and nn not in nodes:
                        errors.append(f"Node '{node_id}' Option '{opt_key}' next_node '{nn}' does not exist")
        
        # 11. Dangerous terms
        dangerous_terms = [
            "illegal", 
            "legally compliant", 
            "compliance failure", 
            "sanction", 
            "court decision", 
            "exact threshold", 
            "exact article",
            "violates",
            "must comply with article",
            "according to article"
        ]
        text_fields = [node.get("text", ""), node.get("challenge", "")]
        if "options" in node:
            for opt in node["options"].values():
                text_fields.extend([opt.get("text", ""), opt.get("feedback", ""), opt.get("expert_log", "")])
        
        is_rag_grounded = graph.get("authoring_source_mode") == "rag_grounded"
        has_source_snippets = bool(graph.get("source_snippets")) or bool(graph.get("source_basis_snippets"))
        
        if not (is_rag_grounded and has_source_snippets):
            for t in text_fields:
                t_lower = t.lower()
                for dt in dangerous_terms:
                    if dt in t_lower:
                        errors.append(f"Node '{node_id}' contains dangerous term '{dt}' without valid RAG snippets")
                        
    # 9. Path reaches END
    ends_reached = 0
    def dfs(node_id, depth):
        nonlocal ends_reached
        if depth > graph["max_steps"]:
            return False
        node = nodes[node_id]
        if "options" not in node:
            return False
        for opt in node["options"].values():
            nn = opt.get("next_node")
            if nn == "END":
                ends_reached += 1
            elif nn in nodes:
                dfs(nn, depth + 1)
        return True
        
    if start_node in nodes:
        dfs(start_node, 1)
    if ends_reached == 0:
        errors.append("No path reaches 'END'")
        
    # 10. max_steps
    if graph["max_steps"] > 6:
        errors.append("max_steps must be <= 6")
        
    return len(errors) == 0, errors


def load_json_scenario_graphs(graphs_dir: str = None) -> dict:
    if graphs_dir is None:
        graphs_dir = os.path.join(os.path.dirname(__file__), "graphs")
        
    loaded_graphs = {}
    if not os.path.exists(graphs_dir):
        return loaded_graphs
        
    for filepath in glob.glob(os.path.join(graphs_dir, "*.json")):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                graph = json.load(f)
            
            is_valid, errors = validate_scenario_graph(graph)
            scenario_id = graph.get("scenario_id", os.path.basename(filepath))
            
            if is_valid:
                if graph.get("validation_status") == "active" and graph.get("review", {}).get("approval_status") == "approved":
                    loaded_graphs[scenario_id] = graph
                    print(f"[GRAPH VALIDATION] {scenario_id}: active and loaded")
                else:
                    print(f"[GRAPH VALIDATION] {scenario_id}: valid draft, not active")
            else:
                print(f"[GRAPH VALIDATION] {scenario_id}: invalid - {errors}")
        except Exception as e:
            print(f"[GRAPH VALIDATION] Failed to load {filepath}: {e}")
            
    return loaded_graphs



def get_runtime_scenario_graphs() -> dict:
    try:
        active_json_graphs = load_json_scenario_graphs()
    except Exception as e:
        print(f"[GRAPH RUNTIME] Error loading JSON graphs: {e}")
        active_json_graphs = {}
        
    runtime_graphs = {}
    runtime_graphs.update(SCENARIO_GRAPHS)
    runtime_graphs.update(active_json_graphs)
    
    print(f"[GRAPH RUNTIME] Loaded active JSON graphs: {list(active_json_graphs.keys())}")
    print("[GRAPH RUNTIME] Draft JSON graphs are not playable.")
    return runtime_graphs

def list_available_graphs() -> dict:
    json_graphs = load_json_scenario_graphs()
    graphs_dir = os.path.join(os.path.dirname(__file__), "graphs")
    draft_graphs = []
    validation_errors = {}
    
    if os.path.exists(graphs_dir):
        for filepath in glob.glob(os.path.join(graphs_dir, "*.json")):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    graph = json.load(f)
                is_valid, errors = validate_scenario_graph(graph)
                sid = graph.get("scenario_id", os.path.basename(filepath))
                if not is_valid:
                    validation_errors[sid] = errors
                elif graph.get("validation_status") != "active" or graph.get("review", {}).get("approval_status") != "approved":
                    draft_graphs.append(sid)
            except Exception as e:
                validation_errors[os.path.basename(filepath)] = str(e)
                
    return {
        "in_code_graphs": list(SCENARIO_GRAPHS.keys()),
        "json_draft_graphs": draft_graphs,
        "json_active_graphs": list(json_graphs.keys()),
        "validation_errors": validation_errors
    }


def select_labyrinth_scenario(question: str) -> str:
    q = question.lower()
    if any(k in q for k in ["urgent", "urgency", "urgent procurement", "κατεπείγον", "κατεπείγουσα ανάγκη"]):
        return "urgent_need_justification"
    if any(k in q for k in ["technical specifications", "specifications", "φωτογραφικές προδιαγραφές", "προδιαγραφές"]):
        return "technical_specifications_bias"
    return "direct_award_fragmentation"

SCENARIO_GRAPHS = {
    "direct_award_fragmentation": {
        "title": "Fragmentation / repeated low-value purchase risk pattern",
        "start_node": "n1",
        "max_steps": 6,
        "nodes": {
            "n1": {
                "text": "A hospital department has several similar supply needs during the same financial year. Different units propose separate low-value purchases from the same supplier family.",
                "challenge": "Which option best addresses the fragmentation risk and creates the strongest audit trail without causing undue operational delays?",
                "options": {
                    "A": {
                        "text": "Proceed with separate purchases immediately but document the urgent need.",
                        "next_node": "n2",
                        "score_delta": -10,
                        "time_delta": 0,
                        "audit_risk_delta": 2,
                        "admin_burden_delta": 1,
                        "value_for_money_risk_delta": 2,
                        "feedback": "Option A is fast, but it treats similar needs as isolated requests. This may weaken estimated-value reasoning and create a weak audit trail.",
                        "expert_log": "Chose isolated requests over consolidation. Increased audit risk."
                    },
                    "B": {
                        "text": "Consolidate the requests to assess the total estimated value before proceeding.",
                        "next_node": "n3",
                        "score_delta": 10,
                        "time_delta": 2,
                        "audit_risk_delta": 0,
                        "admin_burden_delta": 2,
                        "value_for_money_risk_delta": 0,
                        "feedback": "Option B is the strongest response. It consolidates similar needs for review, supports estimated-value reasoning, and creates a clearer audit trail before any award decision.",
                        "expert_log": "Chose consolidation. Strong audit trail."
                    },
                    "C": {
                        "text": "Ask each unit to provide a separate market research memo, then process them individually.",
                        "next_node": "n2",
                        "score_delta": 0,
                        "time_delta": 1,
                        "audit_risk_delta": 1,
                        "admin_burden_delta": 2,
                        "value_for_money_risk_delta": 1,
                        "feedback": "Option C improves documentation at unit level, but separate memos do not fully address the fragmentation risk if the needs are similar and should be examined together.",
                        "expert_log": "Chose separate memos. Marginal documentation improvement but fragmentation risk remains."
                    }
                }
            },
            "n2": {
                "text": "The separate purchases proceed, but internal tracking flags that the combined volume of these isolated requests may exceed the scope suitable for isolated handling.",
                "challenge": "How do you rectify the audit finding?",
                "options": {
                    "A": {
                        "text": "Argue the needs were unforeseeable to justify the isolated handling.",
                        "next_node": "n6",
                        "score_delta": -15,
                        "time_delta": 1,
                        "audit_risk_delta": 3,
                        "admin_burden_delta": 1,
                        "value_for_money_risk_delta": 1,
                        "feedback": "Arguing unforeseeability post-facto for routine supplies creates a severe audit vulnerability.",
                        "expert_log": "Attempted to use unforeseeability incorrectly."
                    },
                    "B": {
                        "text": "Consolidate the remaining needs to assess their total scope.",
                        "next_node": "n3",
                        "score_delta": 10,
                        "time_delta": 2,
                        "audit_risk_delta": -1,
                        "admin_burden_delta": 2,
                        "value_for_money_risk_delta": -1,
                        "feedback": "Consolidating remaining needs shows corrective action and mitigates further risk.",
                        "expert_log": "Corrective consolidation applied."
                    },
                    "C": {
                        "text": "Cancel all remaining requests to avoid further exposure.",
                        "next_node": "END",
                        "score_delta": -20,
                        "time_delta": 0,
                        "audit_risk_delta": 0,
                        "admin_burden_delta": 1,
                        "value_for_money_risk_delta": 3,
                        "feedback": "Canceling operational needs entirely harms the hospital's core mission.",
                        "expert_log": "Operational risk induced to avoid audit tracking."
                    }
                }
            },
            "n3": {
                "text": "The consolidated estimated value is calculated and confirms it requires broader review beyond standard low-value workflows.",
                "challenge": "What is the most appropriate next step?",
                "options": {
                    "A": {
                        "text": "Escalate the request for a more structured supplier comparison route.",
                        "next_node": "n5",
                        "score_delta": 15,
                        "time_delta": 2,
                        "audit_risk_delta": -1,
                        "admin_burden_delta": 2,
                        "value_for_money_risk_delta": -2,
                        "feedback": "Escalating for a structured supplier comparison is the proper action for aggregated values.",
                        "expert_log": "Correct escalation for structured comparison initiated."
                    },
                    "B": {
                        "text": "Split the value between two different financial years to avoid broader review.",
                        "next_node": "n6",
                        "score_delta": -25,
                        "time_delta": 1,
                        "audit_risk_delta": 4,
                        "admin_burden_delta": 1,
                        "value_for_money_risk_delta": 2,
                        "feedback": "Splitting across financial years to evade broader review is a classic fragmentation indicator and severely increases audit risk.",
                        "expert_log": "Attempted deliberate fragmentation across financial years."
                    },
                    "C": {
                        "text": "Seek expanded market research to justify the combined value.",
                        "next_node": "n4",
                        "score_delta": 10,
                        "time_delta": 2,
                        "audit_risk_delta": 0,
                        "admin_burden_delta": 2,
                        "value_for_money_risk_delta": -1,
                        "feedback": "Seeking expanded market research supports value-for-money reasoning and a clearer evidence trail.",
                        "expert_log": "Expanded market research initiated."
                    }
                }
            },
            "n4": {
                "text": "Market research suggests only two suitable suppliers are immediately available for the consolidated volume.",
                "challenge": "How do you handle the limited supplier availability?",
                "options": {
                    "A": {
                        "text": "Proceed with comparing only the two identified suppliers to save time.",
                        "next_node": "END",
                        "score_delta": -5,
                        "time_delta": 1,
                        "audit_risk_delta": 1,
                        "admin_burden_delta": 1,
                        "value_for_money_risk_delta": 1,
                        "feedback": "Comparing only two suppliers offers minimal assurance of value-for-money, but may be acceptable if thoroughly justified.",
                        "expert_log": "Proceeded with minimum comparison. Marginal value-for-money risk."
                    },
                    "B": {
                        "text": "Expand the search or escalate for a broader review.",
                        "next_node": "n5",
                        "score_delta": 10,
                        "time_delta": 2,
                        "audit_risk_delta": -1,
                        "admin_burden_delta": 2,
                        "value_for_money_risk_delta": -1,
                        "feedback": "Expanding the search supports strong transparency safeguards and value-for-money.",
                        "expert_log": "Pushed for broader market access."
                    },
                    "C": {
                        "text": "Ask the suppliers directly to lower prices based on the larger volume.",
                        "next_node": "n6",
                        "score_delta": -15,
                        "time_delta": 1,
                        "audit_risk_delta": 2,
                        "admin_burden_delta": 1,
                        "value_for_money_risk_delta": 0,
                        "feedback": "Informal price negotiation without a structured comparison process creates probity and transparency risks.",
                        "expert_log": "Engaged in unstructured informal negotiation."
                    }
                }
            },
            "n5": {
                "text": "The internal review team suggests internal verification against applicable rules before finalizing the structured comparison.",
                "challenge": "How should the procurement team respond?",
                "options": {
                    "A": {
                        "text": "Support internal verification against applicable rules and ensure documentation is complete.",
                        "next_node": "END",
                        "score_delta": 15,
                        "time_delta": 2,
                        "audit_risk_delta": -2,
                        "admin_burden_delta": 2,
                        "value_for_money_risk_delta": -1,
                        "feedback": "Supporting verification ensures a highly defensible audit trail and minimal risk.",
                        "expert_log": "Supported internal verification. Strong audit defensibility."
                    },
                    "B": {
                        "text": "Push back on the review to prioritize operational speed.",
                        "next_node": "END",
                        "score_delta": -10,
                        "time_delta": -1,
                        "audit_risk_delta": 2,
                        "admin_burden_delta": 0,
                        "value_for_money_risk_delta": 1,
                        "feedback": "Bypassing internal review prioritizes speed but increases exposure to audit findings.",
                        "expert_log": "Bypassed internal review for speed."
                    },
                    "C": {
                        "text": "Delegate the review back to the requesting units.",
                        "next_node": "n6",
                        "score_delta": -10,
                        "time_delta": 2,
                        "audit_risk_delta": 1,
                        "admin_burden_delta": 2,
                        "value_for_money_risk_delta": 1,
                        "feedback": "Delegating centralized review back to the units creates circular delays and weakens oversight.",
                        "expert_log": "Delegated oversight responsibilities incorrectly."
                    }
                }
            },
            "n6": {
                "text": "Severe risk indicators are present: administrative burden is rising, and the audit trail lacks a cohesive justification.",
                "challenge": "What is the final corrective action?",
                "options": {
                    "A": {
                        "text": "Stop the current approach and redesign the request centrally.",
                        "next_node": "END",
                        "score_delta": 10,
                        "time_delta": 3,
                        "audit_risk_delta": -1,
                        "admin_burden_delta": 2,
                        "value_for_money_risk_delta": -1,
                        "feedback": "Redesigning centrally is costly in time but effectively mitigates severe audit risk.",
                        "expert_log": "Halted process for central redesign. High time cost, safe audit."
                    },
                    "B": {
                        "text": "Justify past actions in a single overarching memo and proceed.",
                        "next_node": "END",
                        "score_delta": -20,
                        "time_delta": 1,
                        "audit_risk_delta": 4,
                        "admin_burden_delta": 1,
                        "value_for_money_risk_delta": 2,
                        "feedback": "A single memo cannot retroactively cure systemic fragmentation or transparency flaws.",
                        "expert_log": "Relied on weak post-facto memo justification."
                    },
                    "C": {
                        "text": "Accept operational delay and postpone the needs until the next planning cycle.",
                        "next_node": "END",
                        "score_delta": -5,
                        "time_delta": 2,
                        "audit_risk_delta": 0,
                        "admin_burden_delta": 1,
                        "value_for_money_risk_delta": 3,
                        "feedback": "Postponing resolves the audit risk but represents a failure to meet operational needs.",
                        "expert_log": "Accepted operational failure to avoid audit risk."
                    }
                }
            }
        }
    }
}

def get_msg_text(msg: dict) -> str:
    return (
        msg.get("text")
        or msg.get("content")
        or msg.get("message")
        or msg.get("answer")
        or msg.get("value")
        or ""
    )

def find_latest_labyrinth_context(history: list) -> dict:
    for msg in reversed(history):
        text = get_msg_text(msg)
        if "[SIMULATION MODE]\nProfessional Procurement Labyrinth" in text and "[SCENARIO_ID]\n" in text and "[CURRENT_NODE]\n" in text:
            id_match = re.search(r'\[SCENARIO_ID\]\n([^\n]+)', text)
            node_match = re.search(r'\[CURRENT_NODE\]\n([^\n]+)', text)
            if id_match and node_match:
                return {
                    "scenario_id": id_match.group(1).strip(),
                    "current_node": node_match.group(1).strip()
                }
    return None

def extract_choice(user_text: str):
    text = user_text.strip().lower()
    choice_map = {
        "a": "A", "α": "A",
        "b": "B", "β": "B",
        "c": "C", "γ": "C", "ψ": "C", "Ψ": "C"
    }
    
    # Direct match mapping
    if text in choice_map:
        return choice_map[text]
        
    match = re.search(r'\b(?:option|επιλογή|διάλεξα|choose|select)\s+([abcαβγψ])\b', text)
    if match:
        found = match.group(1).lower()
        return choice_map.get(found)
        
    match = re.search(r'^([abcαβγψ])\b', text)
    if match:
        found = match.group(1).lower()
        return choice_map.get(found)
        
    return None

def apply_labyrinth_option(state: dict, opt: dict):
    state["metrics"]["score_delta"] += opt["score_delta"]
    state["metrics"]["time_cost"] = max(0, state["metrics"]["time_cost"] + opt["time_delta"])
    state["metrics"]["audit_risk"] = max(0, state["metrics"]["audit_risk"] + opt["audit_risk_delta"])
    state["metrics"]["admin_burden"] = max(0, state["metrics"]["admin_burden"] + opt["admin_burden_delta"])
    state["metrics"]["value_for_money_risk"] = max(0, state["metrics"]["value_for_money_risk"] + opt["value_for_money_risk_delta"])

def replay_labyrinth_state(history: list, scenario_id: str) -> dict:
    runtime_graphs = get_runtime_scenario_graphs()
    graph = runtime_graphs.get(scenario_id)
    if not graph:
        return None
    
    state = {
        "scenario_id": scenario_id,
        "current_node": graph["start_node"],
        "step_count": 0,
        "path": [graph["start_node"]],
        "choices": [],
        "metrics": {
            "score_delta": 0,
            "time_cost": 0,
            "audit_risk": 0,
            "admin_burden": 0,
            "value_for_money_risk": 0
        },
        "events": [],
        "finished": False
    }
    
    started = False
    for msg in history:
        role = msg.get("role", "")
        text = get_msg_text(msg)
        
        if role in ["assistant", "bot"]:
            if "[SIMULATION MODE]\nProfessional Procurement Labyrinth" in text and f"[SCENARIO_ID]\n{scenario_id}" in text and "[STEP]\n1 /" in text:
                started = True
                state["current_node"] = graph["start_node"]
                state["step_count"] = 0
                state["path"] = [graph["start_node"]]
                state["choices"] = []
                state["metrics"] = {"score_delta": 0, "time_cost": 0, "audit_risk": 0, "admin_burden": 0, "value_for_money_risk": 0}
                state["events"] = []
                state["finished"] = False
                
        elif role == "user" and started and not state["finished"]:
            choice = extract_choice(text)
            if choice:
                node_data = graph["nodes"].get(state["current_node"])
                if node_data and choice in node_data["options"]:
                    opt = node_data["options"][choice]
                    
                    state["choices"].append(choice)
                    state["step_count"] += 1
                    
                    apply_labyrinth_option(state, opt)
                    
                    state["events"].append({
                        "node": state["current_node"],
                        "choice": choice,
                        "feedback": opt["feedback"],
                        "expert_log": opt["expert_log"]
                    })
                    
                    state["current_node"] = opt["next_node"]
                    state["path"].append(opt["next_node"])
                    
                    if state["current_node"] == "END" or state["step_count"] >= graph["max_steps"]:
                        state["finished"] = True

    return state

def calculate_labyrinth_score(state: dict) -> int:
    base_score = 70
    score = base_score + state["metrics"]["score_delta"] - (state["metrics"]["audit_risk"] * 5) - (state["metrics"]["value_for_money_risk"] * 3) - (state["metrics"]["time_cost"] * 2) - (state["metrics"]["admin_burden"] * 1)
    return max(0, min(100, score))

def get_risk_label(val: int) -> str:
    if val <= 2: return "low"
    if val <= 5: return "medium"
    return "high"

def render_labyrinth_start(graph: dict, state: dict) -> str:
    node = graph["nodes"][state["current_node"]]
    return f"""[SIMULATION MODE]
Professional Procurement Labyrinth
[SCENARIO_ID]
{state['scenario_id']}
[CURRENT_NODE]
{state['current_node']}

[STEP]
{state['step_count'] + 1} / {graph['max_steps']}

[SCENARIO]
{node['text']}

[CHALLENGE]
{node['challenge']}

[OPTIONS]
A. {node['options']['A']['text']}
B. {node['options']['B']['text']}
C. {node['options']['C']['text']}

[CURRENT METRICS]
Score: 70
Time impact: 0
Audit risk: 0
Administrative burden: 0
Value-for-money risk: 0"""

def render_labyrinth_step(graph: dict, state: dict, last_choice: str, last_opt: dict) -> str:
    node = graph["nodes"][state["current_node"]]
    score = calculate_labyrinth_score(state)
    return f"""[SIMULATION MODE]
Professional Procurement Labyrinth
[SCENARIO_ID]
{state['scenario_id']}
[CURRENT_NODE]
{state['current_node']}

[YOUR CHOICE]
{last_choice}

[FEEDBACK]
{last_opt['feedback']}

[STEP]
{state['step_count'] + 1} / {graph['max_steps']}

[SCENARIO]
{node['text']}

[CHALLENGE]
{node['challenge']}

[OPTIONS]
A. {node['options']['A']['text']}
B. {node['options']['B']['text']}
C. {node['options']['C']['text']}

[CURRENT METRICS]
Score: {score}
Time impact: {state['metrics']['time_cost']}
Audit risk: {state['metrics']['audit_risk']}
Administrative burden: {state['metrics']['admin_burden']}
Value-for-money risk: {state['metrics']['value_for_money_risk']}"""

def render_labyrinth_final_report(graph: dict, state: dict, last_choice: str=None, last_opt: dict=None) -> str:
    score = calculate_labyrinth_score(state)
    audit_label = get_risk_label(state['metrics']['audit_risk'])
    vfm_label = get_risk_label(state['metrics']['value_for_money_risk'])
    
    path_str = " → ".join(state["path"])
    choices_str = " → ".join(state["choices"])
    
    expert_log_str = ""
    for ev in state["events"]:
        expert_log_str += f"- Node {ev['node']}, Chose {ev['choice']}: {ev['expert_log']} (Feedback: {ev['feedback']})\n"
        
    feedback_prefix = ""
    if last_choice and last_opt:
        feedback_prefix = f"[YOUR CHOICE]\n{last_choice}\n\n[FEEDBACK]\n{last_opt['feedback']}\n\n"
        
    return f"""[SIMULATION MODE]
Professional Procurement Labyrinth
[SCENARIO_ID]
{state['scenario_id']}
[CURRENT_NODE]
END

{feedback_prefix}[FINAL REPORT]

[PATH TAKEN]
{path_str}

[CHOICES]
{choices_str}

[SCORE]
Final score: {score} / 100

[RISK SUMMARY]
Audit risk: {audit_label} ({state['metrics']['audit_risk']})
Value-for-money risk: {vfm_label} ({state['metrics']['value_for_money_risk']})
Time impact: {state['metrics']['time_cost']}
Administrative burden: {state['metrics']['admin_burden']}

[EXPERT REVIEW LOG]
{expert_log_str}
[DEBRIEF]
Review your path and expert log to identify areas where your choices increased audit risk or administrative burden.

[LIMITATION]
This is a professional training simulation. It is not legal advice and does not constitute a final legal assessment."""

def get_professional_training_log(state: dict) -> dict:
    return state

def expand_simulation_query(question: str) -> str:
    """Expands English simulation queries into Greek procurement terms for better RAG retrieval."""
    q = question.lower()
    expanded = question
    if "direct award" in q or "direct awards" in q:
        expanded += " απευθείας ανάθεση άρθρο 118 άρθρο 120 ν.4412/2016"
    if "negotiated procedure" in q:
        expanded += " διαπραγμάτευση χωρίς προηγούμενη δημοσίευση άρθρο 32 ν.4412/2016"
    if "urgent procurement" in q:
        expanded += " κατεπείγουσα ανάγκη διαδικασία διαπραγμάτευσης άρθρο 32"
    if "framework agreement" in q:
        expanded += " συμφωνία πλαίσιο δημόσιες συμβάσεις"
    return expanded


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
        print("[SIMULATION] mode: professional training", flush=True)
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
        q_clean = question.strip().lower()
        choice = extract_choice(q_clean)
        
        if choice:
            ctx = find_latest_labyrinth_context(history)
            scenario_id = ctx["scenario_id"] if ctx else None
            
            runtime_graphs = get_runtime_scenario_graphs()
            if scenario_id and scenario_id in runtime_graphs:
                state = replay_labyrinth_state(history, scenario_id)
                graph = runtime_graphs[scenario_id]
                node_data = graph["nodes"].get(state["current_node"])
                
                if node_data and choice in node_data["options"] and not state["finished"]:
                    opt = node_data["options"][choice]
                    
                    state["choices"].append(choice)
                    state["step_count"] += 1
                    
                    apply_labyrinth_option(state, opt)
                    
                    state["events"].append({
                        "node": state["current_node"],
                        "choice": choice,
                        "feedback": opt["feedback"],
                        "expert_log": opt["expert_log"]
                    })
                    
                    state["current_node"] = opt["next_node"]
                    state["path"].append(opt["next_node"])
                    
                    if state["current_node"] == "END" or state["step_count"] >= graph["max_steps"]:
                        state["finished"] = True
                        output = render_labyrinth_final_report(graph, state, choice, opt)
                    else:
                        output = render_labyrinth_step(graph, state, choice, opt)
                        
                    yield from stream_static_text(output, chunk_size=10, delay=0.01)
                    return
                
                
            # If it's a standalone A/B/C but not in a valid labyrinth context, don't fall back to legacy.
            recovery_msg = (
                "[SIMULATION MODE]\n"
                "Professional Procurement Labyrinth\n\n"
                "[STATE RECOVERY]\n"
                "The current labyrinth state could not be recovered from the conversation history.\n\n"
                "[NEXT STEP]\n"
                "Please restart the scenario with:\n"
                "give me a serious game about direct awards"
            )
            yield from stream_static_text(recovery_msg, chunk_size=10, delay=0.01)
            return
                
        is_labyrinth_trigger = any(k in q_clean for k in ["direct award", "απευθείας ανάθεση", "απευθείας αναθέσεις", "urgent", "urgency", "urgent procurement", "κατεπείγον", "κατεπείγουσα ανάγκη", "technical specifications", "specifications", "φωτογραφικές προδιαγραφές", "προδιαγραφές"])
        if is_labyrinth_trigger:
            scenario_id = select_labyrinth_scenario(q_clean)
            runtime_graphs = get_runtime_scenario_graphs()
            
            if scenario_id not in runtime_graphs:
                scenario_id = "direct_award_fragmentation"
                
            state = replay_labyrinth_state([], scenario_id)
            graph = runtime_graphs[scenario_id]
            output = render_labyrinth_start(graph, state)
            yield from stream_static_text(output, chunk_size=10, delay=0.01)
            return

        # Legacy fallback safety - NEVER process A/B/C here anymore
        q_clean_upper = q_clean.upper()
        if q_clean_upper == 'NEXT':
            pattern = SCENARIO_PATTERNS["general_risk"]
            output = render_professional_training_start(pattern)
            yield from stream_static_text(output, chunk_size=10, delay=0.01)
            return
        
        pattern = get_scenario_pattern(question)
        if is_start:
            output = render_professional_training_start(pattern)
            yield from stream_static_text(output, chunk_size=10, delay=0.01)
            return
        elif is_conclusion:
            sys_prompt = build_fallback_conclusion(pattern)
        else:
            sys_prompt = build_fallback_continue(pattern)
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
