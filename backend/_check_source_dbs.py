import sys, io, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from neo4j import GraphDatabase

URI  = "bolt://localhost:7687"
USER = "neo4j"
PASS = "ohi21365pote"

def check_endorse():
    print("\n=== Checking ENDORSE (TED) Database ===")
    driver = GraphDatabase.driver(URI, auth=(USER, PASS))
    
    with driver.session() as s:
        # Check total isolated authorities
        iso_q = """
        MATCH (a:Authority)
        WHERE NOT (a)--()
        RETURN count(a) as count
        """
        iso = s.run(iso_q).single()["count"]
        print(f"Isolated Authority nodes (0 connections): {iso}")
        
        # Check how Authority nodes are connected
        rels_q = """
        MATCH (a:Authority)-[r]-()
        RETURN type(r) as rel, count(r) as count
        ORDER BY count DESC
        """
        print("\nAuthority relationships:")
        for r in s.run(rels_q):
            print(f"  {r['rel']}: {r['count']}")
            
        # Check ContractAwards missing issuedBy
        ca_q = """
        MATCH (ca:ContractAward)
        WHERE NOT (ca)-[:issuedBy]->(:Authority)
        RETURN count(ca) as count
        """
        ca_no_issuedBy = s.run(ca_q).single()["count"]
        print(f"\nContractAwards without an 'issuedBy' relationship: {ca_no_issuedBy}")
        
        # If they don't have issuedBy, how do they connect to authorities?
        ca_alt_q = """
        MATCH (ca:ContractAward)
        WHERE NOT (ca)-[:issuedBy]->(:Authority)
        MATCH (ca)-[:belongsToLot]->(:Lot)<-[:hasLot]-(:Notice)-[:publishedBy]->(a:Authority)
        RETURN count(ca) as count
        """
        ca_alt = s.run(ca_alt_q).single()["count"]
        print(f"  ...of which can be reached via Lot->Notice->Authority: {ca_alt}")
        
    driver.close()

def check_kimdis():
    print("\n=== Checking KHMDHS1 Database ===")
    driver = GraphDatabase.driver(URI, auth=(USER, PASS))
    
    with driver.session() as s:
        # Check total isolated authorities
        iso_q = """
        MATCH (a:Auth)
        WHERE NOT (a)--()
        RETURN count(a) as count
        """
        iso = s.run(iso_q).single()["count"]
        print(f"Isolated Auth nodes (0 connections): {iso}")
        
        # Check Auth relationships
        rels_q = """
        MATCH (a:Auth)-[r]-()
        RETURN type(r) as rel, count(r) as count
        ORDER BY count DESC
        """
        print("\nAuth relationships:")
        for r in s.run(rels_q):
            print(f"  {r['rel']}: {r['count']}")
            
    driver.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("db", choices=["endorse", "kimdis"])
    args = parser.parse_args()
    
    try:
        if args.db == "endorse":
            check_endorse()
        else:
            check_kimdis()
    except Exception as e:
        print(f"Error connecting to database: {e}")
