"""
Simple - Schema Verification Script
Verifies that the migration was successful and data is correctly normalized.
"""
from database import execute_cypher

def verify():
    print("🔍 Starting Schema Verification...")
    
    # 1. Check Date Types
    query_dates = """
    MATCH (c:Contract)
    WHERE c.signed_date IS NOT NULL
    RETURN count(c) as total, 
           count(CASE WHEN NOT (toString(c.signed_date) = c.signed_date) THEN 1 END) as date_type
    """
    res = execute_cypher(query_dates, format_output=False)
    if res:
        total = res[0].get('total', 0)
        date_type = res[0].get('date_type', 0)
        print(f"  [Dates] {date_type}/{total} contracts have proper temporal Date types.")
    
    # 2. Check Normalized Nodes
    query_nodes = """
    MATCH (co:Company) WITH count(co) as companies
    MATCH (cpv:CPV) WITH companies, count(cpv) as cpvs
    RETURN companies, cpvs
    """
    res = execute_cypher(query_nodes, format_output=False)
    if res:
        print(f"  [Nodes] Found {res[0].get('companies', 0)} Company nodes and {res[0].get('cpvs', 0)} CPV nodes.")

    # 3. Check Relationships
    query_rels = """
    MATCH ()-[r:AWARDS]->() WITH count(r) as awards
    MATCH ()-[r:AWARDED_TO]->() WITH awards, count(r) as awarded_to
    MATCH ()-[r:HAS_CPV]->() WITH awards, awarded_to, count(r) as has_cpv
    RETURN awards, awarded_to, has_cpv
    """
    res = execute_cypher(query_rels, format_output=False)
    if res:
        print(f"  [Relationships] Found {res[0].get('awards', 0)} AWARDS, {res[0].get('awarded_to', 0)} AWARDED_TO, and {res[0].get('has_cpv', 0)} HAS_CPV.")

    print("🏁 Verification Finished.")

if __name__ == "__main__":
    verify()
