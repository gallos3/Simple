import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from neo4j import GraphDatabase

URI  = "bolt://localhost:7687"
USER = "neo4j"
PASS = "ohi21365pote"

print("=== DEEP CHECK: ENDORSE DATABASE ===")

try:
    driver = GraphDatabase.driver(URI, auth=(USER, PASS))
    
    with driver.session() as s:
        # 1. Are there orphan authorities in ENDORSE?
        q_iso = """
        MATCH (a:Authority)
        WHERE NOT (a)--()
        RETURN count(a) as count
        """
        iso = s.run(q_iso).single()["count"]
        print(f"1. Completely isolated Authority nodes in ENDORSE: {iso}")

        # 2. How many ContractAwards have NO connection to any Authority (direct or indirect)?
        q_missing_auth = """
        MATCH (ca:ContractAward)
        OPTIONAL MATCH (ca)-[:issuedBy]->(auth_d:Authority)
        OPTIONAL MATCH (ca)-[:belongsToLot]->(:Lot)<-[:hasLot]-(:Notice)-[:publishedBy]->(auth_i:Authority)
        WITH ca, auth_d, auth_i
        WHERE auth_d IS NULL AND auth_i IS NULL
        RETURN count(ca) as count
        """
        missing_auth = s.run(q_missing_auth).single()["count"]
        print(f"2. ContractAwards with NO Authority link (direct or indirect): {missing_auth}")
        
        # 3. If they don't have an Authority, what DO they have? Let's check a sample of 5.
        if missing_auth > 0:
            q_sample = """
            MATCH (ca:ContractAward)
            OPTIONAL MATCH (ca)-[:issuedBy]->(auth_d:Authority)
            OPTIONAL MATCH (ca)-[:belongsToLot]->(:Lot)<-[:hasLot]-(:Notice)-[:publishedBy]->(auth_i:Authority)
            WITH ca, auth_d, auth_i
            WHERE auth_d IS NULL AND auth_i IS NULL
            MATCH (ca)-[r]-(n)
            RETURN ca.identifier as ca_id, type(r) as rel, labels(n) as node_labels
            LIMIT 10
            """
            print(f"3. Sample of what these {missing_auth} 'orphan' ContractAwards connect to:")
            for r in s.run(q_sample):
                print(f"   Award {r['ca_id']} -[{r['rel']}]- {r['node_labels']}")

        # 4. Check if there's any OTHER path we missed?
        q_other_paths = """
        MATCH (ca:ContractAward)
        OPTIONAL MATCH (ca)-[:issuedBy]->(auth_d:Authority)
        OPTIONAL MATCH (ca)-[:belongsToLot]->(:Lot)<-[:hasLot]-(:Notice)-[:publishedBy]->(auth_i:Authority)
        WITH ca, auth_d, auth_i
        WHERE auth_d IS NULL AND auth_i IS NULL
        // Find ANY path up to 3 hops from ContractAward to Authority
        MATCH p = (ca)-[*1..3]-(a:Authority)
        RETURN count(p) as count
        """
        other_paths = s.run(q_other_paths).single()["count"]
        print(f"4. Are there any OTHER hidden paths (up to 3 hops) from these awards to Authorities?: {other_paths}")

    driver.close()
except Exception as e:
    print(f"Error connecting to database (make sure ENDORSE is running): {e}")
