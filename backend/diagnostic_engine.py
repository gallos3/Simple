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
    cypher = f"""
    MATCH (u:Buyer)-[:AWARDS]-(c:Award)-[:WON_BY]-(w:Winner)
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
    MATCH (u:Buyer)-[:AWARDS]-(c:Award)-[:WON_BY]-(w:Winner)
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
        "base": base,
        "network_entropy": entropy,
        "conditional_entropy": conditional,
        "ici": ici,
        "vcd": vcd,
        "recurrence": recurrence,
    }
# =============================================================================
# 6. DIAGNOSTIC REASONING (Report Generator)
# =============================================================================

def get_diagnostic_reasoning(diag_data: Dict[str, Any]) -> str:
    """
    Generates a structured, analytical diagnostic report from the metrics.
    """
    # Detect input format
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

    # For CPV-only queries, base has no_data but entropy/VCD/recurrence may still be populated.
    # Only hard-exit if ALL metrics are empty.
    if base.get("status") == "no_data":
        has_data = (
            entropy.get("status") == "ok"
            or vcd_data.get("status") == "ok"
            or recurrence_data.get("status") == "ok"
        )
        if not has_data:
            return "Δεν υπάρχουν επαρκή δεδομένα για διάγνωση."
        # CPV-only mode: use empty authority placeholders
        metrics = {"hhi": 0.0, "top_supplier_share": 0.0, "vendor_diversity": 0, "total_spend": 0.0}
        authority = entropy.get("cpv_domain") or vcd_data.get("cpv_domain") or "CPV Domain"
        year = entropy.get("year") or vcd_data.get("year") or ""
    else:
        metrics = base["metrics"]
        authority = base.get("authority", "Φορέας")
        year = base.get("year", "")
    year_str = f" (Έτος {year})" if year and str(year).isdigit() else ""

    hhi = metrics.get("hhi", 0.0)
    top_share = metrics.get("top_supplier_share", 0.0)
    diversity = metrics.get("vendor_diversity", 0)
    total_spend = metrics.get("total_spend", 0.0)

    # ----------------------------------------------------
    # 1. MARKET STRUCTURE
    # ----------------------------------------------------
    report = f"### 📊 1. MARKET STRUCTURE (Δομή Αγοράς)\n"
    report += f"- **Αναθέτουσα Αρχή**: **{authority}**{year_str}\n"
    hhi_str = f"{hhi:.4f}".replace(".", ",")
    share_str = f"{top_share*100:.1f}".replace(".", ",")
    report += f"- **HHI (Συγκέντρωση Αγοράς)**: `{hhi_str}` | **Κορυφαίο Μερίδιο Αναδόχου**: `{share_str}%` | **Μοναδικοί Ανάδοχοι**: {diversity}\n"
    
    # Entropy/HHI interpretation:
    # High HHI + low entropy -> strong concentration
    # Low HHI + high VCD -> hidden (скрытая) concentration
    vcd_t = vcd_data.get("vcd_total") or 0.0
    hy_norm = entropy.get("H_Y_normalized") if entropy.get("H_Y_normalized") is not None else 1.0
    
    if hhi > 0.15:
        if hy_norm < 0.7:
            report += "> ⚠️ **Market Concentration**: Strong concentration detected. High market concentration (HHI) combined with low network entropy H(Y) indicates oligopolistic hub dominance.\n"
        else:
            report += "> ⚠️ **Market Concentration**: High market concentration detected. Few suppliers capture a significant market share.\n"
    else:
        if vcd_t > 0.4:
            report += "> 🔍 **Hidden Concentration**: Low HHI accompanied by high VCD suggests a hidden concentration pattern. While contract volume is distributed across multiple players, market value is disproportionately captured by a dominant hub.\n"
        else:
            report += "> ✅ **Market Competition**: Balanced market structure showing low concentration and active competitive dialogue.\n"

    # Network Entropy
    if entropy.get("status") == "ok":
        hx_norm = entropy.get("H_X_normalized", 1.0)
        report += f"- **Network Entropy**: H(X) = `{entropy.get('H_X', 0.0):.3f}` (Norm: `{hx_norm:.3f}`) | H(Y) = `{entropy.get('H_Y', 0.0):.3f}` (Norm: `{hy_norm:.3f}`)\n"
        if hx_norm < 0.7:
            report += "  → Oligopsonistic patterns: the demand side is dominated by a few contracting authorities.\n"
        if hy_norm < 0.7:
            report += "  → Oligopolistic patterns: the supply side is dominated by a few key contractors.\n"

    # Conditional Entropy
    if cond.get("status") == "ok":
        hyx = cond.get("H_Y_given_X", 0.0)
        hxy = cond.get("H_X_given_Y", 0.0)
        report += f"- **Conditional Entropy**: H(Y|X) = `{hyx:.3f}` | H(X|Y) = `{hxy:.3f}`\n"
        if hyx <= 1.0:
            report += "  → 🚩 **Preferential Treatment**: Low conditional entropy H(Y|X) indicates that contracting authorities systematically direct awards to specific suppliers.\n"
        if hxy <= 1.0:
            report += "  → 🚩 **Vendor Lock-in / Dependence**: Low conditional entropy H(X|Y) indicates that suppliers are structurally dependent on a very small set of buyers.\n"

    # ----------------------------------------------------
    # 2. DIVERGENCE ANALYSIS (VCD)
    # ----------------------------------------------------
    report += f"\n### 📈 2. DIVERGENCE ANALYSIS (Ανάλυση VCD)\n"
    if vcd_data.get("status") == "ok":
        rho = vcd_data.get("spearman_rho", 0.0)
        rho_vcd = vcd_data.get("rho_vcd", 0.0)
        dg = vcd_data.get("delta_gini", 0.0)
        gv = vcd_data.get("gini_value", 0.0)
        gc_val = vcd_data.get("gini_count", 0.0)
        vcd_norm = vcd_data.get("vcd_normalized", 0.0)
        
        report += f"- **ρ_VCD (Rank Divergence)**: `{rho_vcd:.4f}` (Spearman ρ: `{rho:.4f}`)\n"
        report += f"- **ΔGini (Inequality Divergence)**: `{dg:.4f}` (Gini Value: `{gv:.4f}` | Gini Count: `{gc_val:.4f}`)\n"
        report += f"- **Unified VCD Score (Total)**: `{vcd_t:.4f}` (Normalized: `{vcd_norm:.4f}`)\n"

        # VCD interpretation:
        if vcd_t > 0.4:
            report += "> ⚠️ **Unified Divergence**: Strong structural divergence between participation and value capture detected. Key suppliers are capturing disproportionate contract values while volume distribution seems competitive.\n"
        if dg > 0.1:
            report += "> 🚩 **Inequality Divergence**: Value concentration exceeds participation distribution. The financial inequality among suppliers is much higher than the inequality in the sheer number of contract awards.\n"
    else:
        report += "Δεν υπάρχουν επαρκή δεδομένα VCD για ανάλυση απόκλισης.\n"

    # ----------------------------------------------------
    # 3. RECURRENCE MECHANISMS
    # ----------------------------------------------------
    report += f"\n### 🔄 3. RECURRENCE MECHANISMS (Μηχανισμοί Επαναληψιμότητας)\n"
    if recurrence_data.get("status") == "ok":
        hf_m = recurrence_data.get("hf_mean") or 0.0
        hf_x = recurrence_data.get("hf_max") or 0.0
        pa_m = recurrence_data.get("pa_mean") or 0.0
        aa_m = recurrence_data.get("aa_mean") or 0.0
        
        report += f"- **Historical Frequency (HF_mean)**: `{hf_m:.2f}` (Max: `{hf_x:.0f}`)\n"
        report += f"- **Preferential Attachment (PA_mean)**: `{pa_m:.2f}`\n"
        report += f"- **Adamic-Adar adapted (AA_mean)**: `{aa_m:.4f}`\n"

        # Recurrence interpretation:
        if hf_m > 2.0:
            report += "> ⏳ **Routinised Contracting**: Market exhibits strong historical persistence (routinised contracting) where identical buyer-supplier dyads repeat over years.\n"
        if pa_m > 100.0:
            report += "> 🕸️ **Hub Dominance**: Market structure driven by preferential attachment (hub dominance). Large, well-connected suppliers attract new awards at a faster rate.\n"
        if aa_m > 0.5:
            report += "> 🧩 **Specialised Niche**: Market shows niche or context-dependent matching based on bipartite shared neighbors.\n"

        # Dominant recurrence mechanism using normalized scores
        hf_score = hf_m / 3.0
        pa_score = pa_m / 100.0
        aa_score = aa_m / 0.5
        scores = {"HF": hf_score, "PA": pa_score, "AA": aa_score}
        dom_key = max(scores, key=scores.get)
        
        dom_map = {
            "HF": "routinised continuity",
            "PA": "network-driven concentration",
            "AA": "specialised niche matching"
        }
        report += f"> 🎯 **Dominant Mechanism**: The structural network dynamic is predominantly characterized by **{dom_map[dom_key]}**.\n"
    else:
        report += "Δεν υπάρχουν επαρκή δεδομένα δικτύου για ανάλυση επαναληψιμότητας.\n"

    # ----------------------------------------------------
    # 4. INSTITUTIONAL STRUCTURE (ICI)
    # ----------------------------------------------------
    report += f"\n### 🏢 4. INSTITUTIONAL STRUCTURE (Θεσμικό Κλείσιμο)\n"
    if ici_data.get("status") == "ok":
        ici_val = ici_data.get("ici", 0.0)
        cl_level = ici_data.get("closure_level", "ΧΑΜΗΛΟ")
        fl = ici_data.get("closure_flag", "green")
        fl_icon = "🔴" if fl == "red" else ("🟡" if fl == "yellow" else "🟢")
        
        report += f"- **Institutional Closure Index (ICI)**: `{ici_val:.4f}` {fl_icon} ({cl_level})\n"
        if ici_val > 0.1:
            report += "> ⚠️ **Institutional Closure**: High ICI indicates institutional closure and limited competitive access. Relationships between buyers and suppliers are locked, preventing external entry.\n"
        else:
            report += "> ✅ **Open Procurement**: Low ICI indicates an open, fluid market allowing high player mobility and entry.\n"
    else:
        report += "Δεν υπάρχουν επαρκή δεδομένα για τον υπολογισμό του Institutional Closure Index (ICI).\n"

    # ----------------------------------------------------
    # 5. FINAL DIAGNOSIS
    # ----------------------------------------------------
    report += f"\n### 🩺 5. FINAL DIAGNOSIS (Τελικό Πόρισμα & Θεραπεία)\n"
    
    # Recurrence values for typology classification
    hf_m = (recurrence_data.get("hf_mean") or 0.0) if recurrence_data.get("status") == "ok" else 0.0
    pa_m = (recurrence_data.get("pa_mean") or 0.0) if recurrence_data.get("status") == "ok" else 0.0
    aa_m = (recurrence_data.get("aa_mean") or 0.0) if recurrence_data.get("status") == "ok" else 0.0

    # Market Typology Classification Label
    if hhi > 0.15:
        if vcd_t > 0.4:
            if pa_m > 100.0:
                market_type = "Closed Oligopolistic Hub (High Concentration & High Network Dominance)"
            elif hf_m > 2.0:
                market_type = "Routinised Duopoly / Oligopoly (Persistent Recurrent Imbalance)"
            else:
                market_type = "Standard Concentrated Market (Oligopolistic Capture)"
        else:
            market_type = "Oligopolistic Volume Capture (Concentrated but Value-Proportional)"
    else:
        if vcd_t > 0.4:
            if pa_m > 100.0:
                market_type = "Asymmetric Network-Driven Capture (Hidden Value Concentration via Supplier Position)"
            elif hf_m > 2.0:
                market_type = "Routinised Closed Market (Hidden Persistent Capture)"
            else:
                market_type = "Asymmetric Value-Capture Market (Hidden Concentration)"
        else:
            if aa_m > 0.5:
                market_type = "Specialised Niche Market (High Specialisation / Low General Concentration)"
            else:
                market_type = "Open Competitive Market (Healthy Competitive Dynamics)"

    report += f"- **Market Type (Τυπολογία Αγοράς)**: `{market_type}`\n\n"

    # Combined structural diagnosis
    combined_diagnoses = []
    if vcd_t > 0.4:
        if recurrence_data.get("status") == "ok":
            if pa_m > 100.0:
                combined_diagnoses.append("Concentration driven by network position of key suppliers")
            if hf_m > 2.0:
                combined_diagnoses.append("Persistent incumbency and repeated contracting patterns")
            if aa_m > 0.5:
                combined_diagnoses.append("Specification-driven or niche-based allocation patterns")
    
    if combined_diagnoses:
        report += f"**Structural Insights**:\n"
        for cd in combined_diagnoses:
            report += f"- 🚩 {cd}\n"
    else:
        report += "Market dynamics appear stable, showing no severe systemic imbalances.\n"

    # Therapy recommendations
    needs_action = hhi > 0.15 or top_share > 0.4 or ici_data.get("closure_flag") == "red" or vcd_t > 0.4
    report += "\n**Προτεινόμενη Θεραπεία (Ν.4412/2016)**:\n"
    if needs_action:
        report += "- **Κατάτμηση σε Τμήματα** (Άρθρο 59): Συστήνεται η διαίρεση μεγάλων συμβάσεων σε αυτόνομα τμήματα για την ενθάρρυνση συμμετοχής ΜμΕ.\n"
        report += "- **Market Sounding**: Διενέργεια εκτενούς προκαταρκτικής διαβούλευσης της αγοράς για τον εντοπισμό εναλλακτικών παρόχων.\n"
        if ici_data.get("closure_flag") == "red" or vcd_t > 0.5:
            report += "- **Ειδικός Έλεγχος (Audit)**: Εφαρμογή εντατικών ποιοτικών ελέγχων (Άρθρο 73) λόγω υψηλού βαθμού θεσμικού κλεισίματος ή/και ακραίου value capture.\n"
    else:
        report += "Συνιστάται η διατήρηση της υφιστάμενης στρατηγικής ανοικτού ανταγωνισμού και η συνεχής παρακολούθηση των δεικτών.\n"

    return report
