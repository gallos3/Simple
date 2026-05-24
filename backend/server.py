"""
Simple - Flask Server (OPTIMIZED - Single Load)

ΒΕΛΤΙΣΤΟΠΟΙΗΣΗ:
- Τα βαριά modules (legal_rag, LLM) φορτώνονται ΜΟΝΟ στο worker process
- Αποφεύγεται το διπλό φόρτωμα σε debug mode
"""

import os
import sys

# Fix Windows console encoding — must be FIRST before any other import
# that may print Greek text or emojis (cp1253 cannot encode them)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Force unbuffered output so all print() calls appear immediately in the terminal
os.environ['PYTHONUNBUFFERED'] = '1'

# =============================================================================
# DETECT IF WE'RE IN THE RELOADER'S CHILD PROCESS
# =============================================================================
# Σε Flask debug mode με reloader, ο server ξεκινά 2 processes:
# 1. Parent process - παρακολουθεί αλλαγές αρχείων
# 2. Child process (WERKZEUG_RUN_MAIN=true) - τρέχει το actual server
#
# Φορτώνουμε τα βαριά modules ΜΟΝΟ στο child process!

# Στα Windows ο reloader μπορεί να προκαλέσει "OSError: [WinError 6]" αν το
# terminal δεν έχει σωστό code page. Χρησιμοποίησε το start_all.bat που θέτει
# chcp 65001 πριν την εκκίνηση.
USE_RELOADER = False

IS_WORKER_PROCESS = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
# Φορτώνουμε τα βαριά modules αν είμαστε στο worker process Η αν ο reloader είναι κλειστός
SHOULD_LOAD_MODULES = IS_WORKER_PROCESS or not USE_RELOADER

# =============================================================================
# FLASK APP SETUP
# =============================================================================
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
#===============================================================================
#AUDIT
#===============================================================================
from audit_store import create_audit_case, get_case
from audit_runner import run_audit_S1_to_S4
@app.route("/audit/start", methods=["POST"])
def audit_start():
    data = request.get_json(force=True) or {}
    authority_name = (data.get("authority_name") or "").strip()
    year = (data.get("year") or "").strip()

    if not authority_name or not year:
        return jsonify({"error": "authority_name and year are required"}), 400

    audit_case_id = create_audit_case(authority_name, year)

    # MVP: τρέχει sync (αν θες async αργότερα, το βάζουμε σε background job)
    try:
        run_audit_S1_to_S4(audit_case_id)
    except Exception as e:
        case = get_case(audit_case_id) or {}
        case["status"] = "error"
        case.setdefault("errors", []).append(str(e))

    return jsonify({"audit_case_id": audit_case_id})

@app.route("/audit/results", methods=["GET"])
def audit_results():
    audit_case_id = request.args.get("audit_case_id", "").strip()
    case = get_case(audit_case_id)
    if not case:
        return jsonify({"error": "unknown audit_case_id"}), 404
    return jsonify(case)

# =============================================================================
# HEAVY MODULE LOADING - ΜΟΝΟ ΣΤΟ WORKER PROCESS
# =============================================================================
if SHOULD_LOAD_MODULES:
    print("\n[STARTUP] Worker process - loading modules...")
    
    # GraphRAG replaces legal_rag — no embedding model needed at startup
    from graph_rag import search_graph_corpus
    print("   [OK] graph_rag loaded (Cypher-based, no embedding model)")
    
    # NOTE: legal_rag background preload is DISABLED.
    # The system now uses graph_rag for all legal retrieval.
    # start_background_preload() caused colorama/errno-9 crash on Windows.

else:
    print("\n[STARTUP] Parent process - skipping module loading...")
    print("   (Modules will load in worker process after reloader starts)\n")

# =============================================================================
# CONFIG
# =============================================================================
from config import (
    UPLOAD_FOLDER,
    REPORTS_FOLDER,
    EXPORT_FOLDER,
    API_PORT,
    is_dangerous_query,
    LEGAL_PDFS_FOLDER,
    TEMPLATES_FOLDER,
)

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORTS_FOLDER, exist_ok=True)
os.makedirs(EXPORT_FOLDER, exist_ok=True)
os.makedirs(LEGAL_PDFS_FOLDER, exist_ok=True)
os.makedirs(TEMPLATES_FOLDER, exist_ok=True)

# =============================================================================
# STREAMING ENDPOINT
# =============================================================================
from streaming_endpoint import add_streaming_routes
add_streaming_routes(app)

# =============================================================================
# MAIN ENDPOINT - Ask Question
# =============================================================================
@app.route("/ask", methods=["POST"])
def ask():
    """Handle natural language questions."""
    from engine import answer_question  # Safe re-import (already loaded)
    
    data = request.get_json()
    question = data.get("question", "").strip()
    previous = data.get("previous_question", "").strip()
    from_voice = bool(data.get("from_voice"))
    role = data.get("role") or request.headers.get("X-User-Role")
    web_search_enabled = data.get("web_search_enabled", True)

    if not question:
        return jsonify({"error": "Άδεια ερώτηση."}), 400

    if is_dangerous_query(question):
        return jsonify({
            "result": "H entolh soy θεωρήθηκε επικίνδυνη και δεν εκτελέστηκε."
        }), 400

    print(f"\n[User] {question}")
    response = answer_question(
        question, 
        previous, 
        from_voice=from_voice, 
        role=role,
        web_search_enabled=web_search_enabled
    )

    if isinstance(response, dict):
        return jsonify(response)
    else:
        return jsonify({"result": response, "text": response})


# =============================================================================
# UPLOAD FILE
# =============================================================================
@app.route("/upload_file", methods=["POST"])
def upload_file():
    import pandas as pd
    
    if "file" not in request.files:
        return jsonify({"message": "Den brethhke arxeio."}), 400

    file = request.files["file"]
    filename = file.filename

    if filename == "":
        return jsonify({"message": "Den epilexthke arxeio."}), 400

    ext = filename.lower().split(".")[-1]

    if ext == "csv":
        save_path = os.path.join(str(UPLOAD_FOLDER), filename)
        file.save(save_path)
        print(f"[FILE] CSV uploaded: {save_path}")

        try:
            from database import ingest_csv_to_neo4j
            df = pd.read_csv(save_path, encoding="utf-8")
            ingest_csv_to_neo4j(df)
            return jsonify({"message": f"To CSV '{filename}' anebhke & fortothke sth Neo4j."})
        except ImportError:
            return jsonify({"message": f"To CSV '{filename}' apothikeythke."})
        except Exception as e:
            return jsonify({"message": f"Sfalma: {str(e)}"}), 500

    if ext == "pdf":
        save_path = os.path.join(str(LEGAL_PDFS_FOLDER), filename)
        file.save(save_path)
        print(f"[FILE] Legal PDF uploaded: {save_path}")

        try:
            # 1. Για μόνιμη αποθήκευση στο corpus.jsonl
            from legal_ingest import ingest_pdf_to_corpus
            ingest_pdf_to_corpus(save_path)
            
            # 2. Για άμεση χρήση στη μνήμη (Live RAG)
            from legal_rag import ingest_pdf
            num_chunks = ingest_pdf(save_path)
            
            return jsonify({
                "message": f"[PDF] Το PDF '{filename}' προστέθηκε στη γνώση του συστήματος ({num_chunks} αποσπάσματα). Μπορείς να ρωτήσεις τώρα!"
            })
        except Exception as e:
            print(f"[UPLOAD] Error: {e}")
            return jsonify({"message": f"[!] Σφάλμα: {str(e)}"}), 500

    if ext == "docx":
        save_path = os.path.join(str(TEMPLATES_FOLDER), filename)
        file.save(save_path)
        return jsonify({"message": f"[FILE] Το DOCX '{filename}' αποθηκεύτηκε."})

    return jsonify({"message": f"[!] Ο τύπος .{ext} δεν υποστηρίζεται."})


# =============================================================================
# EXPORT ENDPOINTS
# =============================================================================
@app.route("/export_docx")
def export_docx():
    from engine import generate_full_audit_report
    
    authority = request.args.get("authority", "")
    year = request.args.get("year", "2024")
    audit_order = request.args.get("audit_order_number", "")
    inspectors = request.args.get("inspectors", "")

    if not authority:
        return jsonify({"error": "Απαιτείται αναθέτουσα αρχή"}), 400

    try:
        filepath = generate_full_audit_report(authority, year, audit_order, inspectors)
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/export_summary")
def export_summary():
    from engine import run_illegal_award_checks_and_export_docx
    year = request.args.get("year", "2024")

    try:
        filepath = run_illegal_award_checks_and_export_docx(year)
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/latest_export")
def download_latest_export():
    from engine import get_latest_export_path
    path = get_latest_export_path()

    if not path or not os.path.exists(path):
        return "Den brethhke arxeio.", 404

    return send_file(path, as_attachment=True)


# =============================================================================
# STATIC FILES & HEALTH
# =============================================================================
@app.route("/reports/<path:filename>")
def download_report(filename):
    return send_from_directory(str(REPORTS_FOLDER), filename)

@app.route("/exports/<path:filename>")
def download_export(filename):
    return send_from_directory(str(EXPORT_FOLDER), filename)

@app.route("/health")
def health():
    return jsonify({"status": "ok", "message": "Simple API is running"})

@app.route("/submit_feedback", methods=["POST"])
def submit_feedback():
    """
    Endpoint for users to report an incorrect or unsatisfactory answer.
    Expects JSON: { "comment": "..." }
    """
    from debug_logger import save_feedback_report, get_last_trace
    data = request.get_json(force=True) or {}
    comment = data.get("comment", "No comment provided")
    
    try:
        report_path = save_feedback_report(comment)
        return jsonify({
            "status": "success",
            "message": "Feedback received and trace report saved.",
            "report_file": os.path.basename(report_path)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# =============================================================================
# HUMAN-IN-THE-LOOP (HITL) ENDPOINTS
# =============================================================================
@app.route("/hitl")
def hitl_dashboard():
    """Επιστρέφει το UI για την αξιολόγηση των PENDING_REVIEW"""
    return send_file(os.path.join(str(TEMPLATES_FOLDER), "hitl_dashboard.html"))

@app.route("/api/pending_reviews", methods=["GET"])
def api_pending_reviews():
    from database import get_session
    entity_type = request.args.get("entity", "Buyer")
    
    with get_session() as session:
        query = f"""
        MATCH (a:{entity_type})-[r:PENDING_REVIEW]->(b:{entity_type})
        OPTIONAL MATCH (a)-[:WON_BY|AWARDED_TO]-(awA)
        OPTIONAL MATCH (b)-[:WON_BY|AWARDED_TO]-(awB)
        RETURN id(a) as id1, a.name as name1, a.vat as vat1, count(DISTINCT awA) as count1,
               id(b) as id2, b.name as name2, b.vat as vat2, count(DISTINCT awB) as count2,
               r.score as score, id(r) as rel_id
        ORDER BY r.score DESC
        LIMIT 50
        """
        results = session.run(query)
        pairs = []
        for r in results:
            pairs.append({
                "id1": r["id1"], "name1": r["name1"], "vat1": r["vat1"], "count1": r["count1"],
                "id2": r["id2"], "name2": r["name2"], "vat2": r["vat2"], "count2": r["count2"],
                "score": r["score"], "rel_id": r["rel_id"]
            })
    return jsonify(pairs)

@app.route("/api/resolve_review", methods=["POST"])
def api_resolve_review():
    from database import get_session
    data = request.get_json()
    action = data.get("action")
    id1 = data.get("id1")
    id2 = data.get("id2")
    entity_type = data.get("entity", "Buyer")
    
    if not action or not id1 or not id2:
        return jsonify({"error": "Missing parameters"}), 400
        
    with get_session() as session:
        if action == "approve":
            # APOC Merge - node2 merges into node1
            query = f"""
            MATCH (a:{entity_type}), (b:{entity_type})
            WHERE id(a) = $id1 AND id(b) = $id2
            CALL apoc.refactor.mergeNodes([a, b], {{properties: 'combine', mergeRels: true}}) YIELD node
            RETURN node
            """
            session.run(query, {"id1": id1, "id2": id2})
            return jsonify({"status": "merged"})
            
        elif action == "reject":
            # Αφαίρεση του PENDING_REVIEW και προσθήκη REJECTED_MERGE
            query = f"""
            MATCH (a:{entity_type})-[r:PENDING_REVIEW]-(b:{entity_type})
            WHERE id(a) = $id1 AND id(b) = $id2
            DELETE r
            MERGE (a)-[:REJECTED_MERGE]->(b)
            """
            session.run(query, {"id1": id1, "id2": id2})
            return jsonify({"status": "rejected"})
            
    return jsonify({"error": "Invalid action"}), 400


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print(f"Simple - Procurement Audit Tool API running on port {API_PORT}")
    
    app.run(debug=True, port=API_PORT, host="0.0.0.0", use_reloader=USE_RELOADER)
from audit_store import AUDIT_CASES

@app.route("/_debug/audit_cases", methods=["GET"])
def debug_audit_cases():
    # Επιστρέφει μόνο ids και βασικά keys (όχι όλο το payload)
    ids = list(AUDIT_CASES.keys())
    last_id = ids[-1] if ids else None
    last = AUDIT_CASES.get(last_id) if last_id else None
    return jsonify({
        "count": len(ids),
        "last_id": last_id,
        "last_keys": list(last.keys()) if last else None,
        "last_result_keys": list((last.get("results") or {}).keys()) if last else None
    })
