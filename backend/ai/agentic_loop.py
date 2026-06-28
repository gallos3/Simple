"""
Simple Federated - Custom ReAct Agent Loop
Υλοποιεί το μοτίβο Reason + Act (ReAct) χωρίς εξωτερικά frameworks (π.χ. LangChain).
"""

import re
from typing import List, Dict, Any, Callable, Tuple
from ai.llm_interface import call_llm

class Tool:
    def __init__(self, name: str, description: str, func: Callable[[str], str]):
        self.name = name
        self.description = description
        self.func = func

class ReActAgent:
    def __init__(self, tools: List[Tool], max_iterations: int = 8):
        self.tools = {t.name: t for t in tools}
        self.max_iterations = max_iterations
        self.tool_descriptions = "\n".join([f"- {t.name}: {t.description}" for t in tools])
        
        self.system_prompt = f"""Είσαι ένας Έξυπνος Νομικός και Ελεγκτικός Πράκτορας (Agent). 
Πρέπει να απαντήσεις στην ερώτηση του χρήστη με ακρίβεια και τεκμηρίωση.
Έχεις πρόσβαση στα παρακάτω εργαλεία:

{self.tool_descriptions}

Για να απαντήσεις, ΠΡΕΠΕΙ ΑΥΣΤΗΡΑ να ακολουθήσεις το εξής format:

Thought: [Η σκέψη σου για το τι πρέπει να κάνεις επόμενο]
Action: [Το όνομα του εργαλείου που θα χρησιμοποιήσεις, ΠΡΕΠΕΙ να είναι ένα από τα: {', '.join(self.tools.keys())}]
Action Input: [Τα ορίσματα για το εργαλείο. Π.χ. αν είναι αναζήτηση, γράψε το κείμενο αναζήτησης]

Αφού χρησιμοποιήσεις ένα εργαλείο, θα λάβεις ένα "Observation".
Αν έχεις συλλέξει αρκετές πληροφορίες για να απαντήσεις οριστικά, γράψε:

Thought: [Γνωρίζω πλέον την απάντηση]
Final Answer: [Η τελική σου, εμπεριστατωμένη απάντηση προς τον χρήστη]

ΠΡΟΣΟΧΗ: Κάνε ΕΝΑ (1) βήμα τη φορά. ΜΗΝ γράφεις Observation μόνος σου, περίμενε το σύστημα να στο δώσει."""

    def run(self, question: str) -> str:
        prompt = f"Ερώτηση Χρήστη: {question}\n\n"
        scratchpad = ""
        
        for i in range(self.max_iterations):
            current_prompt = f"{prompt}Ιστορικό Σκέψης:\n{scratchpad}\nΤι κάνεις τώρα;"
            
            # Κλήση στο LLM (σταματάμε στο "Observation:" για να μην το κάνει hallucinate)
            response = call_llm(
                current_prompt, 
                max_tokens=300, 
                temperature=0.1, 
                system_prompt=self.system_prompt
            )
            
            # Αν υπάρχει Final Answer, τερματίζουμε
            final_answer_match = re.search(r"Final Answer:(.*)", response, re.DOTALL | re.IGNORECASE)
            if final_answer_match:
                return final_answer_match.group(1).strip()
                
            # Ψάχνουμε για Action και Action Input
            action_match = re.search(r"Action:\s*(.*?)\n", response, re.IGNORECASE)
            action_input_match = re.search(r"Action Input:\s*(.*)", response, re.IGNORECASE)
            
            if action_match and action_input_match:
                action = action_match.group(1).strip()
                action_input = action_input_match.group(1).strip()
                
                scratchpad += f"\n{response}\n"
                
                if action in self.tools:
                    print(f"\n[Agent Action] 🛠️ Calling {action}('{action_input}')")
                    try:
                        observation = self.tools[action].func(action_input)
                    except Exception as e:
                        observation = f"Σφάλμα κατά την εκτέλεση του εργαλείου: {e}"
                else:
                    observation = f"Το εργαλείο '{action}' δεν υπάρχει. Διαθέσιμα: {', '.join(self.tools.keys())}"
                
                print(f"[Agent Observation] 👁️ {str(observation)[:150]}...\n")
                scratchpad += f"Observation: {observation}\n"
            else:
                # Αν δεν ακολούθησε το format
                if "Thought:" in response and not "Action:" in response:
                    # Μπορεί απλά να δίνει κατευθείαν απάντηση
                    return response.replace("Thought:", "").strip()
                
                scratchpad += f"\n{response}\nObservation: Πρέπει να γράψεις Action και Action Input, ή Final Answer.\n"

        return "Απέτυχα να βρω την απάντηση στα όρια των προσπαθειών μου."

# -----------------------------------------------------------
# DEFINITION OF TOOLS
# -----------------------------------------------------------

def tool_search_legal(query: str) -> str:
    from rag.legal_rag import search_legal_corpus
    passages = search_legal_corpus(query, k=3)
    if not passages:
        return "Δεν βρέθηκε κάτι σχετικό στη νομοθεσία."
    return "\n---\n".join(passages)

def tool_get_compliance(authority: str) -> str:
    from analytics.diagnostic_engine import generate_minimal_audit_report
    # Για το tool δεχόμαστε απλά authority (και ίσως year, θα το αφήσουμε generic για τώρα)
    # Αφαιρούμε quotes αν έβαλε ο agent
    authority = authority.replace('"', '').replace("'", "")
    try:
        report = generate_minimal_audit_report(authority, None)
        return report
    except Exception as e:
        return f"Αδυναμία ανάκτησης δεδομένων ελέγχου: {e}"
CPV_MAPPING = {
    "απινιδωτές": "33182100",
    "απινιδωτης": "33182100",
    "φάρμακα": "33600000",
    "φαρμακα": "33600000",
    "αναλώσιμα": "33140000",
    "ιατρικά": "33100000",
    "καθαρισμός": "90910000",
    "λογισμικό": "48000000",
    "υπολογιστές": "30200000",
    "καύσιμα": "09100000",
    "ρεύμα": "09310000",
    "τρόφιμα": "15000000",
    "catering": "55520000",
    "χαρτική": "30192000",
    "κατασκευές": "45000000",
    "δημόσια έργα": "45000000"
}

def _lookup_cpv_by_text(term: str) -> str:
    term_lower = term.lower()
    if term_lower in CPV_MAPPING:
        return CPV_MAPPING[term_lower]

    import json
    import os
    import unicodedata
    
    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cpv_lookup.json')
    if not os.path.exists(json_path):
        return term
        
    term_norm = ''.join(c for c in unicodedata.normalize('NFD', term_lower) if unicodedata.category(c) != 'Mn').strip()
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            records = json.load(f)
            
        for r in records:
            if r['norm'] == term_norm:
                return r['code']
                
        for r in records:
            if term_norm in r['norm']:
                return r['code']
    except Exception:
        pass
    return term

def extract_cpv_from_nl(question: str) -> str:
    """Extracts CPV domain from a natural language question."""
    import re
    # Check for direct numeric CPV mentions
    cpv_match = re.search(r'cpv\s*(\d{4,8})\b', question, re.IGNORECASE)
    if cpv_match:
        return cpv_match.group(1)
        
    standalone_code = re.search(r'\b(\d{8})\b', question)
    if standalone_code:
        return standalone_code.group(1)
        
    # Check for known text descriptions
    q_lower = question.lower()
    for term in CPV_MAPPING.keys():
        if term in q_lower:
            return CPV_MAPPING[term]
            
    return ""

def _parse_year_cpv(params: str):
    """Helper: parse 'year, cpv' from params string. Returns (year, cpv_domain)."""
    params_clean = params.replace('"', '').replace("'", "").strip()
    parts = [p.strip() for p in params_clean.split(",")]
    year = None
    cpv_domain = ""
    for p in parts:
        if len(p) == 4 and p.isdigit():
            year = p
        elif p and p.lower() not in ("all", "ολα", "ολόκληρη", "αγορά", "market", ""):
            # Check if it contains letters (i.e. is a description rather than a CPV code)
            if any(c.isalpha() for c in p):
                cpv_domain = _lookup_cpv_by_text(p)
            else:
                cpv_domain = p
    return year, cpv_domain


def tool_calculate_vcd(params: str) -> str:
    """Υπολογίζει το Value-Count Divergence (VCD) για την αγορά (CPV domain × year)."""
    from data_access.database import execute_cypher

    year, cpv_domain = _parse_year_cpv(params)
    year_filter = f"AND substring(c.submission_date, 0, 4) = '{year}'" if year else ""
    cpv_filter = f'AND c.cpv_code STARTS WITH "{cpv_domain}"' if cpv_domain else ""
    scope = (f"CPV: {cpv_domain}" if cpv_domain else "Συνολική Αγορά") + (f" | Έτος: {year}" if year else " | Όλα τα έτη")

    query = f"""
    MATCH (c:Award)-[:WON_BY]->(w:Winner)
    WHERE c.submission_date IS NOT NULL {cpv_filter} {year_filter}
    RETURN w.name as supplier,
           count(c) as contract_count,
           sum(toFloat(coalesce(c.value, 0.0))) as contract_value
    """
    res = execute_cypher(query, format_output=False)
    if not isinstance(res, list) or len(res) < 2:
        return f"Δεν βρεθηκαν επαρκη δεδομενα VCD (χρειαζονται >=2 προμηθευτες) για {scope}."

    counts = [r.get("contract_count", 0) for r in res]
    values = [r.get("contract_value", 0.0) or 0.0 for r in res]

    def get_rank(vals):
        sorted_idx = sorted(range(len(vals)), key=lambda k: vals[k], reverse=True)
        ranks = [0] * len(vals)
        for rank, idx in enumerate(sorted_idx, 1):
            ranks[idx] = rank
        return ranks

    n = len(res)
    sum_d2 = sum((rc - rv)**2 for rc, rv in zip(get_rank(counts), get_rank(values)))
    spearman = 1 - (6 * sum_d2) / (n * (n**2 - 1)) if n > 1 else 1.0
    vcd = 1 - spearman

    lines = [
        f"📈 Value-Count Divergence (VCD) — {scope}",
        f"  • Πλήθος προμηθευτών: {n}",
        f"  • VCD (Spearman Divergence): {vcd:.4f}  |  Spearman ρ: {spearman:.4f}",
    ]
    if vcd > 0.5:
        lines.append("  ⚠️ Υψηλή ασυμμετρία: λίγοι προμηθευτές συγκεντρώνουν την αξία, πολλοί μόνο αριθμούς συμβάσεων.")
    else:
        lines.append("  ✅ Χαμηλή ασυμμετρία: συμμετρική κατανομή αξίας/πλήθους.")
    return "\n".join(lines)


def tool_calculate_entropy(params: str) -> str:
    """Υπολογίζει H(X), H(Y), H(Y|X), H(X|Y) για μια αγορά (CPV domain × year)."""
    from analytics.diagnostic_engine import calculate_network_entropy, calculate_conditional_entropy

    year, cpv_domain = _parse_year_cpv(params)

    # Use None year to get all-years data when not specified
    entropy = calculate_network_entropy(year or "2024", cpv_domain)
    cond = calculate_conditional_entropy(year or "2024", cpv_domain)

    if entropy.get("status") == "no_data" and cond.get("status") == "no_data":
        scope = f"CPV {cpv_domain}" + (f", έτος {year}" if year else "")
        return f"Δεν βρέθηκαν δεδομένα εντροπίας για {scope}."

    scope = (f"CPV: {cpv_domain}" if cpv_domain else "Συνολική Αγορά") + (f" | Έτος: {year}" if year else " | Όλα τα έτη")
    lines = [f"📊 Εντροπία Δικτύου & Δεσμευμένη Εντροπία ({scope}):"]

    if entropy.get("status") == "ok":
        hx  = entropy.get("H_X_normalized", 0)
        hy  = entropy.get("H_Y_normalized", 0)
        buyers  = entropy.get("num_buyers", 0)
        winners = entropy.get("num_winners", 0)
        lines.append(f"  • Αναθέτουσες: {buyers} | H(X)={entropy['H_X']:.3f} (κανον: {hx:.3f})")
        lines.append(f"    → {'✅ Ανταγωνιστικό (Buyers)' if hx > 0.7 else '⚠️ Ολιγοψώνιο: λίγες αρχές κυριαρχούν.'}")
        lines.append(f"  • Ανάδοχοι: {winners} | H(Y)={entropy['H_Y']:.3f} (κανον: {hy:.3f})")
        lines.append(f"    → {'✅ Ανταγωνιστικό (Suppliers)' if hy > 0.7 else '⚠️ Ολιγοπώλιο: λίγοι ανάδοχοι κυριαρχούν.'}")

    if cond.get("status") == "ok":
        hyx = cond.get("H_Y_given_X", 0)
        hxy = cond.get("H_X_given_Y", 0)
        lines.append(f"  • H(Y|X)={hyx:.3f} → {'✅ Ομοιόμορφη κατανομή (χωρίς Preferential Treatment).' if hyx > 1.0 else '🚩 Preferential Treatment: αρχές αναθέτουν σε λίγους.'}")
        lines.append(f"  • H(X|Y)={hxy:.3f} → {'✅ Ανάδοχοι με πολλούς αγοραστές.' if hxy > 1.0 else '🚩 Vendor Lock-in: ανάδοχοι εξαρτώνται από λίγες αρχές.'}")

    return "\n".join(lines)


def tool_calculate_ici(authority: str) -> str:
    """
    Υπολογίζει τον Institutional Closure Index (ICI) για μια συγκεκριμένη Αναθέτουσα Αρχή.
    Βασίζεται στους δείκτες Fountoukidis et al. (2024):
    ICI = HHI × RelationalScore (Historical Frequency + Adamic-Adar / Preferential Attachment).
    Υψηλό ICI σημαίνει 'Θεσμικό Κλείσιμο' — η αγορά είναι συγκεντρωμένη ΚΑΙ επαναλαμβανόμενη.
    """
    from analytics.diagnostic_engine import calculate_ici
    authority = authority.strip().replace('"', '').replace("'", "")

    result = calculate_ici(authority)

    if result.get("status") == "no_data":
        return f"Δεν βρέθηκαν επαρκή δεδομένα ICI για τον φορέα '{authority}'."

    ici = result.get("ici", 0)
    hhi = result.get("hhi_component", 0)
    rel = result.get("relational_score", 0)
    level = result.get("closure_level", "")
    flag = result.get("closure_flag", "green")
    icon = "🔴" if flag == "red" else ("🟡" if flag == "yellow" else "🟢")

    cpv_info = f" (Υπολογισμός στον κύριο τομέα CPV: {result.get('cpv_domain')})" if result.get('cpv_domain') else " (Υπολογισμός σε όλα τα CPV)"
    lines = [
        f"🏛️ Institutional Closure Index (ICI) — {authority}{cpv_info}",
        f"  • ICI = {ici:.4f}  {icon}  {level}",
        f"  • Συνιστώσα HHI (Συγκέντρωση): {hhi:.4f}",
        f"  • Συνιστώσα Relational Score (Επαναληψιμότητα): {rel:.4f}",
    ]

    if flag == "red":
        lines.append(
            "  ⚠️ Συμπέρασμα: Ο φορέας εμφανίζει Θεσμικό Κλείσιμο — "
            "συνδυασμός υψηλής συγκέντρωσης με επαναλαμβανόμενες σχέσεις. "
            "Συνιστάται ειδικός έλεγχος (Άρθρο 73, Ν.4412/2016)."
        )
    elif flag == "yellow":
        lines.append(
            "  ℹ️ Συμπέρασμα: Μέτριο επίπεδο κλεισίματος. Συνιστάται παρακολούθηση "
            "και σύγκριση με αντίστοιχους φορείς του ίδιου τομέα."
        )
    else:
        lines.append(
            "  ✅ Συμπέρασμα: Ανοιχτή αγορά. Δεν ανιχνεύεται Θεσμικό Κλείσιμο."
        )

    return "\n".join(lines)

def tool_calculate_market_typology(params: str) -> str:
    """Υπολογίζει την Τυπολογία Αγοράς βάσει Recurrence (HF / PA / AA) για ένα CPV domain."""
    from data_access.database import execute_cypher

    year, cpv_domain = _parse_year_cpv(params)
    year_filter   = f"AND substring(c.submission_date, 0, 4) = '{year}'"   if year else ""
    year_filter_u = f"AND substring(c_u.submission_date, 0, 4) = '{year}'" if year else ""
    year_filter_w = f"AND substring(c_w.submission_date, 0, 4) = '{year}'" if year else ""
    cpv_filter = f'AND c.cpv_code STARTS WITH "{cpv_domain}"' if cpv_domain else ""
    cpv_filter_u = f'AND c_u.cpv_code STARTS WITH "{cpv_domain}"' if cpv_domain else ""
    cpv_filter_w = f'AND c_w.cpv_code STARTS WITH "{cpv_domain}"' if cpv_domain else ""
    scope = (f"CPV: {cpv_domain}" if cpv_domain else "Συνολική Αγορά") + (f" | Έτος: {year}" if year else " | Όλα τα έτη")

    import math
    q_buyers = f"""
    MATCH (u:Buyer)-[:AWARDS]->(c:Award)
    WHERE c.submission_date IS NOT NULL {cpv_filter_u} {year_filter_u}
    WITH u.name AS buyer_raw, count(c) as deg_u
    RETURN buyer_raw, deg_u
    """
    res_b = execute_cypher(q_buyers, format_output=False)
    buyer_degs = {}
    if isinstance(res_b, list):
        for r in res_b:
            b_raw = r.get("buyer_raw")
            b_key = b_raw[0] if isinstance(b_raw, list) and b_raw else str(b_raw)
            buyer_degs[b_key] = r.get("deg_u", 0)

    q_winners = f"""
    MATCH (c:Award)-[:WON_BY]->(w:Winner)
    WHERE c.submission_date IS NOT NULL {cpv_filter_w} {year_filter_w}
    RETURN w.name as winner, count(c) as deg_w
    """
    res_w = execute_cypher(q_winners, format_output=False)
    winner_degs = {r["winner"]: r["deg_w"] for r in res_w} if res_w else {}

    q_pairs = f"""
    MATCH (u:Buyer)-[:AWARDS]->(c:Award)-[:WON_BY]->(w:Winner)
    WHERE c.submission_date IS NOT NULL {cpv_filter} {year_filter}
    WITH u.name AS buyer_raw, w.name as winner, count(DISTINCT substring(c.submission_date, 0, 4)) as hf
    RETURN buyer_raw, winner, hf
    """
    res_p = execute_cypher(q_pairs, format_output=False)

    if not isinstance(res_p, list) or not res_p:
        return f"Δεν βρέθηκαν επαρκή δεδομένα για {scope}."

    total_hf, total_pa, total_aa = 0.0, 0.0, 0.0
    valid_pairs = 0
    for p in res_p:
        b_raw = p.get("buyer_raw")
        b = b_raw[0] if isinstance(b_raw, list) and b_raw else str(b_raw)
        w = p.get("winner")
        hf = p.get("hf", 0)
        deg_u = buyer_degs.get(b, 0)
        deg_w = winner_degs.get(w, 0)
        
        if deg_w > 0 and deg_u > 0:
            pa = deg_u * deg_w
            aa = 1.0 / math.log(deg_w + 2)
            total_hf += hf
            total_pa += pa
            total_aa += aa
            valid_pairs += 1

    if valid_pairs == 0:
        return f"Δεν βρέθηκαν επαρκή δεδομένα για {scope}."

    avg_hf = total_hf / valid_pairs
    avg_pa = total_pa / valid_pairs
    avg_aa = total_aa / valid_pairs

    lines = [
        f"🔁 Τυπολογία Αγοράς (Recurrence Analysis) — {scope}",
        f"  • Μέση Ιστορική Συχνότητα (HF): {avg_hf:.2f} → Institutional Memory",
        f"  • Μέση Προτιμησιακή Σύνδεση (PA): {avg_pa:.2f} → Rich-get-Richer / Hubs",
        f"  • Μέση Τοπική Κλειστότητα (AA): {avg_aa:.3f} → Technical Matching / Fragmentation",
    ]

    if avg_pa > 100:
        typology, desc = "PA-driven (Concentrated)", "Λίγοι μεγάλοι παίκτες κυριαρχούν (Scale-free). Ολιγοπώλιο."
    elif avg_hf > 1.5:
        typology, desc = "HF-driven (Institutionalized)", "Σταθερές επαναλαμβανόμενες σχέσεις. Υψηλό lock-in."
    else:
        typology, desc = "AA-driven (Fragmented)", "Κλειστές τοπικές κοινότητες. Χωρίς κυρίαρχο hub."

    lines.append(f"  👉 Τυπολογία: {typology} — {desc}")
    return "\n".join(lines)

# Δημιουργία των standard tools
standard_tools = [
    Tool(
        name="SearchLegalCorpus",
        description="Αναζητά νομικά κείμενα (Ν.4412/16, αποφάσεις ΕΑΔΗΣΥ/Ελεγκτικού). Χρησιμοποίησέ το για να βρεις τι λέει ο νόμος για ένα θέμα.",
        func=tool_search_legal
    ),
    Tool(
        name="GetComplianceData",
        description="Φέρνει τα δεδομένα ελέγχου νομιμότητας (απευθείας αναθέσεις > 30k κλπ) για μια συγκεκριμένη Αναθέτουσα Αρχή (π.χ. 'Δήμος Αθηναίων').",
        func=tool_get_compliance
    ),
    Tool(
        name="CalculateVCD",
        description=(
            "Υπολογίζει το Value-Count Divergence (VCD) για μια συγκεκριμένη αγορά (CPV domain) και έτος. "
            "Είναι ΔΕΙΚΤΗΣ ΑΓΟΡΑΣ (market-level indicator) που μετράει πόσο διαφέρει η κατάταξη των προμηθευτών "
            "με βάση το πλήθος των συμβάσεων σε σχέση με την κατάταξη βάσει αξίας (Spearman divergence). "
            "Input: 'year, cpv' (π.χ. '2024, 33100'). "
            "Χρησιμοποίησέ το για να δεις την ασυμμετρία συγκέντρωσης (market concentration asymmetry) σε έναν τομέα."
        ),
        func=tool_calculate_vcd
    ),
    Tool(
        name="CalculateNetworkEntropy",
        description=(
            "Υπολογίζει την Εντροπία Δικτύου (Network Entropy) για ΜΙΑ ΑΓΟΡΑ (CPV domain). "
            "Επιστρέφει H(X) και H(Y) (εντροπία αγοράς από πλευρά αναθετουσών/αναδόχων: ποιος κυριαρχεί - concentration) "
            "και H(Y|X), H(X|Y) (δεσμευμένη εντροπία: πώς κατανέμονται οι σχέσεις δομικά - relational distribution). "
            "Input: 'year, cpv' (π.χ. '2024, 33100'). "
            "Χρησιμοποίησέ το για να δεις τη συνολική δομή κατανομής μιας αγοράς."
        ),
        func=tool_calculate_entropy
    ),
    Tool(
        name="CalculateMarketTypology",
        description=(
            "Αξιολογεί το Recurrence σε επίπεδο αγοράς (CPV domain) για να δημιουργήσει την Τυπολογία Αγοράς (Market Typology). "
            "Συγκρίνει τις συνιστώσες HF (Historical Frequency), PA (Preferential Attachment) και AA (Adamic-Adar) "
            "για να ταξινομήσει την αγορά σε HF-driven (institutionalized), PA-driven (concentrated) ή AA-driven (fragmented). "
            "Input: κωδικός CPV (π.χ. '33100')."
        ),
        func=tool_calculate_market_typology
    ),
    Tool(
        name="CalculateICI",
        description=(
            "Υπολογίζει τον Institutional Closure Index (ICI) για μια συγκεκριμένη Αναθέτουσα Αρχή. "
            "Ο ICI μετράει αν ο φορέας εμφανίζει 'Θεσμικό Κλείσιμο' — "
            "δηλαδή υψηλή συγκέντρωση ΚΑΙ επαναλαμβανόμενες σχέσεις με τους ίδιους αναδόχους. "
            "Input: όνομα αναθέτουσας αρχής (π.χ. 'Δήμος Θεσσαλονίκης'). "
            "Χρησιμοποίησέ το όταν ρωτάς για εξάρτηση, lock-in, ή θεσμική ακαμψία ενός φορέα."
        ),
        func=tool_calculate_ici
    ),
]

def create_agent() -> ReActAgent:
    return ReActAgent(tools=standard_tools, max_iterations=5)
