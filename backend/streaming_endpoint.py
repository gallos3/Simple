import json
import os
import re
import time
from datetime import datetime
from debug_logger import start_trace, update_trace
from typing import Any, Dict, List, Optional, Union

from flask import Flask, Response, request, stream_with_context, jsonify
from flask_cors import CORS

# Imports from other modules
from engine import (
    detect_intent,
    _execute_matched_query,
    _handle_no_match,
    _maybe_attach_followup,
    PENDING_FOLLOWUP,
    _is_yes,
    _is_no,
    _clear_followup,
    _execute_followup,
    detect_playbook_intent,
    clear_pending_illegal_awards,
    merge_pending_illegal_awards_question,
    merge_pending_year_reply,
)
from entity_extractor import (
    extract_entity_smart,
    extract_year_from_question,
    load_entity_cache,
    format_authority_name,
    get_article,
    extract_article_from_question,
    normalize_greek
)
from graph_rag import search_graph_corpus
from report_generator import run_compliance_checks, generate_full_audit_report
from llm_interface import answer_general_question, answer_general_question_stream
from agent_modules import (
    generate_legal_answer_stream,
    generate_data_risk_answer_stream,
    generate_mixed_audit_answer_stream
)
from database import get_all_predefined_queries, execute_cypher, extract_graph_elements
from query_matcher import get_query_match, detect_output_type
from web_search import search_legal_web, search_general_web
from social_handler import handle_social_query

def create_sse_event(event_type: str, data: Any) -> str:
    """Formats a message as an SSE event for the frontend."""
    payload = {"type": event_type}
    if event_type == "start":
        payload["intent"] = data.get("intent", "") if isinstance(data, dict) else ""
    elif event_type == "token":
        payload["content"] = data
    elif event_type == "action":
        payload["data"] = data
    elif event_type == "error":
        payload["content"] = str(data)
    
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def stream_text_chunks(text: str, chunk_size: int = 4, delay: float = 0.02):
    """Yields text in chunks to simulate typing."""
    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        yield create_sse_event("token", chunk)
        if delay > 0:
            time.sleep(delay)

def add_streaming_routes(app: Flask):
    """Registers the ask_stream endpoint."""
    
    @app.route("/ask_stream", methods=["POST", "OPTIONS"])
    def ask_stream():
        if request.method == "OPTIONS":
            response = Response()
            response.headers['Access-Control-Allow-Origin'] = '*'
            response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
            response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
            return response

        data = request.get_json(force=True) or {}
        question = (data.get("question") or "").strip()
        from_voice = bool(data.get("from_voice"))
        role = data.get("role") or request.headers.get("X-User-Role")
        web_search_enabled = data.get("web_search_enabled", True)
        history = data.get("history", [])

        if not question:
            return jsonify({"error": "No question provided"}), 400

        def generate():
            nonlocal question
            import engine
            full_answer_str = ""
            
            # === 0.5) Pending Auth Flow ===
            if engine.PENDING_AUTH.get("active"):
                if question.strip() == "EADHSY":
                    engine.IS_AUTHENTICATED_AUDITOR = True
                    engine.PENDING_AUTH["active"] = False
                    yield create_sse_event("start", {"intent": "general"})
                    msg = "[OK] Επιτυχής ταυτοποίηση Ελεγκτή! Ξεκινά η δημιουργία της έκθεσης...\n\n"
                    yield from stream_text_chunks(msg, chunk_size=6, delay=0.03)
                    
                    authority = engine.PENDING_AUTH.get("authority")
                    year = engine.PENDING_AUTH.get("year", "2024")
                    
                    import os
                    from config import API_HOST, API_PORT
                    API_BASE_URL = f"http://{API_HOST}:{API_PORT}"
                    try:
                        filepath = generate_full_audit_report(authority, year)
                        filename = os.path.basename(filepath)
                        download_url = f"{API_BASE_URL}/reports/{filename}"
                        link_msg = f"[DOWNLOAD] [Κατέβασε την έκθεση]({download_url})"
                        
                        action_data = {
                            "action": "report_generated",
                            "filepath": filename,
                            "download_url": download_url,
                            "text": link_msg
                        }
                        yield create_sse_event("action", action_data)
                        yield from stream_text_chunks(link_msg, chunk_size=6, delay=0.02)
                    except Exception as e:
                        err_msg = f"[!] Σφάλμα κατά τη δημιουργία της έκθεσης: {str(e)}"
                        yield create_sse_event("token", err_msg)
                    yield create_sse_event("end", {})
                    return
                else:
                    engine.PENDING_AUTH["active"] = False
                    yield create_sse_event("start", {"intent": "general"})
                    msg = "[!] Λάθος κωδικός. Η διαδικασία δημιουργίας έκθεσης ακυρώθηκε."
                    yield from stream_text_chunks(msg, chunk_size=6, delay=0.03)
                    yield create_sse_event("end", {})
                    return

            # === 1) Pending follow-up flow ===
            if PENDING_FOLLOWUP.get("active"):
                if _is_yes(question):
                    yield create_sse_event("start", {"intent": "followup"})
                    try:
                        followup_answer = _execute_followup()
                    except Exception as e:
                        followup_answer = f"Σφάλμα: {e}"

                    if isinstance(followup_answer, dict):
                        yield create_sse_event("action", followup_answer)
                    else:
                        yield from stream_text_chunks(str(followup_answer), chunk_size=4, delay=0.03)
                    yield create_sse_event("end", {})
                    return

                if _is_no(question):
                    _clear_followup()
                    yield create_sse_event("start", {"intent": "followup_declined"})
                    msg = "Εντάξει. Πες μου τι άλλο θα ήθελες να ελέγξουμε."
                    yield from stream_text_chunks(msg, chunk_size=4, delay=0.03)
                    yield create_sse_event("end", {})
                    return
                _clear_followup()

            # === 1.5) Year-only reply after year prompt → merge with prior question ===
            merged_year_q = merge_pending_year_reply(question, history)
            if merged_year_q != question:
                question = merged_year_q
                print(f"[SSE] Reconstructed question: {question}", flush=True)

            # === 2) PLAYBOOK ROUTING ===
            try:
                playbook_id = detect_playbook_intent(question)
                if playbook_id == "illegal_direct_awards":
                    clear_pending_illegal_awards()
                    yield create_sse_event("start", {"intent": "playbook_illegal_direct_awards"})
                    q_lower = question.lower()
                    is_batch = any(k in q_lower for k in ["συνολική", "συνολικη", "όλες", "ολες", "όλοι", "ολοι", "συγκεντρωτική", "συγκεντρωτικη"])
                    
                    if is_batch:
                        import os
                        from config import API_HOST, API_PORT
                        from report_generator import run_illegal_award_checks_and_export_docx
                        year_batch = extract_year_from_question(question, from_voice=from_voice) or "2024"
                        try:
                            filepath = run_illegal_award_checks_and_export_docx(year_batch)
                            filename = os.path.basename(filepath)
                            download_url = f"http://{API_HOST}:{API_PORT}/reports/{filename}"
                            msg = f"[OK] Δημιουργήθηκε συνολική έκθεση μη νόμιμων αναθέσεων για το {year_batch}.\n\n[DOWNLOAD] [Κατέβασε την έκθεση]({download_url})"
                            yield create_sse_event("action", {"action": "report_generated", "filepath": filename, "download_url": download_url, "text": msg})
                            yield from stream_text_chunks(msg, chunk_size=6, delay=0.02)
                        except Exception as e:
                            yield create_sse_event("token", f"[!] Σφάλμα: {str(e)}")
                    else:
                        from playbook_runner import run_illegal_direct_awards_playbook
                        result_text = run_illegal_direct_awards_playbook(question, from_voice=from_voice)
                        yield from stream_text_chunks(result_text, chunk_size=6, delay=0.01)
                    yield create_sse_event("end", {})
                    return

                # --- TRACE START ---
                start_trace(question)
                update_trace(history=history[-5:] if history else [])
                # -------------------

                merged_illegal = merge_pending_illegal_awards_question(question, from_voice)
                if merged_illegal:
                    yield create_sse_event("start", {"intent": "playbook_illegal_direct_awards"})
                    from playbook_runner import run_illegal_direct_awards_playbook
                    result_text = run_illegal_direct_awards_playbook(merged_illegal, from_voice=from_voice)
                    yield from stream_text_chunks(result_text, chunk_size=6, delay=0.01)
                    yield create_sse_event("end", {})
                    return
            except Exception as e:
                print(f"[SSE][PLAYBOOK] error: {e}")

            # Special case for case details
            q_clean = question.strip().lower()
            if q_clean in {"s1", "s2", "s3", "s4"}:
                from audit_store import get_last_case_id, get_case
                case_id = get_last_case_id()
                if case_id:
                    case = get_case(case_id) or {}
                    text = f"Case: {case_id}\nAvailable results: {list((case.get('results') or {}).keys())}\nΖήτησες: {q_clean.upper()}"
                    yield create_sse_event("start", {"intent": "playbook_detail"})
                    yield from stream_text_chunks(text, chunk_size=6, delay=0.01)
                    yield create_sse_event("end", {})
                    return

            # === 2.5) Normal Intent Detection ===
            intent = detect_intent(question, history)

            # === Early graph-type detection (before entity extraction) ===
            # Normalize accents so "περισσότερες" matches "περισσοτερ"
            q_norm = normalize_greek(question)  # removes accents, lowercases
            is_graph_request = any(k in q_norm for k in [
                "γραφημα", "γραφου", "graph", "δικτυο", "γραφο"
            ])
            is_cpv_query = bool(
                re.search(r'cpv\s*\d{4,8}\b', q_norm, re.IGNORECASE) or 
                re.search(r'\b\d{8}\b', question)  # Only 8-digit standalone numbers are CPV codes
            )
            is_top_company_graph = (
                is_graph_request
                and any(k in q_norm for k in ["εταιρε", "αναδοχ"])
                and any(k in q_norm or k in question.lower() for k in ["περισσοτερ", "πληθος", "max", "top"])
            )

            # Override intent to data_simple for graph queries (detect_intent can't see these)
            if is_top_company_graph or (is_cpv_query and is_graph_request) or is_graph_request:
                intent = "data_simple"
                print(f"[SSE] Intent overridden to data_simple (graph request detected)", flush=True)

            # Optimization: Only extract entity for intents that actually need it
            # Skip entity extraction entirely for graph-only queries
            entity = None
            if intent in ("data_simple", "data_risk", "mixed_legal_data", "market_diagnostic", "report"):
                if not is_top_company_graph:
                    entity_cache = load_entity_cache()
                    entity = extract_entity_smart(question, entity_cache)
                
            year = extract_year_from_question(question, from_voice=from_voice)

            # If we found an entity, CPV detection was likely a false positive (year number)
            if entity and is_cpv_query and not re.search(r'cpv', question, re.IGNORECASE):
                is_cpv_query = False

            print(f"[SSE] Intent: {intent}, Entity: {entity}, Year: {year}, CPV: {is_cpv_query}, TopCo: {is_top_company_graph}, Graph: {is_graph_request}", flush=True)
            update_trace(intent=intent, entity=entity, year=year, is_graph=is_graph_request)


            # === 3) Social intent ===
            if intent == "social":
                user_name = None
                if history:
                    for msg in history:
                        if msg.get("role") == "user" and "με λενε" in msg.get("text", "").lower():
                            user_name = msg.get("text").lower().replace("με λενε", "").strip()
                            break
                social_resp = handle_social_query(question, user_name=user_name)
                if social_resp:
                    yield create_sse_event("start", {"intent": "social"})
                    yield from stream_text_chunks(social_resp, chunk_size=4, delay=0.02)
                    yield create_sse_event("end", {})
                    return

            # === 4) Disambiguation check ===
            if intent in ("data_simple", "data_risk", "mixed_legal_data", "market_diagnostic", "report") and entity and entity.get("ambiguous"):
                yield create_sse_event("start", {"intent": "general"})
                time.sleep(0.1)
                alts = entity["alternatives"]
                msg = "Βρήκα πολλές πιθανές αναθέτουσες αρχές:\n\n"
                for i, alt in enumerate(alts[:5], 1):
                    msg += f"{i}. {format_authority_name(alt)}\n"
                msg += "\nΠοια εννοείς;"
                yield from stream_text_chunks(msg, chunk_size=6, delay=0.03)
                yield create_sse_event("end", {})
                return

            # 🆕 YEAR PROMPT (if missing) - Only for simple data and reports, NOT for graph queries
            if intent in ("data_simple", "report") and not year:
                # Bypass year prompt for CPV, graph queries, and top-N aggregate queries (no year needed)
                # FIX: top-N queries like "top 10 εταιρείες" are system-wide and don't need a year
                is_top_n_query = not entity and any(k in normalize_greek(question) or k in question.lower() for k in ["top", "περισσοτερ", "κορυφ", "πρωτ"])
                if not is_cpv_query and not is_graph_request and not is_top_n_query:
                    yield create_sse_event("start", {"intent": "general"})
                    yield create_sse_event("token", "Για ποιο **έτος** θέλεις να τρέξω τον έλεγχο (π.χ. 2024);")
                    yield create_sse_event("end", {})
                    return


            # FIX: Use the actual intent to ensure the frontend renders the correct component.
            yield create_sse_event("start", {"intent": intent})
            
            # For diagnostic/simulation intents, we add a small delay and a thinking message
            if intent in ("mixed_legal_data", "market_diagnostic", "procurement_simulation", "procurement_report_card"):
                time.sleep(0.1)


            try:
                # ============ LEGAL ============
                if intent == "legal":
                    print(f"[SSE][LEGAL] GraphRAG search for: {question}", flush=True)
                    rag_query = question
                    legal_passages = search_graph_corpus(rag_query)
                    web_results = search_legal_web(question) if web_search_enabled else ""
                    context = legal_passages + ([f"Web Context:\n{web_results}"] if web_results else [])
                    for token in generate_legal_answer_stream(question, context):
                        full_answer_str += token
                        yield create_sse_event("token", token)

                # ============ SIMULATION ============
                elif intent == "procurement_simulation":
                    from procurement_simulation import stream_simulation
                    yield create_sse_event("action", {"action": "start_simulation", "text": ""})
                    
                    # NOTE: We intentionally skip RAG for simulations to avoid loading
                    # the SentenceTransformer embedding model in parallel with the LLM,
                    # which causes OOM (os error 1455) on memory-constrained machines.
                    # The simulation system prompts already contain full legal context.
                    rag_ctx = ""
                        
                    for token in stream_simulation(question, history, rag_ctx):
                        full_answer_str += token
                        yield create_sse_event("token", token)
                        
                    # ----------------------------------------------------
                    # REPORT CARD (Φύλλο Αξιολόγησης) στο τέλος του σεναρίου
                    # ----------------------------------------------------
                    from procurement_simulation import _count_student_turns, MAX_TURNS, generate_report_card
                    is_start = any(w in question.lower() for w in ["start", "ξεκίνα", "σεναριο", "σενάριο", "παιχνίδι", "εκπαίδευση", "scenario", "simulation", "new"])
                    student_turns = _count_student_turns(history)
                    
                    if (not is_start) and (student_turns >= MAX_TURNS):
                        yield create_sse_event("token", "\n\n---\n\n(ΑΝΑΜΟΝΗ) _Δημιουργία τελικού Φύλλου Αξιολόγησης..._\n\n")
                        
                        try:
                            # Evaluate the full transcript (history + the latest question)
                            full_eval_history = history + [{"role": "user", "text": question}]
                            report_json_str = generate_report_card(full_eval_history)
                            import json
                            report = json.loads(report_json_str)
                            
                            md_report = f"### 📋 Φύλλο Αξιολόγησης (Report Card)\n\n"
                            md_report += f"| Τομέας Αξιολόγησης | Βαθμολογία |\n"
                            md_report += f"| :--- | :--- |\n"
                            md_report += f"| ⚖️ Νομική Γνώση | **{report.get('Legal_Knowledge', 'N/A')}/100** |\n"
                            md_report += f"| ⚠️ Εκτίμηση Κινδύνου | **{report.get('Risk_Assessment', 'N/A')}/100** |\n"
                            md_report += f"| 🧠 Λήψη Αποφάσεων | **{report.get('Decision_Making', 'N/A')}/100** |\n"
                            md_report += f"| 🏆 **Συνολικός Βαθμός** | **{report.get('Overall_Grade', 'N/A')}/100** |\n\n"
                            md_report += f"**Σύνοψη**: {report.get('Summary', '')}\n\n"
                            
                            mistakes = report.get('Key_Mistakes', [])
                            if mistakes:
                                md_report += "**Βασικά Λάθη**:\n"
                                if isinstance(mistakes, list):
                                    for m in mistakes:
                                        md_report += f"- {m}\n"
                                else:
                                    md_report += f"- {mistakes}\n"
                                    
                            md_report += f"\n**Σύσταση Μελέτης**: {report.get('Recommendation', '')}\n"
                            
                            for chunk in stream_text_chunks(md_report, chunk_size=8, delay=0.01):
                                yield chunk
                                
                        except Exception as e:
                            print(f"[REPORT CARD ERROR] {e}")
                            yield create_sse_event("token", f"\n[!] Σφάλμα κατά τη δημιουργία αξιολόγησης: {str(e)}")


                # ============ MIXED LEGAL DATA (Hybrid Diagnosis) ============
                elif intent in ("mixed_legal_data", "market_diagnostic"):
                    if not entity:
                        yield create_sse_event("token", "**Ανάλυση Αγοράς (Market Diagnosis)**\n\n_Υπολογισμός Δεικτών..._\n\n")
                        from agentic_loop import tool_calculate_vcd, tool_calculate_entropy, tool_calculate_market_typology, extract_cpv_from_nl
                        
                        cpv = extract_cpv_from_nl(question)
                        params = f"{year or ''}, {cpv or ''}"
                        
                        try:
                            vcd_res = tool_calculate_vcd(params)
                            yield from stream_text_chunks(vcd_res + "\n\n", chunk_size=4, delay=0.01)
                            
                            ent_res = tool_calculate_entropy(params)
                            yield from stream_text_chunks(ent_res + "\n\n", chunk_size=4, delay=0.01)
                            
                            typ_res = tool_calculate_market_typology(params)
                            yield from stream_text_chunks(typ_res + "\n\n", chunk_size=4, delay=0.01)
                            
                            ici_note = "ℹ️ Ο δείκτης **ICI (Institutional Capture Index)** υπολογίζεται ανά Αναθέτουσα Αρχή. Για να δείτε τον δείκτη ICI, παρακαλώ ζητήστε διάγνωση για συγκεκριμένο φορέα (π.χ. 'διάγνωση για το ΑΧΕΠΑ')."
                            yield from stream_text_chunks(ici_note + "\n", chunk_size=4, delay=0.01)
                            
                        except Exception as e:
                            yield create_sse_event("token", f"Σφάλμα Υπολογισμού: {str(e)}")
                    else:
                        yield create_sse_event("token", "**Πόρισμα Διαγνωστικού Ελέγχου**\n\n")
                        from diagnostic_engine import calculate_full_diagnostics, get_diagnostic_reasoning
                        from agent_modules import generate_mixed_audit_answer_stream
                        
                        # 1. Legal Search via GraphRAG (no embedding model needed)
                        search_q = f"{question} παραβάσεις απευθείας ανάθεσης όρια ν.4412/2016"
                        passages = search_graph_corpus(search_q)
                        
                        # 2. Calculate Metrics (Fountoukidis)
                        # Determine authority and CPV domain
                        cpv_domain = None
                        authority_name = None
                        if entity:
                            if entity.get("label") == "CPV":
                                cpv_domain = entity.get("value")
                                print(f"[DEBUG] Passing CPV to diagnostics: {cpv_domain}")
                            else:
                                authority_name = entity.get("value")
                        # Fallback: ensure authority_name is set when not CPV
                        if not authority_name:
                            authority_name = None
                        diag_data = calculate_full_diagnostics(authority_name, year, cpv_domain=cpv_domain)
                        diagnosis_text = get_diagnostic_reasoning(diag_data)

                        # 3. Stream Hybrid Answer (Metrics + Law + LLM)
                        for token in generate_mixed_audit_answer_stream(
                            question, entity["value"], year, {}, passages, diag_data, diagnosis_text
                        ):
                            full_answer_str += token
                            yield create_sse_event("token", token)

                # ============ REPORT ============
                elif intent == "report":
                    if not entity:
                        yield create_sse_event("token", "[?] Δεν κατάφερα να αναγνωρίσω την αναθέτουσα αρχή.")
                    else:
                        authority = entity["value"]
                        import engine
                        if not engine.IS_AUTHENTICATED_AUDITOR:
                            engine.PENDING_AUTH.update({"active": True, "authority": authority, "year": year})
                            msg = "(ΤΑΥΤΟΠΟΙΗΣΗ) Απαιτείται επιβεβαίωση ιδιότητας Ελεγκτή. Παρακαλώ εισάγετε τον κωδικό πρόσβασης:"
                            yield from stream_text_chunks(msg, chunk_size=6, delay=0.03)
                        else:
                            from config import API_HOST, API_PORT
                            filepath = generate_full_audit_report(authority, year)
                            filename = os.path.basename(filepath)
                            download_url = f"http://{API_HOST}:{API_PORT}/reports/{filename}"
                            msg = f"(ΕΝΤΑΞΕΙ) Δημιουργήθηκε έκθεση ελέγχου για **{authority}** ({year}).\n\n[ΚΑΤΕΒΑΣΜΑ] [Κατέβασε την έκθεση]({download_url})"
                            yield create_sse_event("action", {"action": "report_generated", "filepath": filename, "download_url": download_url, "text": msg})
                            yield from stream_text_chunks(msg, chunk_size=6, delay=0.02)

                # ============ DATA RISK ============
                elif intent == "data_risk":
                    if not entity:
                        yield create_sse_event("token", "Ποια αρχή εννοείς;")
                    else:
                        compliance = run_compliance_checks(entity["value"], year)
                        full_answer_str = ""
                        for token in generate_data_risk_answer_stream(question, entity["value"], year, compliance):
                            full_answer_str += token
                            yield create_sse_event("token", token)
                        answer_with_followup = _maybe_attach_followup(question, entity, year, full_answer_str, intent="data_risk")
                        if isinstance(answer_with_followup, str) and len(answer_with_followup) > len(full_answer_str):
                            yield from stream_text_chunks(answer_with_followup[len(full_answer_str):], chunk_size=6, delay=0.03)

                # ============ DATA SIMPLE ============
                elif intent == "data_simple":
                    queries = get_all_predefined_queries()
                    
                    # Graph routing using pre-computed flags
                    matched_query = None
                    if is_cpv_query and is_graph_request:
                        from database import get_predefined_query
                        matched_query = get_predefined_query(502)
                    elif is_top_company_graph:
                        from database import get_predefined_query
                        matched_query = get_predefined_query(503)
                    elif entity and is_graph_request:
                        from database import get_predefined_query
                        matched_query = get_predefined_query(504)
                    else:
                        from query_matcher import get_query_match
                        matched_query, _ = get_query_match(question, queries, has_entity=bool(entity)) or (None, 0)
                        
                    if matched_query:
                        update_trace(query_id=matched_query.get("id"), cypher_template=matched_query.get("query"))
                        
                    base_answer = _execute_matched_query(matched_query, entity, year, question) if matched_query else _handle_no_match(question, entity, year)
                    
                    # Normalize article
                    if isinstance(base_answer, str) and entity:
                        user_article = extract_article_from_question(question, entity["value"]) or get_article(entity["value"])
                        short_name = format_authority_name(entity["value"])
                        if user_article:
                            base_answer = re.sub(r"(Ο|Η|Το)\s+«[^»]+»\s+(έχει|είχε)", f"{user_article} «{short_name}» \\2", base_answer)
                            base_answer = re.sub(r"Η αναθέτουσα αρχή «[^»]+»", f"{user_article} «{short_name}»", base_answer)
                    
                    answer = _maybe_attach_followup(question, entity, year, base_answer, intent="data_simple")
                    if isinstance(answer, dict):
                        yield create_sse_event("action", answer)
                    else:
                        yield from stream_text_chunks(str(answer), chunk_size=6, delay=0.03)

                # ============ GENERAL ============
                else:
                    # Try web search first for factual questions
                    web_context = ""
                    if web_search_enabled:
                        print(f"[SSE][GENERAL] Web search for: {question}", flush=True)
                        web_context = search_general_web(question)
                    
                    if web_context:
                        # Web found results — stream them directly (no LLM needed)
                        print(f"[SSE][GENERAL] Web results found, streaming directly", flush=True)
                        yield from stream_text_chunks(web_context, chunk_size=6, delay=0.02)
                        full_answer_str = web_context
                    else:
                        # No web results — fall back to LLM
                        for token in answer_general_question_stream(question):
                            full_answer_str += token
                            yield create_sse_event("token", token)

                yield create_sse_event("end", {})
                update_trace(llm_response=full_answer_str)
            except Exception as e:
                import traceback
                traceback.print_exc()
                yield create_sse_event("error", str(e))

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'text/event-stream; charset=utf-8'
            }
        )

    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        return response
