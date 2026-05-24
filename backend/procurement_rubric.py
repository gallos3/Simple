"""
Procurement Rubric - Evaluation Logic for Serious Games
Defines the scoring criteria and domains for the OSCE-style report card.
"""

PROCUREMENT_RUBRIC = {
    "LEGAL_GROUNDS": [
        "Identified correct legal basis (e.g., Art. 32 of N.4412)",
        "Correctly cited relevant Case Law (ΕΑΔΗΣΥ/Curia)",
        "Analyzed the conditions for the chosen procedure"
    ],
    "PROCEDURAL_COMPLIANCE": [
        "Followed mandatory timelines (e.g., publication periods)",
        "Checked for necessary approvals (e.g., Financial Service)",
        "Verified technical specifications neutrality"
    ],
    "DECISION_MAKING": [
        "Reasoned the rejection/acceptance of a bidder",
        "Handled pre-judicial appeals correctly",
        "Balanced proportionality and transparency"
    ],
    "RISK_ASSESSMENT": [
        "Detected potential fragmentation (κατάτμηση)",
        "Identified conflict of interest risks",
        "Ensured equal treatment of bidders"
    ]
}

SCENARIO_TEMPLATES = {
    "DIRECT_AWARD_LIMIT": {
        "title": "Direct Award Threshold Challenge",
        "description": "A department wants to buy IT equipment worth 35,000€. They suggest splitting it into two 17,500€ contracts.",
        "correct_action": "Reject fragmentation and suggest a summary or open competition.",
        "rubric_key": "RISK_ASSESSMENT"
    },
    "TECH_SPECS_BIAS": {
        "title": "The 'Specific Brand' Trap",
        "description": "The technical department provided specs that match only one specific manufacturer's catalog.",
        "correct_action": "Request removal of brand names and use of 'or equivalent' (ή ισοδύναμο).",
        "rubric_key": "PROCEDURAL_COMPLIANCE"
    }
}

def evaluate_critical_errors(transcript_turns, checklist_results):
    """
    Deterministic check for critical failures.
    Example: If student approves fragmentation, that's a critical error.
    """
    errors = []
    
    # Heuristic check on transcript
    transcript_text = " ".join([t.get('text', '').lower() for t in transcript_turns if t.get('role') == 'user'])
    
    if "κατάτμηση" in transcript_text and ("ναι" in transcript_text or "εγκρίνω" in transcript_text):
        errors.append("Critical Error: Approved contract fragmentation (κατάτμηση).")
        
    return errors
