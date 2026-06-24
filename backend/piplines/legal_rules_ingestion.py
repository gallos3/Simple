"""
Simple - Legal Rules Ingestion
Populates the graph with thresholds and rules from Greek Procurement Law (N.4412/2016).
"""
from database import execute_cypher

def ingest_rules():
    print("⚖️ Ingesting Legal Rules into Graph...")
    
    cypher = """
    // 1. Direct Award Rule
    MERGE (r1:LegalRule {id: 'N4412_ART118', name: 'Direct Award (Απευθείας Ανάθεση)', article: '118'})
    
    // 2. Thresholds
    MERGE (t1:Threshold {id: 'DA_LIMIT_SERVICES', value: 30000, type: 'Services/Supplies', description: 'Standard limit for services and supplies'})
    MERGE (t2:Threshold {id: 'DA_LIMIT_WORKS', value: 60000, type: 'Works', description: 'Standard limit for public works'})
    
    // 3. Relationships
    MERGE (r1)-[:HAS_THRESHOLD]->(t1)
    MERGE (r1)-[:HAS_THRESHOLD]->(t2)
    
    RETURN r1, t1, t2
    """
    
    res = execute_cypher(cypher, format_output=False)
    if isinstance(res, str):
        print(f"  ❌ Error: {res}")
    else:
        print("  ✅ Legal rules and thresholds successfully ingested.")

if __name__ == "__main__":
    ingest_rules()
