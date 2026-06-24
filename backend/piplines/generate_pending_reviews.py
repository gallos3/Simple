"""
Simple Federated - Pending Review Generator
Σαρώνει τους κόμβους (Buyer ή Winner) και εντοπίζει αυτούς που έχουν
πολύ παρόμοιο όνομα, δημιουργώντας τη σχέση :PENDING_REVIEW ώστε να 
εξεταστούν στο Human-in-the-Loop Dashboard.
"""

import argparse
import time
from collections import defaultdict
from itertools import combinations
from typing import List, Dict

from database import get_session
from entity_resolver import similarity_score, token_overlap_score, normalize_greek_name

def block_by_prefix(entities: List[Dict], prefix_len: int = 4) -> Dict[str, List[Dict]]:
    """Ομαδοποιεί τις οντότητες με βάση τους πρώτους χαρακτήρες του normalized name για ταχύτητα."""
    blocks = defaultdict(list)
    for ent in entities:
        norm_name = normalize_greek_name(ent["name"] or "")
        if len(norm_name) >= prefix_len:
            prefix = norm_name[:prefix_len]
        else:
            prefix = norm_name
            
        # Επίσης, κάνουμε block με βάση τα αρχικά γράμματα κάθε λέξης
        words = norm_name.split()
        acronym = "".join([w[0] for w in words if w])[:prefix_len]
        
        blocks[prefix].append(ent)
        if acronym and acronym != prefix:
            blocks[acronym].append(ent)
            
    return blocks

def generate_pending_reviews(label: str, threshold_min: float = 0.75, threshold_max: float = 0.98):
    print(f"[{label}] Έναρξη σάρωσης για διπλοεγγραφές προς αξιολόγηση (HITL)...")
    start_time = time.time()
    
    with get_session() as session:
        # 1. Καθαρισμός παλιών PENDING_REVIEW
        print(f"[{label}] Καθαρισμός παλιών εκκρεμοτήτων...")
        session.run(f"MATCH (a:{label})-[r:PENDING_REVIEW]->(b:{label}) DELETE r")
        
        # 2. Ανάκτηση όλων των οντοτήτων
        print(f"[{label}] Ανάκτηση δεδομένων από Neo4j...")
        # Δεν ελέγχουμε αυτά που έχουν ήδη απορριφθεί στο παρελθόν
        query = f"""
        MATCH (n:{label})
        OPTIONAL MATCH (n)-[rej:REJECTED_MERGE]-(m:{label})
        RETURN id(n) as id, n.name as name, n.vat as vat, collect(id(m)) as rejected_ids
        """
        results = session.run(query)
        entities = []
        for r in results:
            if not r["name"]: continue
            entities.append({
                "id": r["id"],
                "name": r["name"],
                "vat": r["vat"],
                "rejected_ids": set(r["rejected_ids"] if r["rejected_ids"] else [])
            })
            
        print(f"[{label}] Βρέθηκαν {len(entities)} οντότητες.")
        
        # 3. Ομαδοποίηση (Blocking) για αποφυγή O(N^2)
        blocks = block_by_prefix(entities, prefix_len=4)
        print(f"[{label}] Δημιουργήθηκαν {len(blocks)} blocks (groups) για γρήγορη σύγκριση.")
        
        # 4. Σύγκριση ανά block
        pending_pairs = []
        seen_pairs = set()
        
        for prefix, block_entities in blocks.items():
            if len(block_entities) < 2: continue
            
            # Συγκρίνουμε όλα τα ζευγάρια μέσα στο block
            for a, b in combinations(block_entities, 2):
                pair_id = tuple(sorted([a["id"], b["id"]]))
                if pair_id in seen_pairs:
                    continue
                seen_pairs.add(pair_id)
                
                # Αν έχουν απορριφθεί στο παρελθόν, τα αγνοούμε
                if b["id"] in a["rejected_ids"]:
                    continue
                
                # Αν έχουν διαφορετικά ΑΦΜ (και τα 2 υπάρχουν), είναι διαφορετικά!
                vat_a = a.get("vat")
                vat_b = b.get("vat")
                if vat_a and vat_b and vat_a != vat_b:
                    continue
                    
                # Υπολογισμός Score
                name_a = a["name"]
                name_b = b["name"]
                lev_score = similarity_score(name_a, name_b)
                tok_score = token_overlap_score(name_a, name_b)
                final_score = (lev_score * 0.6) + (tok_score * 0.4)
                
                if threshold_min <= final_score <= threshold_max:
                    pending_pairs.append({
                        "id1": a["id"],
                        "id2": b["id"],
                        "score": round(final_score, 3)
                    })

        print(f"[{label}] Βρέθηκαν {len(pending_pairs)} υποψήφια ζεύγη προς αξιολόγηση.")
        
        # 5. Αποθήκευση σχέσεων στο Neo4j
        if pending_pairs:
            print(f"[{label}] Δημιουργία σχέσεων :PENDING_REVIEW στη βάση...")
            # Χρησιμοποιούμε batches για να μην υπερφορτώσουμε τη μνήμη
            batch_size = 1000
            for i in range(0, len(pending_pairs), batch_size):
                batch = pending_pairs[i:i+batch_size]
                query = f"""
                UNWIND $batch AS pair
                MATCH (a:{label}) WHERE id(a) = pair.id1
                MATCH (b:{label}) WHERE id(b) = pair.id2
                MERGE (a)-[r:PENDING_REVIEW]->(b)
                SET r.score = pair.score, r.reason = 'similar_name'
                """
                session.run(query, {"batch": batch})
                
    elapsed = time.time() - start_time
    print(f"[{label}] Ολοκληρώθηκε σε {elapsed:.1f} δευτερόλεπτα.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Εντοπισμός διπλοεγγραφών για το HITL Dashboard")
    parser.add_argument("--entity", choices=["Buyer", "Winner"], default="Buyer", help="Ποια οντότητα να ελεγχθεί")
    parser.add_argument("--min", type=float, default=0.75, help="Ελάχιστο similarity score (0.0-1.0)")
    args = parser.parse_args()
    
    generate_pending_reviews(args.entity, threshold_min=args.min)
