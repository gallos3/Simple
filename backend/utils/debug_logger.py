import os
import json
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "debug_reports")

# In-memory storage for the last execution trace (per session/request simplified for MVP)
_LAST_TRACE: Dict[str, Any] = {}

def start_trace(question: str):
    """Initialize a new trace for a request."""
    global _LAST_TRACE
    _LAST_TRACE = {
        "trace_id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "question": question,
        "intent": None,
        "query_id": None,
        "cypher_template": None,
        "cypher_executed": None,
        "db_results_raw": None,
        "llm_response": None,
        "metadata": {}
    }
    return _LAST_TRACE["trace_id"]

def update_trace(**kwargs):
    """Update fields in the current trace."""
    global _LAST_TRACE
    _LAST_TRACE.update(kwargs)

def get_last_trace():
    """Retrieve the last captured trace."""
    return _LAST_TRACE

def save_feedback_report(user_comment: str, trace: Optional[Dict] = None):
    """
    Combine trace with user feedback and save to an AI-readable file.
    """
    if not os.path.exists(REPORTS_DIR):
        os.makedirs(REPORTS_DIR)

    report_data = trace if trace else _LAST_TRACE
    
    # Add feedback info
    final_report = {
        "report_type": "USER_FEEDBACK_ERROR",
        "user_comment": user_comment,
        "execution_context": report_data
    }

    filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.json"
    filepath = os.path.join(REPORTS_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(final_report, f, ensure_ascii=False, indent=2)

    return filepath
