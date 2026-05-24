# audit_runner.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple
import math

from audit_store import get_case, update_case
from database import execute_cypher
from config import BASE_DIR
import json


def _load_predefined_queries() -> Dict[int, Dict[str, Any]]:
    # cache-friendly: φορτώνει μία φορά ανά process
    if not hasattr(_load_predefined_queries, "_cache"):
        path = BASE_DIR / "predefined_queries.json"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "queries" in data:
            data = data["queries"]
        _load_predefined_queries._cache = {int(q["id"]): q for q in data}
    return _load_predefined_queries._cache


def _row_amount(row: Dict[str, Any]) -> float:
    return _safe_float(
        row.get("Ποσό")
        or row.get("ποσό")
        or row.get("Value")
        or row.get("Ποσό_")
    )


def _row_total(row: Dict[str, Any]) -> float:
    return _safe_float(row.get("Σύνολο") or row.get("σύνολο"))


def _safe_float(x: Any) -> float:
    try:
        if x is None:
            return 0.0
        return float(x)
    except Exception:
        return 0.0


def _compute_excess(amount: float, threshold: float) -> float:
    return max(0.0, amount - threshold)


def _run_query_id(qid: int, authority_name: str, year: str) -> List[Dict[str, Any]]:
    queries = _load_predefined_queries()
    q = queries.get(qid)
    if not q:
        return []

    cypher = q.get("query") or q.get("cypher", "")
    params = {"name": authority_name, "year": year}

    raw = execute_cypher(cypher, params=params, format_output=False)

    # execute_cypher μπορεί να επιστρέψει string σε error
    if isinstance(raw, str):
        return []
    return raw



def run_audit_S1_to_S4(audit_case_id: str) -> Dict[str, Any]:
    case = get_case(audit_case_id)
    if not case:
        raise ValueError("Unknown audit_case_id")

    authority_name = case["authority_name"]
    year = case["year"]

    update_case(
        audit_case_id,
        status="running",
        progress={"current": 0, "total": 4, "label": "starting"},
        results={},
        errors=[],
    )

    results: Dict[str, Any] = {}

    # -------------------------
    # S1: Contract-level > threshold
    # -------------------------
    update_case(audit_case_id, progress={"current": 1, "total": 4, "label": "S1"})
    s1_rows = []
    for qid, threshold in [(101, 30000.0), (102, 60000.0)]:
        rows = _run_query_id(qid, authority_name, year)
        print(f"[AUDIT] qid={qid} rows={len(rows)}")

        for r in rows:
            amount = _row_amount(r)
            s1_rows.append({
                "threshold_used": threshold,
                "excess": _compute_excess(amount, threshold),
                "row": r,
            })
    print(f"[AUDIT] S1 done authority={authority_name} year={year} findings={len(s1_rows)}")

    results["S1"] = {
        "subcheck_id": "S1_contract_over_threshold",
        "count": len(s1_rows),
        "findings": sorted(s1_rows, key=lambda x: x["excess"], reverse=True),
        "notes": [],
    }

    # -------------------------
    # S2: Sum by CPV > threshold
    # -------------------------
    update_case(audit_case_id, progress={"current": 2, "total": 4, "label": "S2"})
    s2_findings = []
    for qid, threshold in [(103, 30000.0), (104, 60000.0)]:
        rows = _run_query_id(qid, authority_name, year)
        for r in rows:
            total = _row_total(r)
            s2_findings.append({
                "threshold_used": threshold,
                "excess": _compute_excess(total, threshold),
                "group_key": {"CPV": r.get("CPV")},
                "row": r,
            })

    results["S2"] = {
        "subcheck_id": "S2_sum_by_cpv",
        "count": len(s2_findings),
        "findings": sorted(s2_findings, key=lambda x: x["excess"], reverse=True),
        "notes": [],
    }

    # -------------------------
    # S3: Sum by CPV5 > threshold
    # -------------------------
    update_case(audit_case_id, progress={"current": 3, "total": 4, "label": "S3"})
    s3_findings = []
    for qid, threshold in [(105, 30000.0), (106, 60000.0)]:
        rows = _run_query_id(qid, authority_name, year)
        for r in rows:
            total = _row_total(r)
            s3_findings.append({
                "threshold_used": threshold,
                "excess": _compute_excess(total, threshold),
                "group_key": {"CPV5": r.get("CPV5")},
                "row": r,
            })

    results["S3"] = {
        "subcheck_id": "S3_sum_by_cpv5",
        "count": len(s3_findings),
        "findings": sorted(s3_findings, key=lambda x: x["excess"], reverse=True),
        "notes": [],
    }

    # -------------------------
    # S4: Sum by Supplier > threshold (indicator)
    # -------------------------
    update_case(audit_case_id, progress={"current": 4, "total": 4, "label": "S4"})
    s4_findings = []
    for qid, threshold in [(107, 30000.0), (108, 60000.0)]:
        rows = _run_query_id(qid, authority_name, year)
        for r in rows:
            total = _row_total(r)
            s4_findings.append({
                "threshold_used": threshold,
                "excess": _compute_excess(total, threshold),
                "group_key": {"Ανάδοχος": r.get("Ανάδοχος") or r.get("ανάδοχος")},
                "row": r,
            })

    results["S4"] = {
        "subcheck_id": "S4_sum_by_supplier_indicator",
        "count": len(s4_findings),
        "findings": sorted(s4_findings, key=lambda x: x["excess"], reverse=True),
        "notes": [
            "S4 είναι ένδειξη (aggregation ανά ανάδοχο). Απαιτείται επιβεβαίωση ομοιότητας αντικειμένου από ελεγκτή."
        ],
    }

    update_case(audit_case_id, status="done", progress={"current": 4, "total": 4, "label": "done"}, results=results)
    return results
