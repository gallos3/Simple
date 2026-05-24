"""
Simple - Schema Migration Script
Converts string dates to temporal types and normalizes the graph structure.
"""
from database import get_driver, execute_cypher

def migrate():
    driver = get_driver()
    
    print("🚀 Starting Migration...")

    # 1. Add Constraints
    print("  Adding Constraints...")
    execute_cypher("CREATE CONSTRAINT contract_ref IF NOT EXISTS FOR (c:Contract) REQUIRE c.reference_number IS UNIQUE")
    execute_cypher("CREATE CONSTRAINT authority_name IF NOT EXISTS FOR (a:Authority) REQUIRE a.name IS UNIQUE")
    execute_cypher("CREATE CONSTRAINT company_name IF NOT EXISTS FOR (c:Company) REQUIRE c.name IS UNIQUE")
    execute_cypher("CREATE CONSTRAINT cpv_code IF NOT EXISTS FOR (c:CPV) REQUIRE c.code IS UNIQUE")

    # 2. Convert signed_date to Date
    print("  Converting signed_date to temporal Date types...")
    # Using toString(c.signed_date) = c.signed_date to identify strings
    migrate_dates_query = """
    MATCH (c:Contract)
    WHERE c.signed_date IS NOT NULL AND toString(c.signed_date) = c.signed_date
    WITH c, 
         CASE 
            WHEN c.signed_date =~ '\\d{4}-\\d{2}-\\d{2}.*' THEN date(substring(c.signed_date, 0, 10))
            WHEN c.signed_date =~ '\\d{4}/\\d{2}/\\d{2}.*' THEN date(replace(substring(c.signed_date, 0, 10), '/', '-'))
            WHEN c.signed_date =~ '\\d{4}' THEN date({year: toInteger(c.signed_date), month: 1, day: 1})
            ELSE null
         END AS new_date
    WHERE new_date IS NOT NULL
    SET c.signed_date = new_date
    RETURN count(c) as updated
    """
    res = execute_cypher(migrate_dates_query, format_output=False)
    if isinstance(res, str):
        print(f"    ❌ Error during date migration: {res}")
    else:
        print(f"    Updated {res[0].get('updated', 0) if res else 0} contract dates.")

    # 3. Normalize CPV
    print("  Normalizing CPV codes into dedicated nodes...")
    migrate_cpv_query = """
    MATCH (c:Contract)
    WHERE c.cpv_code IS NOT NULL OR c.cpv IS NOT NULL
    WITH c, coalesce(c.cpv_code, c.cpv) AS code
    MERGE (cpv:CPV {code: code})
    MERGE (c)-[:HAS_CPV]->(cpv)
    RETURN count(cpv) as cpvs_created
    """
    res = execute_cypher(migrate_cpv_query, format_output=False)
    if isinstance(res, str):
        print(f"    ❌ Error during CPV migration: {res}")
    else:
        print(f"    Linked contracts to {res[0].get('cpvs_created', 0) if res else 0} CPV nodes.")

    # 4. Standardize Relationships (Optional but recommended)
    print("  Standardizing relationships (BUY -> AWARDS, SELLS -> AWARDED_TO)...")
    
    # BUY -> AWARDS
    execute_cypher("""
    MATCH (a:Authority)-[r:BUY]->(c:Contract)
    MERGE (a)-[:AWARDS]->(c)
    DELETE r
    """)
    
    # SELLS -> AWARDED_TO
    execute_cypher("""
    MATCH (co:Company)-[r:SELLS]-(c:Contract)
    MERGE (c)-[:AWARDED_TO]->(co)
    DELETE r
    """)

    print("✅ Migration Completed!")

if __name__ == "__main__":
    migrate()
