
import unicodedata
from database import get_session

def normalize_greek(text):
    if not text: return ""
    if isinstance(text, list):
        text = text[0] # Take first name if multiple exist
    # Title/Lower to Upper
    text = str(text).upper()
    # Remove accents
    nfkd_form = unicodedata.normalize('NFKD', text)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def merge_by_normalized_name():
    print(" Starting Advanced Name-based Resolution (Python-assisted)...")
    
    try:
        with get_session() as session:
            # 1. Get all buyers
            print("   Fetching buyers...")
            res = session.run("MATCH (b:Buyer) RETURN id(b) as id, b.name as name")
            
            # 2. Update norm_name in Neo4j
            print("   Updating normalized names in DB...")
            # Χρησιμοποιούμε batches για ταχύτητα
            batch = []
            for r in res:
                norm = normalize_greek(r['name'])
                batch.append({"id": r['id'], "norm": norm})
                if len(batch) >= 5000:
                    session.run("UNWIND $batch AS item MATCH (b:Buyer) WHERE id(b) = item.id SET b.norm_name = item.norm", {"batch": batch})
                    batch = []
            if batch:
                session.run("UNWIND $batch AS item MATCH (b:Buyer) WHERE id(b) = item.id SET b.norm_name = item.norm", {"batch": batch})

            # 3. Perform the APOC Merge
            print("   Executing APOC merge on normalized names...")
            merge_query = """
            CALL apoc.periodic.iterate(
              "MATCH (b:Buyer) WHERE b.norm_name IS NOT NULL WITH b.norm_name AS norm, collect(b) AS nodes WHERE size(nodes) > 1 RETURN nodes",
              "CALL apoc.refactor.mergeNodes(nodes, {properties: 'combine', mergeRels: true}) YIELD node RETURN count(*)",
              {batchSize: 1, parallel: false}
            )
            YIELD batches, total, errorMessages
            RETURN total AS merged_groups
            """
            result = session.run(merge_query)
            record = result.single()
            print(f" Successfully unified {record['merged_groups']} authorities.")
            
    except Exception as e:
        print(f" Error: {e}")

if __name__ == "__main__":
    merge_by_normalized_name()
