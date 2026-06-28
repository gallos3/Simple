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
from data_access.database import execute_cypher


# =============================================================================
# HELPER: Shannon Entropy
# =============================================================================

def _shannon(probs: list) -> float:
    """H = -Σ p * log2(p), ignoring zero probabilities."""
    return -sum(p * math.log2(p) for p in probs if p > 0)


# =============================================================================
# 1. AUTHORITY-LEVEL DIAGNOSTICS (HHI + basic metrics)
# =============================================================================

def calculate_authority_diagnostics(authority_name: str, year: str = "2024", cpv_domain: str = None) -> Dict[str, Any]:
    """
    Calculates HHI, top-share, diversity, and total spend for an authority.
    Falls back to CPV-level supplier HHI when authority_name is None.
    """
    # --- CPV-only mode: supplier-level HHI across the CPV domain ---
    if not authority_name and cpv_domain:
        year_filter = f"AND substring(c.submission_date, 0, 4) = '{year}'" if year else ""
        cypher_cpv = f"""
        MATCH (u:Buyer)-[:AWARDS]-(c:Award)-[:WON_BY]-(w:Winner)
        WHERE c.cpv_code STARTS WITH $cpv_domain {year_filter}
        WITH w.name AS company, sum(toFloat(coalesce(c.value, 0.0))) AS total_val
        WITH collect(total_val) AS vals, sum(total_val) AS grand_total, count(DISTINCT company) AS diversity
        WHERE grand_total > 0
        RETURN diversity, grand_total,
               [v IN vals | (v/grand_total)*(v/grand_total)] AS hhi_components,
               reduce(m=0.0, v IN vals | CASE WHEN v > m THEN v ELSE m END) / grand_total AS top_share
        """
        res_cpv = execute_cypher(cypher_cpv, {"cpv_domain": cpv_domain}, format_output=False)
        if isinstance(res_cpv, list) and res_cpv and isinstance(res_cpv[0], dict):
            res = res_cpv[0]
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
                "authority": f"CPV {cpv_domain}",
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
        return {"status": "no_data"}

    year_filter = f"AND substring(c.submission_date, 0, 4) = '{year}'" if year else ""
    cpv_filter = "AND c.cpv_code STARTS WITH $cpv_domain" if cpv_domain else ""
    params = {"authority": authority_name}
    if cpv_domain:
        params["cpv_domain"] = cpv_domain

    cypher = f"""
    MATCH (u:Buyer)-[:AWARDS]-(c:Award)-[:WON_BY]-(w:Winner)
    WHERE toUpper(u.name) CONTAINS toUpper($authority)
      AND c.submission_date IS NOT NULL {year_filter} {cpv_filter}
    WITH w.name AS company, sum(toFloat(coalesce(c.value, 0.0))) AS total_val
    WITH collect(total_val) AS vals, sum(total_val) AS grand_total, count(DISTINCT company) AS diversity
    WHERE grand_total > 0
    RETURN diversity, grand_total,
           [v IN vals | (v/grand_total)*(v/grand_total)] AS hhi_components,
           reduce(m=0.0, v IN vals | CASE WHEN v > m THEN v ELSE m END) / grand_total AS top_share
    """
    results = execute_cypher(cypher, params, format_output=False)

    if not isinstance(results, list) or not results:
        # Fallback: try without year filter
        cypher_fb = f"""
    MATCH (u:Buyer)-[:AWARDS]-(c:Award)-[:WON_BY]-(w:Winner)
    WHERE toUpper(u.name) CONTAINS toUpper($authority) {cpv_filter}
    WITH w.name AS company, sum(toFloat(coalesce(c.value, 0.0))) AS total_val
    WITH collect(total_val) AS vals, sum(total_val) AS grand_total, count(DISTINCT company) AS diversity
    WHERE grand_total > 0
    RETURN diversity, grand_total,
           [v IN vals | (v/grand_total)*(v/grand_total)] AS hhi_components,
           reduce(m=0.0, v IN vals | CASE WHEN v > m THEN v ELSE m END) / grand_total AS top_share
        """
        results = execute_cypher(cypher_fb, params, format_output=False)

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
    MATCH (u:Buyer)-[:AWARDS]-(c:Award)-[:WON_BY]-(w:Winner)
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
    MATCH (u:Buyer)-[:AWARDS]-(c:Award)-[:WON_BY]-(w:Winner)
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

def calculate_ici(authority_name: str, cpv_domain: str = None) -> Dict[str, Any]:
    """
    Institutional Closure Index for a specific contracting authority.
    Uses multi-year data for Historical Frequency and Adamic-Adar.

    Returns ICI in [0, 1]:
      - High  → concentrated + persistent relationships → "Institutional Closure"
      - Low   → dispersed or non-persistent → open, competitive procurement
    """
    # Step 0: Find dominant CPV domain (5-digit) if not provided
    if not cpv_domain:
        # Note: Buyer.name may be an array — use ANY() for matching
        cypher_domain = """
        MATCH (u:Buyer)-[:AWARDS]-(c:Award)
        WHERE ANY(n IN u.name WHERE n = $authority)
          AND c.cpv_code IS NOT NULL
        WITH substring(c.cpv_code, 0, 5) AS cpv_domain, count(c) AS cnt
        ORDER BY cnt DESC
        RETURN cpv_domain LIMIT 1
        """
        domain_res = execute_cypher(cypher_domain, {"authority": authority_name}, format_output=False)
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
    MATCH (u:Buyer)-[:AWARDS]-(c:Award)-[:WON_BY]-(w:Winner)
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
    MATCH (u:Buyer)-[:AWARDS]-(c:Award)-[:WON_BY]-(w:Winner)
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
    MATCH (u:Buyer)-[:AWARDS]-(c:Award)-[:WON_BY]-(w:Winner)
    WHERE ANY(n IN u.name WHERE n = $authority) {cpv_filter_c}
    WITH w.name AS winner, count(c) AS shared_awards
    MATCH (other:Buyer)-[:AWARDS]-(c2:Award)-[:WON_BY]-(w2:Winner {cpv_filter_c2})
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
    MATCH (u:Buyer)-[:AWARDS]-(c:Award)
    WHERE ANY(n IN u.name WHERE n = $authority) {cpv_filter_c}
    WITH count(c) AS deg_u
    MATCH (c2:Award)-[:WON_BY]-(w:Winner)
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
        raw_scores[w] = (hf + aa) / (hf + aa + pa + epsilon)

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
# 5. VALUE CAPTURE DIVERGENCE (VCD)
#    Based on Fountoukidis et al. — value_captor_predictor_v3.py
#    EXACT same logic as compute_vcd() / gini() from source.
#    Measures divergence between contract COUNT ranking and VALUE ranking.
# =============================================================================

def _gini(arr) -> float:
    """
    Gini coefficient — EXACT replica from value_captor_predictor_v3.py line 90-96.
    gini([]) = 0.0
    gini([equal...]) ≈ 0.0
    gini([0,0,...,big]) → 1.0
    """
    import numpy as np
    arr = np.array(arr, dtype=float)
    arr = arr[arr > 0]
    if len(arr) == 0:
        return 0.0
    arr = np.sort(arr)
    n = len(arr)
    return (2 * np.sum(np.arange(1, n + 1) * arr) / (n * np.sum(arr))) - (n + 1) / n


def _vcd_supplier_stats(year: str = None, cpv_domain: str = None) -> list:
    """
    Queries Neo4j for per-supplier contract count and total value.
    Returns list of dicts: [{"supplier": str, "cnt": int, "total_val": float}, ...]
    Adapted from _FEATURE_STATS_QUERY in source, using Simple_Federated schema:
      (Buyer)-[:AWARDS]-(Award)-[:WON_BY]-(Winner)
    """
    year_filter = f"AND substring(c.submission_date, 0, 4) = '{year}'" if year else ""
    cpv_filter = "AND c.cpv_code STARTS WITH $cpv_domain" if cpv_domain else ""

    cypher = f"""
    MATCH (u:Buyer)-[:AWARDS]-(c:Award)-[:WON_BY]-(w:Winner)
    WHERE c.submission_date IS NOT NULL
      AND toFloat(coalesce(c.value, 0)) > 0
      {year_filter} {cpv_filter}
    WITH w.name AS supplier,
         count(c) AS cnt,
         sum(toFloat(coalesce(c.value, 0))) AS total_val
    RETURN supplier, cnt, total_val
    """
    params = {}
    if cpv_domain:
        params["cpv_domain"] = cpv_domain

    results = execute_cypher(cypher, params, format_output=False)
    if not isinstance(results, list):
        return []
    return [r for r in results if isinstance(r, dict)]


def calculate_vcd(year: str = None, cpv_domain: str = None) -> Dict[str, Any]:
    """
    Value Capture Divergence — EXACT logic from compute_vcd() in
    value_captor_predictor_v3.py (lines 295-310).

    Steps:
      1. Query per-supplier: cnt (contract count), total_val (sum of values)
      2. Filter to suppliers with total_val > 0
      3. If < 10 suppliers → return nan (same threshold as source)
      4. Spearman rank correlation between cnt rank and total_val rank
      5. rho_vcd = 1 - rho  (divergence measure)
      6. delta_gini = gini(total_val) - gini(cnt)
      7. Return all components

    Args:
        year: optional, e.g. "2024"
        cpv_domain: optional CPV prefix, e.g. "45233"

    Returns:
        dict with spearman_rho, rho_vcd, delta_gini, gini_value, gini_count,
        vcd_pval, n_suppliers, status
    """
    import numpy as np
    from scipy.stats import spearmanr

    rows = _vcd_supplier_stats(year=year, cpv_domain=cpv_domain)
    if not rows:
        return {"status": "no_data"}

    # Build arrays — same filtering as source line 296: total_val > 0
    cnt_arr = []
    val_arr = []
    for r in rows:
        tv = float(r.get("total_val", 0) or 0)
        if tv > 0:
            cnt_arr.append(float(r.get("cnt", 0) or 0))
            val_arr.append(tv)

    n = len(cnt_arr)
    # Same threshold as source line 297-299: < 10 → nan
    if n < 10:
        return {
            "status": "insufficient_data",
            "spearman_rho": None,
            "rho_vcd": None,
            "delta_gini": None,
            "gini_value": None,
            "gini_count": None,
            "vcd_total": None,
            "vcd_normalized": None,
            "vcd_pval": None,
            "n_suppliers": n,
        }

    cnt_np = np.array(cnt_arr)
    val_np = np.array(val_arr)

    # Exact same call as source line 300-301:
    # spearmanr(df["cnt"].rank(ascending=False), df["total_val"].rank(ascending=False))
    # scipy.stats.spearmanr internally handles ranking, equivalent to rank correlation
    from scipy.stats import rankdata
    rank_cnt = rankdata(-cnt_np)  # ascending=False → negate for descending
    rank_val = rankdata(-val_np)
    rho, pval = spearmanr(rank_cnt, rank_val)

    # Exact same computation as source lines 302-310
    gini_value = _gini(val_np)
    gini_count = _gini(cnt_np)
    delta_gini = gini_value - gini_count

    rho_vcd = 1 - rho
    vcd_total = rho_vcd + delta_gini
    vcd_normalized = vcd_total / 2

    return {
        "status": "ok",
        "spearman_rho": round(rho, 4),
        "rho_vcd": round(rho_vcd, 4),
        "delta_gini": round(delta_gini, 4),
        "gini_value": round(gini_value, 4),
        "gini_count": round(gini_count, 4),
        "vcd_total": round(vcd_total, 4),
        "vcd_normalized": round(vcd_normalized, 4),
        "vcd_pval": round(pval, 6),
        "n_suppliers": n,
        "year": year,
        "cpv_domain": cpv_domain,
    }


# =============================================================================
# 5b. RECURRENCE SIGNALS (Historical Frequency, Preferential Attachment, Adamic-Adar)
#     Adapted from Fountoukidis et al. — predictor_khmdhs_hhi_fixed.py
#     Aggregates pair-level structural features to market-level signals.
# =============================================================================

def calculate_recurrence_signals(year: str = None, cpv_domain: str = None) -> Dict[str, Any]:
    """
    Market-level aggregation of recurrence features: HF, PA.
    Uses simple flat Cypher — no CALL subqueries.
    Schema: (u:Buyer)-[:AWARDS]-(a:Award)-[:WON_BY]-(w:Winner)
    """
    year_filter = f"AND substring(a.submission_date, 0, 4) = '{year}'" if year else ""
    cpv_filter  = "AND a.cpv_code STARTS WITH $cpv_domain" if cpv_domain else ""

    params = {}
    if cpv_domain:
        params["cpv_domain"] = cpv_domain

    # Debug probe: verify CPV filter hits the DB
    debug_cypher = f"""
    MATCH (u:Buyer)-[:AWARDS]-(a:Award)-[:WON_BY]-(w:Winner)
    WHERE a.submission_date IS NOT NULL
      {year_filter} {cpv_filter}
    RETURN count(*) AS total_pairs
    """
    debug_res = execute_cypher(debug_cypher, params, format_output=False)
    total_pairs = debug_res[0].get("total_pairs", 0) if debug_res and isinstance(debug_res, list) else 0
    print(f"[DEBUG] Recurrence probe — cpv_domain={cpv_domain}, year={year}, total_pairs={total_pairs}", flush=True)

    cypher = f"""
    MATCH (u:Buyer)-[:AWARDS]-(a:Award)-[:WON_BY]-(w:Winner)
    WHERE a.submission_date IS NOT NULL
      {cpv_filter}

    WITH u, w,
         count(DISTINCT substring(a.submission_date, 0, 4)) AS hf,
         count(a) AS interactions

    WITH u, w, hf,
         COUNT {{ (u)--() }} AS deg_u,
         COUNT {{ (w)--() }} AS deg_w

    WITH hf, (deg_u * deg_w) AS pa

    RETURN
        avg(hf) AS hf_mean,
        max(hf) AS hf_max,
        avg(pa) AS pa_mean
    """

    results = execute_cypher(cypher, params, format_output=False)
    if not results or not isinstance(results, list) or not results[0] or results[0].get("hf_mean") is None:
        return {
            "status": "no_data",
            "hf_mean": None,
            "hf_max": None,
            "pa_mean": None,
            "aa_mean": None
        }

    res = results[0]
    return {
        "status": "ok",
        "hf_mean": round(float(res.get("hf_mean") or 0.0), 4),
        "hf_max":  round(float(res.get("hf_max")  or 0.0), 4),
        "pa_mean": round(float(res.get("pa_mean")  or 0.0), 4),
        "aa_mean": None   # AA omitted (required CALL subquery)
    }


# =============================================================================
# 6. FULL DIAGNOSTICS (combines all metrics)
# =============================================================================

def calculate_full_diagnostics(authority_name: str = None, year: str = "2024", cpv_domain: str = None) -> Dict[str, Any]:
    """Runs all diagnostic metrics and returns a combined result dict.
    If cpv_domain is provided, it is used for metrics that depend on CPV filtering.
    """
    # Determine CPV domain to use for metrics that need it
    cpv_to_use = cpv_domain
    if not cpv_to_use and authority_name:
        # Find dominant CPV domain for the authority
        cypher_domain = """
        MATCH (u:Buyer)-[:AWARDS]-(c:Award)
        WHERE ANY(n IN u.name WHERE n = $authority)
          AND c.cpv_code IS NOT NULL
        WITH substring(c.cpv_code, 0, 5) AS cpv_domain, count(c) AS cnt
        ORDER BY cnt DESC
        RETURN cpv_domain LIMIT 1
        """
        domain_res = execute_cypher(cypher_domain, {"authority": authority_name}, format_output=False)
        if isinstance(domain_res, list) and domain_res and isinstance(domain_res[0], dict):
            cpv_to_use = domain_res[0].get("cpv_domain")
    # Base authority diagnostics — supports CPV-only mode via cpv_domain param
    base = calculate_authority_diagnostics(authority_name, year, cpv_domain=cpv_to_use)
    entropy = calculate_network_entropy(year, cpv_to_use)
    conditional = calculate_conditional_entropy(year, cpv_to_use)
    ici = calculate_ici(authority_name, cpv_domain=cpv_to_use) if authority_name else {"status": "no_data"}
    vcd = calculate_vcd(year=year, cpv_domain=cpv_to_use)
    recurrence = calculate_recurrence_signals(year=year, cpv_domain=cpv_to_use)

    return {
        "requested_authority": authority_name,
        "requested_year": year,
        "requested_cpv": cpv_domain,
        "is_cpv_filtered": bool(cpv_domain and cpv_domain != "ALL"),
        "base": base,
        "network_entropy": entropy,
        "conditional_entropy": conditional,
        "ici": ici,
        "vcd": vcd,
        "recurrence": recurrence,
    }
import math
from typing import Dict, Any

def interpret_hhi(hhi: float) -> dict:
    hhi = hhi or 0.0
    if hhi > 0.25:
        interp, rule, act = "Υψηλή (High)", "hhi > 0.25", "Εξετάστε ενίσχυση ανταγωνιστικών διαδικασιών"
    elif hhi > 0.15:
        interp, rule, act = "Μέτρια (Medium)", "0.15 < hhi <= 0.25", "Παρακολούθηση συγκέντρωσης"
    else:
        interp, rule, act = "Χαμηλή (Low)", "hhi <= 0.15", "Καμία απαιτούμενη ενέργεια"
    return {"raw": hhi, "trans": None, "interp": interp, "rule": rule, "action": act}

def interpret_pa(pa: float) -> dict:
    pa = pa or 0.0
    band = math.log10(pa + 1)
    if band > 7:
        interp, rule, act = "Υψηλή (High)", "band > 7", "Ελέγξτε επαναλαμβανόμενη ανάθεση σε συγκεκριμένους αναδόχους"
    elif band > 5:
        interp, rule, act = "Μέτρια (Medium)", "band > 5", "Παρακολούθηση προτίμησης αναδόχων"
    else:
        interp, rule, act = "Χαμηλή (Low)", "band <= 5", "Καμία απαιτούμενη ενέργεια"
    return {"raw": pa, "trans": f"log10(PA+1) = {band:.2f}", "interp": interp, "rule": rule, "action": act}

def interpret_hf(hf: float) -> dict:
    hf = hf or 0.0
    if hf > 2.0:
        interp, rule, act = "Υψηλή (High)", "hf > 2.0", "Διερευνήστε ρουτινοποιημένες αναθέσεις"
    elif hf > 1.2:
        interp, rule, act = "Μέτρια (Medium)", "hf > 1.2", "Παρακολούθηση ιστορικής συχνότητας"
    else:
        interp, rule, act = "Χαμηλή (Low)", "hf <= 1.2", "Καμία απαιτούμενη ενέργεια"
    return {"raw": hf, "trans": None, "interp": interp, "rule": rule, "action": act}

def interpret_aa(aa: float) -> dict:
    aa = aa or 0.0
    return {"raw": aa, "trans": None, "interp": "Δεν υπάρχει διαθέσιμος κανόνας", "rule": "-", "action": "-"}

def interpret_vcd(vcd: float) -> dict:
    vcd = vcd or 0.0
    if vcd > 0.4:
        interp, rule, act = "Υψηλή απόκλιση (High divergence)", "vcd > 0.4", "Ελέγξτε ασυμμετρία αξίας/όγκου"
    elif vcd > 0.2:
        interp, rule, act = "Μέτρια απόκλιση (Medium divergence)", "0.2 < vcd <= 0.4", "Παρακολούθηση απόκλισης"
    else:
        interp, rule, act = "Χαμηλή απόκλιση (Low divergence)", "vcd <= 0.2", "Καμία απαιτούμενη ενέργεια"
    return {"raw": vcd, "trans": None, "interp": interp, "rule": rule, "action": act}

def interpret_entropy(ent: float) -> dict:
    ent = ent or 0.0
    if ent < 0.4:
        interp, rule, act = "Χαμηλή ποικιλία (Low diversity) / Υψηλή συγκέντρωση", "entropy_norm < 0.4", "Διερευνήστε περιορισμένη ποικιλία συμμετεχόντων"
    elif ent < 0.7:
        interp, rule, act = "Μέτρια ποικιλία (Medium diversity)", "0.4 <= entropy_norm < 0.7", "Παρακολούθηση ποικιλίας συμμετεχόντων"
    else:
        interp, rule, act = "Υψηλή ποικιλία (High diversity)", "entropy_norm >= 0.7", "Καμία απαιτούμενη ενέργεια"
    return {"raw": ent, "trans": None, "interp": interp, "rule": rule, "action": act}

def interpret_ici(ici: float) -> dict:
    ici = ici or 0.0
    if ici > 0.1:
        interp, rule, act = "Υψηλό κλείσιμο (High closure)", "ici > 0.1", "Απαιτείται έλεγχος θεσμικού κλεισίματος"
    elif ici > 0.02:
        interp, rule, act = "Μέτριο κλείσιμο (Medium closure)", "0.02 < ici <= 0.1", "Παρακολούθηση θεσμικού περιβάλλοντος"
    else:
        interp, rule, act = "Χαμηλό κλείσιμο (Low closure)", "ici <= 0.02", "Καμία απαιτούμενη ενέργεια"
    return {"raw": ici, "trans": None, "interp": interp, "rule": rule, "action": act}

def format_interpretation(name: str, res: dict) -> str:
    lines = []
    lines.append(f"**Metric:** {name}  ")
    val_str = f"{res['raw']:,.4f}" if isinstance(res['raw'], float) else f"{res['raw']}"
    lines.append(f"**Value:** {val_str}  ")
    if res.get('trans'):
        lines.append(f"**Scale:** {res['trans']}  ")
    lines.append(f"**Interpretation:** {res['interp']}  ")
    lines.append(f"**Rule:** {res['rule']}  ")
    lines.append(f"**Action:** {res['action']}")
    return "\n".join(lines) + "\n"

# =============================================================================
# 6. DIAGNOSTIC REASONING (Report Generator)
# =============================================================================

def get_diagnostic_reasoning(diag_data: Dict[str, Any]) -> str:
    """
    Generates a strict, rule-based, deterministic diagnostic report from metrics.
    """
    if "base" in diag_data:
        base = diag_data["base"]
        entropy = diag_data.get("network_entropy", {})
        cond = diag_data.get("conditional_entropy", {})
        ici_data = diag_data.get("ici", {})
        vcd_data = diag_data.get("vcd", {})
        recurrence_data = diag_data.get("recurrence", {})
    else:
        base = diag_data
        entropy = {}
        cond = {}
        ici_data = {}
        vcd_data = {}
        recurrence_data = {}

    if base.get("status") == "no_data":
        has_data = (
            entropy.get("status") == "ok"
            or vcd_data.get("status") == "ok"
            or recurrence_data.get("status") == "ok"
        )
        if not has_data:
            return "Δεν υπάρχουν επαρκή δεδομένα για διάγνωση."
        metrics = {"hhi": 0.0, "top_supplier_share": 0.0, "vendor_diversity": 0, "total_spend": 0.0}
    else:
        metrics = base["metrics"]

    authority = (
        diag_data.get("requested_authority")
        or base.get("authority")
        or diag_data.get("authority")
        or "Μη προσδιορισμένη αναθέτουσα αρχή"
    )
    
    year = (
        diag_data.get("requested_year")
        or base.get("year")
        or entropy.get("year")
        or vcd_data.get("year")
        or ""
    )

    cpv_code = (
        diag_data.get("requested_cpv")
        or base.get("cpv_domain")
        or entropy.get("cpv_domain")
        or vcd_data.get("cpv_domain")
    )
    
    year_str = f" (Έτος {year})" if year and str(year).isdigit() else ""

    hhi = metrics.get("hhi", 0.0)
    diversity = metrics.get("vendor_diversity", 0)
    total_contracts = metrics.get("contract_count")

    is_filtered = diag_data.get("is_cpv_filtered")
    if is_filtered is None:
        is_filtered = True if (cpv_code and cpv_code != "ALL") else False

    report = ""
    
    # 0. DATA SCOPE
    report += f"### 📌 DATA SCOPE\n\n"
    
    if authority != "Μη προσδιορισμένη αναθέτουσα αρχή" and cpv_code:
        dataset_type = "Filtered subset (authority + CPV-level analysis)"
    elif authority != "Μη προσδιορισμένη αναθέτουσα αρχή" and not cpv_code:
        dataset_type = "Full procurement of authority"
    else:
        dataset_type = "CPV-domain analysis (no authority filter)"

    report += f"- Authority: {authority}\n"
    report += f"- Year: {year if year else 'ALL'}\n"
    report += f"- CPV filter: {cpv_code if cpv_code else 'ALL'}\n"
    report += f"- Dataset type: {dataset_type}\n\n"
    
    if cpv_code and cpv_code != "ALL":
        report += "⚠️ Η ανάλυση βασίζεται σε υποσύνολο συμβάσεων και δεν αντιπροσωπεύει το σύνολο των αναθέσεων της αναθέτουσας αρχής.\n\n"

    # 1. MARKET STRUCTURE
    report += f"### 🏢 MARKET STRUCTURE (Authority Level)\n"
    report += f"Scope: Επίπεδο Αναθέτουσας Αρχής (ανά έτος)\n\n"
    report += f"Μοναδικοί ανάδοχοι: {diversity} (στο συγκεκριμένο σύνολο δεδομένων)\n"
    if total_contracts is not None:
        report += f"Σύνολο συμβάσεων: {total_contracts}\n"
    report += "\n"
    
    hhi_res = interpret_hhi(hhi)
    report += format_interpretation("HHI", hhi_res)
    report += "\n"

    if ici_data.get("status") == "ok":
        ici_res = interpret_ici(ici_data.get("ici", 0.0))
        report += format_interpretation("ICI", ici_res)
        report += "\n"

    # 2. NETWORK STRUCTURE
    report += f"### 🌐 NETWORK STRUCTURE (Market Level)\n"
    report += f"Scope: Δίκτυο αγοράς (network-level)\n\n"

    hy_norm = entropy.get("H_Y_normalized") if entropy.get("status") == "ok" and entropy.get("H_Y_normalized") is not None else None
    if hy_norm is not None:
        ent_res = interpret_entropy(hy_norm)
        report += format_interpretation("Entropy_normalized H(Y)", ent_res)
        report += "\n"

    vcd_t = vcd_data.get("vcd_total")
    if vcd_data.get("status") == "ok" and vcd_t is not None:
        vcd_res = interpret_vcd(vcd_t)
        report += format_interpretation("VCD", vcd_res)
        report += "\n"

    # 3. RECURRENCE
    report += f"### 🔁 RECURRENCE (Multi-year Network)\n"
    report += f"Scope: Πολυετές Δίκτυο Αγοράς\n\n"
    if recurrence_data.get("status") == "ok":
        pa_res = interpret_pa(recurrence_data.get("pa_mean", 0.0))
        report += format_interpretation("PA_mean", pa_res)
        report += "\n"

        hf_res = interpret_hf(recurrence_data.get("hf_mean", 0.0))
        report += format_interpretation("HF_mean", hf_res)
        report += "\n"
        
        aa_res = interpret_aa(recurrence_data.get("aa_mean", 0.0))
        report += format_interpretation("AA_mean", aa_res)
        report += "\n"
    else:
        report += "Δεν υπάρχουν επαρκή δεδομένα δικτύου για ανάλυση επαναληψιμότητας.\n\n"

    # 4. FINAL DIAGNOSIS
    report += f"### 📊 FINAL DIAGNOSIS\n\n"
    
    report += format_interpretation("HHI", hhi_res)
    report += "\n"
    
    if recurrence_data.get("status") == "ok":
        report += format_interpretation("HF_mean", hf_res)
        report += "\n"
        report += format_interpretation("PA_mean", pa_res)
        report += "\n"
        
    if ici_data.get("status") == "ok":
        report += format_interpretation("ICI", ici_res)
        report += "\n"

    return report
