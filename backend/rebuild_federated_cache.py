
import json
from database import get_session
from entity_extractor import ENTITY_CACHE_PATH

def rebuild_cache():
    print(" Rebuilding Entity Cache from Federated Graph...")
    
    with get_session() as session:
        # 1. Fetch Buyers
        print("   Fetching Buyers...")
        res = session.run("MATCH (b:Buyer) RETURN b.name AS name")
        buyers = [r["name"] for r in res if r["name"]]
        print(f"   Found {len(buyers)} unique buyers.")
        
        # 2. Fetch Winners (Optional, but useful for resolution)
        print("   Fetching Winners...")
        res = session.run("MATCH (w:Winner) RETURN w.name AS name")
        winners = [r["name"] for r in res if r["name"]]
        print(f"   Found {len(winners)} unique winners.")
        
    # Ensure names are strings (handle cases where mergeNodes created lists)
    def clean_name(n):
        if isinstance(n, list): return str(n[0])
        return str(n)
        
    cache = {
        "Buyer.name": sorted(list(set(clean_name(b) for b in buyers))),
        "Winner.name": sorted(list(set(clean_name(w) for w in winners)))
    }
    
    with open(ENTITY_CACHE_PATH, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    
    print(f" Cache rebuilt successfully at {ENTITY_CACHE_PATH}")

if __name__ == "__main__":
    rebuild_cache()
