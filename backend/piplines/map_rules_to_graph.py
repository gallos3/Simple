"""
Simple - Rule Mapping Script
Connects Legal Rules to CPVs based on their categories.
"""
from database import execute_cypher

def map_rules():
    print("🔗 Mapping Legal Rules to CPVs...")
    
    # Rule for Works (CPVs starting with 45)
    query_works = """
    MATCH (r:LegalRule {id: 'N4412_ART118'})
    MATCH (t:Threshold {id: 'DA_LIMIT_WORKS'})
    MATCH (cpv:CPV) WHERE cpv.code STARTS WITH '45'
    MERGE (cpv)-[:SUBJECT_TO {type: 'Works'}]->(r)
    MERGE (cpv)-[:USE_THRESHOLD]->(t)
    RETURN count(cpv) as mapped_works
    """
    
    # Rule for Services/Supplies (The rest)
    query_services = """
    MATCH (r:LegalRule {id: 'N4412_ART118'})
    MATCH (t:Threshold {id: 'DA_LIMIT_SERVICES'})
    MATCH (cpv:CPV) WHERE NOT cpv.code STARTS WITH '45'
    MERGE (cpv)-[:SUBJECT_TO {type: 'Services/Supplies'}]->(r)
    MERGE (cpv)-[:USE_THRESHOLD]->(t)
    RETURN count(cpv) as mapped_services
    """
    
    res1 = execute_cypher(query_works, format_output=False)
    res2 = execute_cypher(query_services, format_output=False)
    
    if not isinstance(res1, str) and not isinstance(res2, str):
        print(f"  ✅ Mapped {res1[0].get('mapped_works', 0)} CPVs to Works limit.")
        print(f"  ✅ Mapped {res2[0].get('mapped_services', 0)} CPVs to Services/Supplies limit.")
    else:
        print("  ❌ Error mapping rules.")

if __name__ == "__main__":
    map_rules()
