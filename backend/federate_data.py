"""
Simple_Federated - Federated Data Ingestor (ETL)
==================================================
3-Phase approach (λόγω ξεχωριστών DBMS instances):

  Phase A: Start KHMDHS1  python federate_data.py --extract kimdis
  Phase B: Start Endorse   python federate_data.py --extract ted
  Phase C: Start federated  python federate_data.py --load

ΚΑΝΟΝΑΣ ΑΣΦΑΛΕΙΑΣ: Ποτέ δεν γράφει στις πηγές. Μόνο READ.
"""

import argparse
import json
import sys
import re
import uuid
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from neo4j import GraphDatabase

from entity_resolver import (
    match_buyers,
    MatchResult,
    HIGH_CONFIDENCE,
    MEDIUM_CONFIDENCE,
)

# =============================================================================
# CONFIGURATION
# =============================================================================
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "ohi21365pote"

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

KIMDIS_FILE = DATA_DIR / "kimdis_extract.json"
ENDORSE_FILE = DATA_DIR / "endorse_extract.json"

BATCH_SIZE = 5000


# =============================================================================
# NEO4J HELPER
# =============================================================================
class DBConnector:
    def __init__(self):
        self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        print(f" Connected to Neo4j at {NEO4J_URI}")

    def run(self, query, params=None):
        with self.driver.session() as session:
            result = session.run(query, params or {})
            return [dict(r) for r in result]

    def write(self, query, params=None):
        with self.driver.session() as session:
            session.run(query, params or {})

    def write_batch(self, query, batch):
        with self.driver.session() as session:
            session.run(query, {"batch": batch})

    def close(self):
        self.driver.close()


# =============================================================================
# PHASE A: EXTRACT FROM KIMDIS (KHMDHS1 DBMS must be running)
# =============================================================================
def extract_kimdis():
    print("\n EXTRACT: Reading from KHMDHS1 (KIMDIS API)...")
    conn = DBConnector()

    # Schema discovery
    print("\n Schema Discovery...")
    for label in ["Auth", "AuthUnit", "Awr", "Comp", "Cpv"]:
        rows = conn.run(f"MATCH (n:{label}) RETURN keys(n) AS keys LIMIT 100")
        if rows:
            all_keys = set()
            for r in rows:
                all_keys.update(r.get("keys", []))
            print(f"   :{label}  {sorted(list(all_keys))}")
        else:
            print(f"   :{label}  NOT FOUND")

    # Extract buyers (Auth  AuthUnit)
    buyers_raw = conn.run("""
        MATCH (a:Auth)
        OPTIONAL MATCH (au:AuthUnit)-[:UNIT_OF]->(a)
        RETURN properties(a) AS props,
               properties(au) AS unit_props
    """)
    buyers = []
    for r in buyers_raw:
        p = r.get("props") or {}
        u = r.get("unit_props") or {}
        p["unit_name"] = u.get("name") or u.get("nameRaw") or u.get("authKey")
        buyers.append(p)
    print(f"    Buyers: {len(buyers)}")

    # Extract awards in batches (too many for single query)
    print("    Counting awards...")
    count_result = conn.run("MATCH (awr:Awr)-[:AWARDED]-(au:AuthUnit) RETURN count(DISTINCT awr) AS cnt")
    total = count_result[0]["cnt"] if count_result else 0
    print(f"    Total Awards: {total}")

    PAGE_SIZE = 10000
    awards = []
    for offset in range(0, total, PAGE_SIZE):
        batch = conn.run(f"""
            MATCH (awr:Awr)-[:AWARDED]-(au:AuthUnit)
            OPTIONAL MATCH (au)-[:UNIT_OF]-(auth:Auth)
            OPTIONAL MATCH (awr)-[:WON]-(comp:Comp)
            OPTIONAL MATCH (awr)-[:HAS_CPV]-(cpv:Cpv)
            RETURN properties(au) AS unit_props,
                   properties(awr) AS awr_props,
                   properties(comp) AS comp_props,
                   cpv.code AS cpv_code,
                   auth.vat AS auth_vat
            SKIP {offset} LIMIT {PAGE_SIZE}
        """)
        for r in batch:
            awr = r.get("awr_props") or {}
            unit = r.get("unit_props") or {}
            comp = r.get("comp_props") or {}
            awards.append({
                "awr": {k: awr[k] for k in ["cost_without_vat", "protocol_num", "nuts_code",
                        "ici_deg", "contract_type", "cancellation", "title",
                        "submission_date", "ref"] if k in awr},
                "buyer_name": unit.get("nameRaw") or unit.get("nameNorm", ""),
                "buyer_nuts": unit.get("nuts_code"),
                "buyer_vat": r.get("auth_vat"),
                "winner_name": comp.get("nameRaw") or comp.get("nameNorm", ""),
                "winner_vat": comp.get("vat"),
                "cpv_code": r.get("cpv_code"),
            })
        print(f"      Batch {offset//PAGE_SIZE+1}: {len(batch)} rows (total: {len(awards)})")

    conn.close()

    # Save to JSON
    data = {"source": "KIMDIS_API", "timestamp": datetime.now().isoformat(),
            "buyers": buyers, "awards": awards}
    with open(KIMDIS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)
    size_mb = KIMDIS_FILE.stat().st_size / (1024*1024)
    print(f"\n Saved to {KIMDIS_FILE} ({size_mb:.1f} MB)")


# =============================================================================
# PHASE B: EXTRACT FROM ENDORSE (Endorse DBMS must be running)
# =============================================================================
def extract_endorse():
    print("\n EXTRACT: Reading from Endorse (TED)...")
    conn = DBConnector()

    # Schema discovery
    print("\n Schema Discovery...")
    for label in ["Authority", "ContractAward", "Company", "Notice", "Lot", "CPV"]:
        rows = conn.run(f"MATCH (n:{label}) RETURN keys(n) AS keys LIMIT 100")
        if rows:
            all_keys = set()
            for r in rows:
                all_keys.update(r.get("keys", []))
            print(f"   :{label}  {sorted(list(all_keys))}")
        else:
            print(f"   :{label}  NOT FOUND")

    # Extract buyers
    buyers_raw = conn.run("MATCH (a:Authority) RETURN properties(a) AS props")
    buyers = []
    for r in buyers_raw:
        p = r.get("props") or {}
        p["name"] = p.get("legalName") or p.get("officialName")
        p["nuts_code"] = p.get("nuts3") or p.get("nuts_code") # Map nuts3 to nuts_code for consistency
        buyers.append(p)
    print(f"    Buyers: {len(buyers)}")

    # Extract awards in batches (too many for single query)
    print("    Counting awards...")
    count_result = conn.run("MATCH (ca:ContractAward) RETURN count(ca) AS cnt")
    total = count_result[0]["cnt"] if count_result else 0
    print(f"    Total Awards: {total}")

    # Open file for streaming to prevent MemoryError
    print(f"\n Streaming output to {ENDORSE_FILE}...")
    with open(ENDORSE_FILE, "w", encoding="utf-8") as f:
        # Write header
        ts = datetime.now().isoformat()
        f.write('{\n  "source": "TED",\n  "timestamp": "' + ts + '",\n')
        
        # Write buyers
        import json as built_in_json
        f.write('  "buyers": [\n')
        for i, b in enumerate(buyers):
            f.write("    " + built_in_json.dumps(b, ensure_ascii=False, default=str))
            f.write(",\n" if i < len(buyers) - 1 else "\n")
        f.write('  ],\n')
        
        f.write('  "awards": [\n')
        
        first_award = True
        PAGE_SIZE = 10000
        for offset in range(0, total, PAGE_SIZE):
            batch = conn.run(f"""
                MATCH (ca:ContractAward)
                WITH ca ORDER BY id(ca)
                SKIP {offset} LIMIT {PAGE_SIZE}
                OPTIONAL MATCH (ca)-[:awardedTo]->(comp:Company)
                WITH ca, collect(DISTINCT comp) AS comps
                OPTIONAL MATCH (ca)-[:belongsToLot]->(lot:Lot)
                WITH ca, comps, collect(DISTINCT lot) AS lots
                OPTIONAL MATCH (ca)-[:issuedBy]->(auth_d:Authority)
                OPTIONAL MATCH (ca)-[:belongsToLot]->(:Lot)<-[:hasLot]-(:Notice)-[:publishedBy]->(auth_i:Authority)
                WITH ca, comps, lots, collect(DISTINCT auth_d) + collect(DISTINCT auth_i) AS all_auths
                RETURN properties(ca) AS ca_props,
                       [c IN comps | properties(c)] AS comp_props_list,
                       [l IN lots | properties(l)] AS lot_props_list,
                       [a IN all_auths WHERE a IS NOT NULL | properties(a)] AS auth_props_list
            """)
            
            rows_in_batch = 0
            for r in batch:
                ca = r.get("ca_props") or {}
                comp_list = r.get("comp_props_list") or [{}]
                lot_list = r.get("lot_props_list") or [{}]
                auth_list = r.get("auth_props_list") or [{}]
                
                # Cartesian product in Python (flat dicts for the loader)
                for comp in comp_list:
                    for lot in lot_list:
                        for auth in auth_list:
                            aw_dict = {
                                "ca": {k: ca[k] for k in ["contractValue", "value", "awardYear", "year", "identifier", "deg", "mainCPV"] if k in ca},
                                "buyer_name": auth.get("legalName") or auth.get("officialName"),
                                "buyer_vat": auth.get("VATNumber") or auth.get("vat"),
                                "buyer_nuts": auth.get("nuts3") or auth.get("nuts_code") or auth.get("nuts"),
                                "winner_name": comp.get("legalName"),
                                "winner_vat": comp.get("VATNumber") or comp.get("vat"),
                                "lot_id": lot.get("identifier"),
                                "lot_cpv": lot.get("mainCPV")
                            }
                            
                            if not first_award:
                                f.write(",\n")
                            first_award = False
                            f.write("    " + built_in_json.dumps(aw_dict, ensure_ascii=False, default=str))
                            rows_in_batch += 1
                            
            print(f"      Batch {offset//PAGE_SIZE+1}: Generated {rows_in_batch} JSON objects")

        f.write('\n  ]\n}\n')

    conn.close()
    size_mb = ENDORSE_FILE.stat().st_size / (1024*1024)
    print(f"\n Saved to {ENDORSE_FILE} ({size_mb:.1f} MB)")


# =============================================================================
# PHASE C: ENTITY RESOLUTION + LOAD (federated DBMS must be running)
# =============================================================================
class EntityRegistry:
    def __init__(self):
        self.buyers = []
        self.winners = []
        self.merge_log = []
        self.pending_review = []
        self._buyer_vat_idx = {}
        self._winner_vat_idx = {}
        self._buyer_name_idx = {}
        self._winner_name_idx = {}

    def _clean_vat(self, vat):
        if not vat: return None
        clean = re.sub(r"[^0-9]", "", str(vat))
        return clean if len(clean) >= 5 else None

    def _normalize(self, name):
        if not name: return ""
        n = name.lower()
        n = "".join(c for c in unicodedata.normalize("NFD", n) if unicodedata.category(c) != "Mn")
        return re.sub(r"[^\w\s]", "", n).replace(" ", "")

    def register_buyer(self, buyer_data, source):
        vat = buyer_data.get("vat") or buyer_data.get("VATNumber")
        clean_vat = self._clean_vat(vat)
        name = buyer_data.get("name") or ""
        norm_name = self._normalize(name)
        
        # 1. O(1) Exact Name match (VAT auto-merge removed to preserve decentralized units)
        if norm_name and norm_name in self._buyer_name_idx:
            existing = self._buyer_name_idx[norm_name]
            existing.setdefault("aliases", []).append(name)
            existing.setdefault("sources", set()).add(source)
            self.merge_log.append({
                "type": "buyer", "canonical": existing["name"],
                "merged": name, "score": 1.0,
            })
            if clean_vat and not existing.get("vat"):
                existing["vat"] = clean_vat
                self._buyer_vat_idx[clean_vat] = existing
            return

        # 3. New Entity
        buyer_data.setdefault("sources", set()).add(source)
        buyer_data["aliases"] = []
        self.buyers.append(buyer_data)
        if clean_vat:
            self._buyer_vat_idx[clean_vat] = buyer_data
        if norm_name:
            self._buyer_name_idx[norm_name] = buyer_data

    def register_winner(self, winner_data, source):
        vat = winner_data.get("vat") or winner_data.get("VATNumber")
        clean_vat = self._clean_vat(vat)
        name = winner_data.get("name") or ""
        norm_name = self._normalize(name)

        if clean_vat and clean_vat in self._winner_vat_idx:
            existing = self._winner_vat_idx[clean_vat]
            existing.setdefault("aliases", []).append(name)
            existing.setdefault("sources", set()).add(source)
            self.merge_log.append({
                "type": "winner", "canonical": existing["name"],
                "merged": name, "score": 1.0,
            })
            return

        if norm_name and norm_name in self._winner_name_idx:
            existing = self._winner_name_idx[norm_name]
            existing.setdefault("aliases", []).append(name)
            existing.setdefault("sources", set()).add(source)
            self.merge_log.append({
                "type": "winner", "canonical": existing["name"],
                "merged": name, "score": 1.0,
            })
            if clean_vat and not existing.get("vat"):
                existing["vat"] = clean_vat
                self._winner_vat_idx[clean_vat] = existing
            return

        winner_data.setdefault("sources", set()).add(source)
        winner_data["aliases"] = []
        self.winners.append(winner_data)
        if clean_vat:
            self._winner_vat_idx[clean_vat] = winner_data
        if norm_name:
            self._winner_name_idx[norm_name] = winner_data


def load_to_federated(dry_run=False):
    import ijson
    print("\nLOAD: Entity Resolution + Write to federated (Streaming mode)...")

    if not KIMDIS_FILE.exists() and not ENDORSE_FILE.exists():
        print(" No data to load. Extract first!")
        return

    # --- Entity Resolution ---
    print("\nResolution...")
    registry = EntityRegistry()

    # 1. Register Buyers
    if KIMDIS_FILE.exists():
        print("   Streaming KIMDIS Buyers...")
        with open(KIMDIS_FILE, "rb") as f:
            for b in ijson.items(f, 'buyers.item', use_float=True):
                registry.register_buyer({"name": b.get("unit_name") or b.get("name"), "vat": b.get("vat") or b.get("afm"), "nuts_code": b.get("nuts_code")}, "KIMDIS_API")

    if ENDORSE_FILE.exists():
        print("   Streaming ENDORSE Buyers...")
        with open(ENDORSE_FILE, "rb") as f:
            for b in ijson.items(f, 'buyers.item', use_float=True):
                registry.register_buyer({"name": b.get("name"), "vat": b.get("VATNumber"), "nuts_code": b.get("nuts_code")}, "TED")

    # 2. Register Winners
    seen = set()
    if KIMDIS_FILE.exists():
        print("   Streaming KIMDIS Winners...")
        with open(KIMDIS_FILE, "rb") as f:
            for a in ijson.items(f, 'awards.item', use_float=True):
                wn = a.get("winner_name")
                if wn and wn not in seen:
                    registry.register_winner({"name": wn, "vat": a.get("winner_vat")}, "KIMDIS_API")
                    seen.add(wn)

    if ENDORSE_FILE.exists():
        print("   Streaming ENDORSE Winners...")
        with open(ENDORSE_FILE, "rb") as f:
            for a in ijson.items(f, 'awards.item', use_float=True):
                wn = a.get("winner_name")
                if wn and wn not in seen:
                    registry.register_winner({"name": wn, "vat": a.get("winner_vat")}, "TED")
                    seen.add(wn)

    print(f"\n    Results:")
    print(f"      Unique Buyers:  {len(registry.buyers)}")
    print(f"      Unique Winners: {len(registry.winners)}")
    print(f"      Auto-merged:    {len(registry.merge_log)}")
    print(f"      Pending Review: {len(registry.pending_review)}")

    if dry_run:
        print("\nDRY RUN: No writes.")
        return

    print("\nWriting to federated database...")
    conn = DBConnector()

    # Schema
    for q in [
        "CREATE CONSTRAINT buyer_name IF NOT EXISTS FOR (n:Buyer) REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT winner_name IF NOT EXISTS FOR (n:Winner) REQUIRE n.name IS UNIQUE",
        "CREATE CONSTRAINT award_id IF NOT EXISTS FOR (a:Award) REQUIRE a.identifier IS UNIQUE",
        "CREATE INDEX award_source IF NOT EXISTS FOR (a:Award) ON (a.source)",
    ]:
        try: conn.write(q)
        except Exception as e: print(f"    {e}")

    # Insert Buyers
    buyers_list = [{"name": b["name"], "sources": list(b.get("sources", [])),
               "aliases": b.get("aliases", []), "vat": b.get("vat"),
               "nuts_code": b.get("nuts_code")} for b in registry.buyers if b.get("name")]
    for i in range(0, len(buyers_list), BATCH_SIZE):
        chunk = buyers_list[i:i+BATCH_SIZE]
        conn.write_batch("""
            UNWIND $batch AS row
            MERGE (b:Buyer {name: row.name})
            SET b.sources = row.sources, b.aliases = row.aliases,
                b.vat = row.vat, b.nuts_code = row.nuts_code, b.ingested_at = datetime(),
                b.`rdf:type` = 'http://data.europa.eu/a4g/ontology#Buyer'
        """, chunk)
    print(f"    {len(buyers_list)} buyers loaded")

    # Insert Winners
    winners_list = [{"name": w["name"], "sources": list(w.get("sources", [])),
               "vat": w.get("vat")} for w in registry.winners if w.get("name")]
    for i in range(0, len(winners_list), BATCH_SIZE):
        chunk = winners_list[i:i+BATCH_SIZE]
        conn.write_batch("""
            UNWIND $batch AS row
            MERGE (w:Winner {name: row.name})
            SET w.sources = row.sources, w.vat = row.vat, w.ingested_at = datetime(),
                w.`rdf:type` = 'http://data.europa.eu/a4g/ontology#Winner'
        """, chunk)
    print(f"    {len(winners_list)} winners loaded")

    # Insert Awards (KIMDIS)
    if KIMDIS_FILE.exists():
        print("    Inserting KIMDIS awards...")
        batch = []
        with open(KIMDIS_FILE, "rb") as f:
            for a in ijson.items(f, 'awards.item', use_float=True):
                awr = a.get("awr", {})
                # Skip cancelled/voided awards
                cancel = awr.get("cancellation")
                if cancel and str(cancel).lower() not in ("false", "none", "", "0"):
                    continue
                orig_id = str(awr.get("ref") or "")
                if not orig_id or orig_id == "UNKNOWN" or orig_id == "None":
                    orig_id = "UNKNOWN_" + uuid.uuid4().hex
                batch.append({
                    "buyer": a.get("buyer_name") or "UNKNOWN",
                    "id": orig_id,
                    "identifier": "KIMDIS_" + orig_id,
                    "value": awr.get("cost_without_vat"),
                    "deg": awr.get("ici_deg"),
                    "cpv": a.get("cpv_code"),
                    "nuts": a.get("buyer_nuts"),
                    "winner": a.get("winner_name"),
                    "title": awr.get("title"),
                    "date": awr.get("submission_date"),
                    "buyer_vat": a.get("buyer_vat")
                })
                if len(batch) >= BATCH_SIZE:
                    conn.write_batch("""
                        UNWIND $batch AS row
                        MERGE (b:Buyer {name: row.buyer})
                        SET b.vat = coalesce(b.vat, row.buyer_vat), b.nuts_code = coalesce(b.nuts_code, row.nuts)
                        MERGE (a:Award {identifier: row.identifier})
                        ON CREATE SET a.original_id = row.id, a.value = toFloat(row.value), 
                            a.deg = toFloat(row.deg), a.cpv_code = row.cpv, a.nuts_code = row.nuts,
                            a.title = row.title, a.submission_date = row.date,
                            a.source = "KIMDIS_API", a.ingested_at = datetime(),
                            a.`rdf:type` = 'http://data.europa.eu/a4g/ontology#ContractAward'
                        MERGE (b)-[:AWARDS]->(a)
                        WITH a, row WHERE row.winner IS NOT NULL
                        MERGE (w:Winner {name: row.winner})
                        MERGE (a)-[:WON_BY]->(w)
                    """, batch)
                    batch = []
        if batch:
            conn.write_batch("""
                        UNWIND $batch AS row
                        MERGE (b:Buyer {name: row.buyer})
                        SET b.vat = coalesce(b.vat, row.buyer_vat), b.nuts_code = coalesce(b.nuts_code, row.nuts)
                        MERGE (a:Award {identifier: row.identifier})
                        ON CREATE SET a.original_id = row.id, a.value = toFloat(row.value), 
                            a.deg = toFloat(row.deg), a.cpv_code = row.cpv, a.nuts_code = row.nuts,
                            a.title = row.title, a.submission_date = row.date,
                            a.source = "KIMDIS_API", a.ingested_at = datetime(),
                            a.`rdf:type` = 'http://data.europa.eu/a4g/ontology#ContractAward'
                        MERGE (b)-[:AWARDS]->(a)
                        WITH a, row WHERE row.winner IS NOT NULL
                        MERGE (w:Winner {name: row.winner})
                        MERGE (a)-[:WON_BY]->(w)
            """, batch)
            
    # Insert Awards (ENDORSE)
    if ENDORSE_FILE.exists():
        print("    Inserting ENDORSE awards...")
        batch = []
        with open(ENDORSE_FILE, "rb") as f:
            for a in ijson.items(f, 'awards.item', use_float=True):
                ca = a.get("ca", {})
                orig_id = str(ca.get("identifier") or "")
                if not orig_id or orig_id == "UNKNOWN" or orig_id == "None":
                    orig_id = "UNKNOWN_" + uuid.uuid4().hex
                batch.append({
                    "buyer": a.get("buyer_name") or "UNKNOWN",
                    "id": orig_id,
                    "identifier": "TED_" + orig_id,
                    "value": ca.get("value") or ca.get("contractValue"),
                    "year": ca.get("year") or ca.get("awardYear"),
                    "deg": ca.get("deg"),
                    "cpv": ca.get("mainCPV"),
                    "nuts": a.get("buyer_nuts"),
                    "winner": a.get("winner_name"),
                    "buyer_vat": a.get("buyer_vat")
                })
                if len(batch) >= BATCH_SIZE:
                    conn.write_batch("""
                        UNWIND $batch AS row
                        MERGE (b:Buyer {name: row.buyer})
                        SET b.vat = coalesce(b.vat, row.buyer_vat), b.nuts_code = coalesce(b.nuts_code, row.nuts)
                        MERGE (a:Award {identifier: row.identifier})
                        ON CREATE SET a.original_id = row.id, a.value = toFloat(row.value), a.year = toInteger(row.year),
                            a.deg = row.deg, a.cpv_code = row.cpv, a.nuts_code = row.nuts,
                            a.source = "TED", a.ingested_at = datetime(),
                            a.`rdf:type` = 'http://data.europa.eu/a4g/ontology#ContractAward'
                        MERGE (b)-[:AWARDS]->(a)
                        WITH a, row WHERE row.winner IS NOT NULL
                        MERGE (w:Winner {name: row.winner})
                        MERGE (a)-[:WON_BY]->(w)
                    """, batch)
                    batch = []
        if batch:
            conn.write_batch("""
                        UNWIND $batch AS row
                        MERGE (b:Buyer {name: row.buyer})
                        SET b.vat = coalesce(b.vat, row.buyer_vat), b.nuts_code = coalesce(b.nuts_code, row.nuts)
                        MERGE (a:Award {identifier: row.identifier})
                        ON CREATE SET a.original_id = row.id, a.value = toFloat(row.value), a.year = toInteger(row.year),
                            a.deg = row.deg, a.cpv_code = row.cpv, a.nuts_code = row.nuts,
                            a.source = "TED", a.ingested_at = datetime(),
                            a.`rdf:type` = 'http://data.europa.eu/a4g/ontology#ContractAward'
                        MERGE (b)-[:AWARDS]->(a)
                        WITH a, row WHERE row.winner IS NOT NULL
                        MERGE (w:Winner {name: row.winner})
                        MERGE (a)-[:WON_BY]->(w)
            """, batch)

    # Create LegalEntity hierarchy
    print("   Constructing LegalEntity hierarchy for decentralized units...")
    conn.write_batch("""
        MATCH (b:Buyer) 
        WHERE b.vat IS NOT NULL 
        MERGE (le:LegalEntity {vat: b.vat}) 
        MERGE (b)-[:BELONGS_TO]->(le)
    """, [{"dummy": 1}])
    print("    LegalEntity hierarchy constructed")

    conn.close()
    print("\n Load complete!")

    # Save report
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {"timestamp": ts, "buyers": len(registry.buyers),
              "winners": len(registry.winners), "merged": len(registry.merge_log),
              "pending": len(registry.pending_review),
              "merge_log": registry.merge_log[:50],
              "pending_review": registry.pending_review[:50]}
    rpath = LOG_DIR / f"ingestion_report_{ts}.json"
    with open(rpath, "w", encoding="utf-8") as f:
        import json as built_in_json
        built_in_json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f" Report: {rpath}")


# =============================================================================
# CLI
# =============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simple_Federated ETL")
    parser.add_argument("--extract", choices=["kimdis", "ted"], help="Extract from source DBMS to JSON")
    parser.add_argument("--load", action="store_true", help="Load JSON data into federated DBMS")
    parser.add_argument("--dry-run", action="store_true", help="Entity resolution only, no writes")
    args = parser.parse_args()

    if args.extract == "kimdis":
        extract_kimdis()
    elif args.extract == "ted":
        extract_endorse()
    elif args.load:
        load_to_federated(dry_run=args.dry_run)
    else:
        print("Usage:")
        print("  Step 1: Start KHMDHS1  python federate_data.py --extract kimdis")
        print("  Step 2: Start Endorse   python federate_data.py --extract ted")
        print("  Step 3: Start federated  python federate_data.py --load [--dry-run]")
