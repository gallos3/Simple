# audit_store.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import uuid
from typing import Any, Dict, Optional

# In-memory store: χάνεται σε restart (OK για MVP)
AUDIT_CASES: Dict[str, Dict[str, Any]] = {}


def create_audit_case(authority_name: str, year: str) -> str:
    audit_case_id = str(uuid.uuid4())
    AUDIT_CASES[audit_case_id] = {
        "audit_case_id": audit_case_id,
        "authority_name": authority_name,
        "year": year,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "created",  # created|running|done|error
        "progress": {"current": 0, "total": 4, "label": "created"},
        "results": {},  # "S1"..."S4"
        "errors": [],
    }
    global LAST_AUDIT_CASE_ID
    LAST_AUDIT_CASE_ID = audit_case_id
    return audit_case_id


def get_case(audit_case_id: str) -> Optional[Dict[str, Any]]:
    return AUDIT_CASES.get(audit_case_id)


def update_case(audit_case_id: str, **kwargs) -> None:
    case = AUDIT_CASES.get(audit_case_id)
    if not case:
        return
    case.update(kwargs)
# --- Simple single-user "last case" pointer (MVP) ---
LAST_AUDIT_CASE_ID: Optional[str] = None

def set_last_case_id(audit_case_id: str) -> None:
    global LAST_AUDIT_CASE_ID
    LAST_AUDIT_CASE_ID = audit_case_id

def get_last_case_id() -> Optional[str]:
    return LAST_AUDIT_CASE_ID
