import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from neo4j import GraphDatabase

URI  = "bolt://localhost:7687"
USER = "neo4j"
PASS = "ohi21365pote"

try:
    driver = GraphDatabase.driver(URI, auth=(USER, PASS))
    with driver.session() as s:
        # Check isolated Authorities
        q_iso = "MATCH (a:Authority) WHERE NOT (a)--() RETURN count(a) as count"
        iso = s.run(q_iso).single()["count"]
        print(f"Isolated Authority nodes in ENDORSE: {iso}")
        
        # Fast check for missing Authority links in ContractAwards using EXISTS to avoid full MATCHes
        q_missing = """
        MATCH (ca:ContractAward)
        WHERE NOT exists((ca)-[:issuedBy]->(:Authority))
          AND NOT exists((ca)-[:belongsToLot]->(:Lot)<-[:hasLot]-(:Notice)-[:publishedBy]->(:Authority))
        RETURN count(ca) as count
        """
        missing = s.run(q_missing).single()["count"]
        print(f"ContractAwards missing any known Authority link: {missing}")

    driver.close()
except Exception as e:
    print(f"Error: {e}")
