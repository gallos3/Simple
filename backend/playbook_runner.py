# playbook_runner.py
from __future__ import annotations
from typing import Any, Dict, Optional

from entity_extractor import load_entity_cache, extract_entity_from_question, extract_year_from_question
from audit_store import create_audit_case, get_case
from audit_runner import run_audit_S1_to_S4

def _strip_playbook_words(q: str) -> str:
    bad = [
        "ελεγξε", "έλεγξε", "μη", "νομιμες", "νόμιμες",
        "αναθεσεις", "αναθέσεις", "για", "το", "την", "στο", "στη", "στον"
    ]
    out = q
    for w in bad:
        out = out.replace(w, " ")
    return " ".join(out.split())

def run_illegal_direct_awards_playbook(question: str, from_voice: bool = False) -> str:
    """
    Conversation-first runner.
    - απαιτεί: authority + year
    - τρέχει S1–S4 (predefined queries via audit_runner)
    - επιστρέφει summary ως plain text (chat friendly)
    """
    from entity_extractor import load_entity_cache, extract_entity_smart
    from engine import (
        disambiguate_authority_by_nuts,
        clear_pending_illegal_awards,
        set_pending_illegal_awards_clarification,
    )

    entity_cache = load_entity_cache()
    entity = extract_entity_smart(question, entity_cache)
    entity = disambiguate_authority_by_nuts(entity, question)



    year = extract_year_from_question(question, from_voice=from_voice)

    if not entity:
        clear_pending_illegal_awards()
        return (
            "Για να τρέξω τον έλεγχο **μη νόμιμων απευθείας αναθέσεων (S1–S4)**, "
            "γράψε την **πλήρη επωνυμία** της αναθέτουσας αρχής και το **έτος**.\n"
            "Παράδειγμα: «Έλεγξε για μη νόμιμες αναθέσεις το ΠΓΝΘ ΑΧΕΠΑ για το 2024»."
        )

    if entity.get("ambiguous"):
        set_pending_illegal_awards_clarification(
            waiting_for_full_authority_name=True,
            year=year or "",
            authority="",
            from_voice=from_voice,
        )
        return (
            "Υπάρχουν περισσότερες από μία αναθέτουσες αρχές με αυτό το όνομα. "
            "Παρακαλώ γράψε **ολόκληρη** την επωνυμία."
        )

    if not year:
        set_pending_illegal_awards_clarification(
            waiting_for_full_authority_name=False,
            year="",
            authority=entity["value"],
            from_voice=from_voice,
        )
        return "Για ποιο **έτος** θέλεις να τρέξω τον έλεγχο (π.χ. 2024);"

    clear_pending_illegal_awards()
    authority = entity["value"]

    audit_case_id = create_audit_case(authority, str(year))
    run_audit_S1_to_S4(audit_case_id)
    case = get_case(audit_case_id) or {}

    return format_illegal_awards_summary(case)


def format_illegal_awards_summary(case: Dict[str, Any]) -> str:
    results = (case.get("results") or {})

    def count(sid: str) -> int:
        try:
            return int((results.get(sid) or {}).get("count") or 0)
        except Exception:
            return 0

    s1 = count("S1")
    s2 = count("S2")
    s3 = count("S3")
    s4 = count("S4")

    authority = case.get("authority_name", "-")
    year = case.get("year", "-")

    return (
        f"**Έλεγχος ενδίξεων κατάτμησης/υπέρβασης ορίου (S1–S4)**\n"
        f"Αναθέτουσα: **{authority}**\n"
        f"Έτος: **{year}**\n\n"
        f"- **S1** Μονές υπερβάσεις ορίου (ανά σύμβαση): **{s1}**\n"
        f"- **S2** Άθροιση ανά CPV (υπέρβαση ορίου): **{s2}**\n"
        f"- **S3** Άθροιση ανά CPV-5 (υπέρβαση ορίου): **{s3}**\n"
        f"- **S4** Άθροιση ανά Ανάδοχο: **{s4}** *(ένδειξη — απαιτεί έλεγχο ομοιότητας αντικειμένου)*\n\n"
        f"Αν θέλεις λεπτομέρειες, πες: **S1**, **S2**, **S3** ή **S4**."
    )
