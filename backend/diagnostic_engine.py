"""
Simple - Diagnostic Engine (Fountoukidis Methodology)
-------------------------------------------------------
Implements diagnostic metrics for procurement auditing based on:
  - Fountoukidis et al. (2022) "Competitive conditions in the public
    procurement markets: an investigation with network analysis"
  - Fountoukidis et al. (2024) "Measuring Institutional Closure in
    Public Procurement: Evidence from European Buyer–Supplier Networks"

Metrics implemented:
  1. HHI  - Herfindahl-Hirschman Index (Market Concentration)
  2. H(X) - Network Entropy from Buyers' side
  3. H(Y) - Network Entropy from Sellers' (Winners') side
  4. H(Y|X) - Conditional Entropy: avg. seller distribution per buyer
  5. H(X|Y) - Conditional Entropy: avg. buyer distribution per seller
  6. ICI  - Institutional Closure Index (HHI × Relational Score)
"""

import math
from typing import Dict, Any
from database import execute_cypher


# =============================================================================
# HELPER: Shannon Entropy
# =============================================================================

def _shannon(probs: list) -> float:
    """H = -Σ p * log2(p), ignoring zero probabilities."""
    return -sum(p * math.log2(p) for p in probs if p > 0)


# =============================================================================
# 1. AUTHORITY-LEVEL DIAGNOSTICS (HHI + basic metrics)
# =============================================================================

def calculate_authority_diagnostics(authority_name: str, year: str = "2024") -> Dict[str, Any]:
    """
    Calculates HHI, top-share, diversity, and total spend for an authority.
    Falls back to all years if the specific year yields no data.
    """
    year_filter = f"AND substring(c.submission_date, 0, 4) = '{year}'" if year else ""
    cypher = f"""
    MATCH (u:Buyer)-[:AWARDS]->(c:Award)-[:WON_BY]->(w:Winner)
    WHERE ANY(n IN u.name WHERE n = $authority)
      AND c.submission_date IS NOT NULL {year_filter}
    WITH w.name AS company, sum(toFloat(coalesce(c.value, 0.0))) AS total_val
    WITH collect(total_val) AS vals, sum(total_val) AS grand_total, count(DISTINCT company) AS diversity
    WHERE grand_total > 0
    RETURN diversity, grand_total,
           [v IN vals | (v/grand_total)*(v/grand_total)] AS hhi_components,
           reduce(m=0.0, v IN vals | CASE WHEN v > m THEN v ELSE m END) / grand_total AS top_share
    """
    results = execute_cypher(cypher, {"authority": authority_name}, format_output=False)

    if not isinstance(results, list) or not results:
        # Fallback: try without year filter
        cypher_fb = """
    MATCH (u:Buyer)-[:AWARDS]->(c:Award)-[:WON_BY]->(w:Winner)
    WHERE ANY(n IN u.name WHERE n = $authority)
    WITH w.name AS company, sum(toFloat(coalesce(c.value, 0.0))) AS total_val
    WITH collect(total_val) AS vals, sum(total_val) AS grand_total, count(DISTINCT company) AS diversity
    WHERE grand_total > 0
    RETURN diversity, grand_total,
           [v IN vals | (v/grand_total)*(v/grand_total)] AS hhi_components,
           reduce(m=0.0, v IN vals | CASE WHEN v > m THEN v ELSE m END) / grand_total AS top_share
        """
        results = execute_cypher(cypher_fb, {"authority": authority_name}, format_output=False)

    if not isinstance(results, list) or not results:
        return {"status": "no_data"}

    res = results[0]
    if not isinstance(res, dict):
        return {"status": "no_data"}

    hhi = sum(res.get('hhi_components', []) or [])

    risk_score = 0
    diagnosis = "Normal"
    if hhi > 0.25:
        diagnosis = "High Market Concentration (Potential Capture)"
        risk_score += 40
    elif hhi > 0.15:
        diagnosis = "Moderate Concentration"
        risk_score += 20
    if res.get('top_share', 0) > 0.5:
        diagnosis = "Severe Vendor Dependency"
        risk_score += 50

    return {
        "status": "ok",
        "authority": authority_name,
        "year": year,
        "metrics": {
            "hhi": round(hhi, 4),
            "top_supplier_share": round(res.get('top_share', 0), 4),
            "vendor_diversity": res.get('diversity', 0),
            "total_spend": round(res.get('grand_total', 0), 2),
        },
        "diagnosis": diagnosis,
        "risk_score": min(risk_score, 100),
    }


# =============================================================================
# 2. NETWORK ENTROPY  H(X) and H(Y)
#    Based on Fountoukidis et al. (2022), Equations (5) and (6)
# =============================================================================

def calculate_network_entropy(year: str = "2024", cpv_domain: str = None) -> Dict[str, Any]:
    """
    H(X): Shannon entropy of contract distribution across Buyers.
    H(Y): Shannon entropy of contract distribution across Winners.
    Both based on contract COUNT share in the given year.
    Low value → few agents dominate (oligopsony / oligopoly).
    High value → competitive, no dominant agent.
    """
    cpv_filter = "AND c.cpv_code STARTS WITH $cpv_domain" if cpv_domain else ""
    year_filter = f"AND substring(c.submission_date, 0, 4) = '{year}'" if year else ""
    cypher = f"""
    MATCH (u:Buyer)-[:AWARDS]->(c:Award)-[:WON_BY]->(w:Winner)
    WHERE c.submission_date IS NOT NULL {cpv_filter} {year_filter}
    WITH
      u.name AS buyer_raw,
      w.name AS winner,
      count(c) AS contracts
    RETURN buyer_raw, winner, contracts
    """
    params = {}
    if cpv_domain:
        params["cpv_domain"] = cpv_domain
        
    results = execute_cypher(cypher, params, format_output=False)
    if not isinstance(results, list) or not results:
        return {"status": "no_data"}

    # Aggregate per buyer and per winner, and calculate total
    buyer_counts: Dict[str, float] = {}
    winner_counts: Dict[str, float] = {}
    total = 0.0
    for row in results:
        b_raw = row.get("buyer_raw")
        b = b_raw[0] if isinstance(b_raw, list) and b_raw else str(b_raw)
        w = row.get("winner") or ""
        cnt = float(row.get("contracts", 0) or 0)
        buyer_counts[b] = buyer_counts.get(b, 0) + cnt
        winner_counts[w] = winner_counts.get(w, 0) + cnt
        total += cnt

    if not total:
        return {"status": "no_data"}


    px = [v / total for v in buyer_counts.values()]
    py = [v / total for v in winner_counts.values()]

    hx = _shannon(px)
    hy = _shannon(py)
    hx_max = math.log2(len(px)) if len(px) > 1 else 1
    hy_max = math.log2(len(py)) if len(py) > 1 else 1

    return {
        "status": "ok",
        "year": year,
        "cpv_domain": cpv_domain,
        "H_X": round(hx, 4),
        "H_Y": round(hy, 4),
        "H_X_normalized": round(hx / hx_max, 4) if hx_max else 0,
        "H_Y_normalized": round(hy / hy_max, 4) if hy_max else 0,
        "num_buyers": len(buyer_counts),
        "num_winners": len(winner_counts),
    }


# =============================================================================
# 3. CONDITIONAL NETWORK ENTROPY  H(Y|X) and H(X|Y)
#    Based on Fountoukidis et al. (2022), Equations (7) and (8)
# =============================================================================

def calculate_conditional_entropy(year: str = "2024", cpv_domain: str = None) -> Dict[str, Any]:
    """
    H(Y|X): weighted avg. of each buyer's entropy over its sellers.
    H(X|Y): weighted avg. of each seller's entropy over its buyers.
    """
    cpv_filter = "AND c.cpv_code STARTS WITH $cpv_domain" if cpv_domain else ""
    year_filter = f"AND substring(c.submission_date, 0, 4) = '{year}'" if year else ""
    cypher = f"""
    MATCH (u:Buyer)-[:AWARDS]->(c:Award)-[:WON_BY]->(w:Winner)
    WHERE c.submission_date IS NOT NULL {cpv_filter} {year_filter}
    WITH
      u.name AS buyer_raw,
      w.name AS winner,
      count(c) AS contracts
    RETURN buyer_raw, winner, contracts
    """
    params = {}
    if cpv_domain:
        params["cpv_domain"] = cpv_domain
        
    results = execute_cypher(cypher, params, format_output=False)
    if not isinstance(results, list) or not results:
        return {"status": "no_data"}

    # Build adjacency: buyer → {winner: count}
    buyer_map: Dict[str, Dict[str, float]] = {}
    winner_map: Dict[str, Dict[str, float]] = {}
    grand_total = 0.0

    for row in results:
        b_raw = row.get("buyer_raw")
        b = b_raw[0] if isinstance(b_raw, list) and b_raw else str(b_raw)
        w = row.get("winner") or ""
        cnt = float(row.get("contracts", 0) or 0)
        buyer_map.setdefault(b, {})[w] = buyer_map.get(b, {}).get(w, 0) + cnt
        winner_map.setdefault(w, {})[b] = winner_map.get(w, {}).get(b, 0) + cnt
        grand_total += cnt

    if grand_total == 0:
        return {"status": "no_data"}

    # H(Y|X) = -Σ_j P(xj) * Σ_i P(xj→yi)*log2(P(xj→yi))
    h_y_given_x = 0.0
    for b, sellers in buyer_map.items():
        pxj = sum(sellers.values()) / grand_total
        local_total = sum(sellers.values())
        local_probs = [v / local_total for v in sellers.values()]
        h_y_given_x += pxj * _shannon(local_probs)

    # H(X|Y) = -Σ_i P(yi) * Σ_j P(yi→xj)*log2(P(yi→xj))
    h_x_given_y = 0.0
    for w, buyers in winner_map.items():
        pyi = sum(buyers.values()) / grand_total
        local_total = sum(buyers.values())
        local_probs = [v / local_total for v in buyers.values()]
        h_x_given_y += pyi * _shannon(local_probs)

    return {
        "status": "ok",
        "year": year,
        "H_Y_given_X": round(h_y_given_x, 4),
        "H_X_given_Y": round(h_x_given_y, 4),
    }


# =============================================================================
# 4. INSTITUTIONAL CLOSURE INDEX (ICI)
#    Based on Fountoukidis et al. (2024)
#    ICI_authority = HHI_authority × RelationalScore_authority
#    RelationalScore = weighted avg over suppliers of:
#       score(a,s) = (HF + AA) / (PA + epsilon)   normalized to [0,1]
# =============================================================================

def calculate_ici(authority_name: str) -> Dict[str, Any]:
    """
    Institutional Closure Index for a specific contracting authority.
    Uses multi-year data for Historical Frequency and Adamic-Adar.

    Returns ICI in [0, 1]:
      - High  → concentrated + persistent relationships → "Institutional Closure"
      - Low   → dispersed or non-persistent → open, competitive procurement
    """
    # Step 0: Find dominant CPV domain (5-digit)
    # Note: Buyer.name may be an array — use ANY() for matching
    cypher_domain = """
    MATCH (u:Buyer)-[:AWARDS]->(c:Award)
    WHERE ANY(n IN u.name WHERE n = $authority)
      AND c.cpv_code IS NOT NULL
    WITH substring(c.cpv_code, 0, 5) AS cpv_domain, count(c) AS cnt
    ORDER BY cnt DESC
    RETURN cpv_domain LIMIT 1
    """
    domain_res = execute_cypher(cypher_domain, {"authority": authority_name}, format_output=False)
    cpv_domain = None
    if isinstance(domain_res, list) and domain_res and isinstance(domain_res[0], dict):
        cpv_domain = domain_res[0].get("cpv_domain")

    # If we found a dominant CPV domain, we filter by it. Otherwise, we calculate globally.
    cpv_filter_c  = "AND c.cpv_code STARTS WITH $cpv_domain"  if cpv_domain else ""
    cpv_filter_c2 = "AND c2.cpv_code STARTS WITH $cpv_domain" if cpv_domain else ""
    # HF uses submission_date substring for year counting
    hf_date_filter = "AND c.submission_date IS NOT NULL" + (" AND c.cpv_code STARTS WITH $cpv_domain" if cpv_domain else "")

    params = {"authority": authority_name}
    if cpv_domain:
        params["cpv_domain"] = cpv_domain

    # Step 1: HHI (count-based) for this authority across all years (within domain)
    cypher_hhi = f"""
    MATCH (u:Buyer)-[:AWARDS]->(c:Award)-[:WON_BY]->(w:Winner)
    WHERE ANY(n IN u.name WHERE n = $authority) {cpv_filter_c}
    WITH w.name AS winner, count(c) AS cnt
    WITH collect(cnt) AS counts, sum(cnt) AS total
    WHERE total > 0
    RETURN total, [v IN counts | toFloat(v)/total * toFloat(v)/total] AS hhi_components
    """
    hhi_res = execute_cypher(cypher_hhi, params, format_output=False)
    if not isinstance(hhi_res, list) or not hhi_res or not isinstance(hhi_res[0], dict):
        return {"status": "no_data"}

    hhi = sum(hhi_res[0].get("hhi_components", []) or [])
    total_contracts = hhi_res[0].get("total", 0)

    # Step 2: Historical Frequency per (authority, winner) pair
    # HF = number of distinct years with at least one contract
    cypher_hf = f"""
    MATCH (u:Buyer)-[:AWARDS]->(c:Award)-[:WON_BY]->(w:Winner)
    WHERE ANY(n IN u.name WHERE n = $authority) {hf_date_filter}
    WITH w.name AS winner,
         count(DISTINCT substring(c.submission_date, 0, 4)) AS hf,
         count(c) AS pair_cnt
    RETURN winner, hf, pair_cnt
    """
    hf_res = execute_cypher(cypher_hf, params, format_output=False)
    if not isinstance(hf_res, list) or not hf_res:
        return {"status": "no_data"}

    hf_map = {r["winner"]: (r.get("hf", 1), r.get("pair_cnt", 1))
              for r in hf_res if isinstance(r, dict) and r.get("winner")}

    # Step 3: Adamic-Adar adapted for bipartite networks
    cypher_aa = f"""
    MATCH (u:Buyer)-[:AWARDS]->(c:Award)-[:WON_BY]->(w:Winner)
    WHERE ANY(n IN u.name WHERE n = $authority) {cpv_filter_c}
    WITH w.name AS winner, count(c) AS shared_awards
    MATCH (other:Buyer)-[:AWARDS]->(c2:Award)-[:WON_BY]->(w2:Winner {cpv_filter_c2})
    WHERE w2.name = winner
    WITH winner, shared_awards, count(DISTINCT other) AS other_buyers
    WHERE other_buyers > 0
    RETURN winner, shared_awards,
           shared_awards * 1.0 / log(other_buyers + 2) AS aa_score
    """
    aa_res = execute_cypher(cypher_aa, params, format_output=False)
    aa_map = {}
    if isinstance(aa_res, list):
        for r in aa_res:
            if isinstance(r, dict) and r.get("winner"):
                aa_map[r["winner"]] = r.get("aa_score", 0) or 0

    # Step 4: Preferential Attachment
    cypher_pa = f"""
    MATCH (u:Buyer)-[:AWARDS]->(c:Award)
    WHERE ANY(n IN u.name WHERE n = $authority) {cpv_filter_c}
    WITH count(c) AS deg_u
    MATCH (c2:Award)-[:WON_BY]->(w:Winner)
    WHERE c2 IS NOT NULL {cpv_filter_c2}
    WITH deg_u, w.name AS winner, count(c2) AS deg_w
    RETURN winner, deg_u * deg_w AS pa
    """
    pa_res = execute_cypher(cypher_pa, params, format_output=False)
    pa_map = {}
    if isinstance(pa_res, list):
        for r in pa_res:
            if isinstance(r, dict) and r.get("winner"):
                pa_map[r["winner"]] = r.get("pa", 1) or 1

    # Step 5: Compute normalized dyadic score per winner
    # score(a,s) = (HF + AA) / (PA + ε), then normalize to [0,1]
    epsilon = 1e-6
    raw_scores = {}
    for w, (hf, pair_cnt) in hf_map.items():
        aa = aa_map.get(w, 0)
        pa = pa_map.get(w, 1)
        raw_scores[w] = (hf + aa) / (pa + epsilon)

    if not raw_scores:
        return {"status": "no_data"}

    max_score = max(raw_scores.values()) or 1
    norm_scores = {w: v / max_score for w, v in raw_scores.items()}

    # Step 6: Authority-level relational component
    # R(authority) = Σ_w weight(w) * norm_score(w)
    # weight(w) = pair_cnt(w) / total_contracts
    relational_score = 0.0
    for w, norm_s in norm_scores.items():
        pair_cnt = hf_map[w][1]
        weight = pair_cnt / total_contracts if total_contracts else 0
        relational_score += weight * norm_s

    # Step 7: ICI = HHI × RelationalScore
    ici = hhi * relational_score

    # Interpretation thresholds
    if ici > 0.3:
        closure_level = "ΥΨΗΛΟ (Θεσμικό Κλείσιμο)"
        closure_flag = "red"
    elif ici > 0.1:
        closure_level = "ΜΕΤΡΙΟ (Παρακολούθηση)"
        closure_flag = "yellow"
    else:
        closure_level = "ΧΑΜΗΛΟ (Ανοιχτή Αγορά)"
        closure_flag = "green"

    return {
        "status": "ok",
        "authority": authority_name,
        "cpv_domain": cpv_domain,
        "ici": round(ici, 4),
        "hhi_component": round(hhi, 4),
        "relational_score": round(relational_score, 4),
        "closure_level": closure_level,
        "closure_flag": closure_flag,
    }


# =============================================================================
# 5. FULL DIAGNOSTICS (combines all metrics)
# =============================================================================

def calculate_full_diagnostics(authority_name: str, year: str = "2024") -> Dict[str, Any]:
    """Runs all diagnostic metrics and returns a combined result dict."""
    base = calculate_authority_diagnostics(authority_name, year)
    entropy = calculate_network_entropy(year)
    conditional = calculate_conditional_entropy(year)
    ici = calculate_ici(authority_name)

    return {
        "base": base,
        "network_entropy": entropy,
        "conditional_entropy": conditional,
        "ici": ici,
    }


# =============================================================================
# 6. DIAGNOSTIC REASONING (Report Generator)
# =============================================================================

def get_diagnostic_reasoning(diag_data: Dict[str, Any]) -> str:
    """
    Generates a structured diagnostic report (Therapy) from the metrics.
    Supports both simple dict (from calculate_authority_diagnostics)
    and full dict (from calculate_full_diagnostics).
    """
    # Detect input format
    if "base" in diag_data:
        base = diag_data["base"]
        entropy = diag_data.get("network_entropy", {})
        cond = diag_data.get("conditional_entropy", {})
        ici_data = diag_data.get("ici", {})
    else:
        base = diag_data
        entropy = {}
        cond = {}
        ici_data = {}

    if base.get("status") == "no_data":
        return "Δεν υπάρχουν επαρκή δεδομένα για διάγνωση."

    metrics = base["metrics"]
    authority = base.get("authority", "Φορέας")
    year = base.get("year", "")
    year_str = f" (Έτος {year})" if year and str(year).isdigit() else ""

    is_concentrated = metrics["hhi"] > 0.15
    is_dependent = metrics["top_supplier_share"] > 0.4
    hhi_str = f"{metrics['hhi']:.4f}".replace(".", ",")
    share_str = f"{metrics['top_supplier_share']*100:.1f}".replace(".", ",")

    is_medical = any(k in authority.upper() for k in ["ΝΟΣΟΚΟΜΕΙΟ", "ΥΓΕΙΑΣ", "ΝΟΣΗΛΕΥΤΙΚΟ", "ΑΧΕΠΑ"])
    market_context = "Στην αγορά στο χώρο της υγείας" if is_medical else "Στην αγορά για τον συγκεκριμένο τομέα δραστηριότητας"

    report = f"### 🩺 1. ΔΙΑΓΝΩΣΗ\n"
    report += f"Φορέας: **{authority}**{year_str}\n"
    report += f"{market_context}, η πολυφωνία είναι κρίσιμη για την αποφυγή μονοπωλιακών καταστάσεων.\n\n"

    report += "### 📊 2. ΑΝΑΛΥΣΗ ΔΕΙΚΤΩΝ\n"
    report += f"- **HHI (Συγκέντρωση Αγοράς)**: `{hhi_str}`. "
    report += "Υγιής ανταγωνισμός.\n" if not is_concentrated else "⚠️ Υψηλή συγκέντρωση — κίνδυνος 'Market Capture'.\n"

    report += f"- **Εξάρτηση από κορυφαίο ανάδοχο**: `{share_str}%`. "
    report += "Φυσιολογική.\n" if not is_dependent else "⚠️ Κίνδυνος Vendor Lock-in.\n"

    report += f"- **Μοναδικοί ανάδοχοι**: {metrics['vendor_diversity']}\n"

    # Network Entropy
    if entropy.get("status") == "ok":
        hx = entropy.get("H_X_normalized", None)
        hy = entropy.get("H_Y_normalized", None)
        hx_raw = entropy.get("H_X", "N/A")
        hy_raw = entropy.get("H_Y", "N/A")
        report += f"\n**Εντροπία Δικτύου (Έτος {entropy.get('year','')}):**\n"
        report += f"- H(X) — Εντροπία Αναθετουσών: `{hx_raw}` (κανονικοποιημένη: `{hx:.3f}`). "
        if hx is not None:
            report += "✅ Ανταγωνιστικό περιβάλλον από πλευράς αγοραστών.\n" if hx > 0.7 else "⚠️ Λίγες αναθέτουσες αρχές κυριαρχούν στην αγορά (Ολιγοψώνιο).\n"
        report += f"- H(Y) — Εντροπία Αναδόχων: `{hy_raw}` (κανονικοποιημένη: `{hy:.3f}`). "
        if hy is not None:
            report += "✅ Ανταγωνιστικό περιβάλλον από πλευράς πωλητών.\n" if hy > 0.7 else "⚠️ Λίγοι ανάδοχοι κυριαρχούν στην αγορά (Ολιγοπώλιο).\n"

    # Conditional Entropy
    if cond.get("status") == "ok":
        hyx = cond.get("H_Y_given_X", None)
        hxy = cond.get("H_X_given_Y", None)
        report += f"\n**Δεσμευμένη Εντροπία (Conditional Entropy):**\n"
        if hyx is not None:
            report += f"- H(Y|X) = `{hyx}` — "
            report += "Οι αναθέτουσες αρχές κατανέμουν ομοιόμορφα τις συμβάσεις τους.\n" if hyx > 1.0 else "🚩 **Red Flag**: Οι αναθέτουσες αρχές κατευθύνουν συστηματικά τις συμβάσεις σε λίγους αναδόχους. Ένδειξη **προτιμησιακής μεταχείρισης**.\n"
        if hxy is not None:
            report += f"- H(X|Y) = `{hxy}` — "
            report += "Οι ανάδοχοι συνεργάζονται με ποικιλία φορέων.\n" if hxy > 1.0 else "🚩 **Red Flag**: Οι ανάδοχοι εξαρτώνται από λίγες αναθέτουσες αρχές. Ένδειξη **θεσμικής εξάρτησης**.\n"

    # ICI
    if ici_data.get("status") == "ok":
        ici_val = ici_data.get("ici", 0)
        closure_level = ici_data.get("closure_level", "")
        flag = ici_data.get("closure_flag", "green")
        cpv_dom = ici_data.get("cpv_domain")
        cpv_str = f" (Υπολογισμός στον κύριο τομέα CPV: {cpv_dom})" if cpv_dom else " (Υπολογισμός σε όλα τα CPV)"
        flag_icon = "🔴" if flag == "red" else ("🟡" if flag == "yellow" else "🟢")
        report += f"\n**Institutional Closure Index (ICI):** `{ici_val:.4f}` {flag_icon} — {closure_level}{cpv_str}\n"
        if flag == "red":
            report += "> ⚠️ Υψηλό ICI: Η αγορά εμφανίζει χαρακτηριστικά **Θεσμικού Κλεισίματος** — συγκεντρωμένη κατανομή + επαναλαμβανόμενες σχέσεις. Συνιστάται εκτεταμένος ποιοτικός έλεγχος.\n"

    report += "\n### 💊 3. ΠΡΟΤΕΙΝΟΜΕΝΗ ΘΕΡΑΠΕΙΑ (Ν.4412/2016)\n"
    needs_action = is_concentrated or is_dependent or ici_data.get("closure_flag") == "red"
    if needs_action:
        report += "- **Κατάτμηση σε Τμήματα** (Άρθρο 59): Ενθάρρυνση συμμετοχής ΜμΕ.\n"
        report += "- **Market Sounding**: Διαβούλευση για εναλλακτικές πηγές προμήθειας.\n"
        if ici_data.get("closure_flag") == "red":
            report += "- **Ειδικός Έλεγχος (Audit)**: Το υψηλό ICI δικαιολογεί εφαρμογή Άρθρου 73 (Πολιτική Εξαιρέσεων).\n"
    else:
        report += "Συνιστάται η διατήρηση της υφιστάμενης στρατηγικής και η συνεχής παρακολούθηση των δεικτών.\n"

    report += "\n---\n💡 **ΝΟΜΙΚΗ ΠΑΡΑΤΗΡΗΣΗ**\n"
    if not is_concentrated and not needs_action:
        report += f"Η υγιής πολυφωνία (HHI: {hhi_str}) διασφαλίζει τήρηση της αρχής ελεύθερου ανταγωνισμού (Άρθρο 18, Ν.4412/2016)."
    else:
        report += "Η αυξημένη συγκέντρωση ή/και το θεσμικό κλείσιμο ενδέχεται να περιορίζουν την πρόσβαση ΜμΕ στις διαδικασίες ανάθεσης."

    return report
