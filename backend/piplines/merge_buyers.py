
from database import get_session

def merge_buyers_apoc():
    print(" Starting Professional Entity Resolution (APOC Merge)...")
    
    # Αυτό το query βρίσκει τα διπλά ΑΦΜ και τα συγχωνεύει χρησιμοποιώντας το APOC
    query = """
    CALL apoc.periodic.iterate(
      "MATCH (b:Buyer) WHERE b.vat IS NOT NULL WITH b.vat AS vat, collect(b) AS nodes WHERE size(nodes) > 1 RETURN nodes",
      "CALL apoc.refactor.mergeNodes(nodes, {properties: 'combine', mergeRels: true}) YIELD node RETURN count(*)",
      {batchSize: 1, parallel: false}
    )
    YIELD batches, total, errorMessages
    RETURN total AS merged_groups, errorMessages
    """
    
    try:
        with get_session() as session:
            result = session.run(query)
            record = result.single()
            print(f" Successfully unified {record['merged_groups']} procurement authorities.")
    except Exception as e:
        print(f" Error during APOC merge: {e}")

if __name__ == "__main__":
    merge_buyers_apoc()
