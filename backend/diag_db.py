import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from neo4j import GraphDatabase

URI  = "bolt://localhost:7687"
USER = "neo4j"
PASS = "ohi21365pote"
DB   = "neo4j"

print("Connecting to Neo4j database...")
driver = GraphDatabase.driver(URI, auth=(USER, PASS))

def query(q):
    with driver.session(database=DB) as session:
        return [dict(r) for r in session.run(q)]

try:
    # 1. Show all databases
    print("\n--- Databases ---")
    dbs = query("SHOW DATABASES YIELD name, currentStatus, role")
    for d in dbs:
        print(f"  Database: {d['name']}, Status: {d['currentStatus']}, Role: {d.get('role')}")
        
    # 2. Node label counts in the target database
    print("\n--- Node Counts ---")
    node_counts = query("MATCH (n) RETURN labels(n) AS labels, count(n) AS count ORDER BY count DESC")
    for r in node_counts:
        print(f"  Labels: {r['labels']}, Count: {r['count']}")
        
    # 3. Relationship type counts
    print("\n--- Relationship Counts ---")
    rel_counts = query("MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS count ORDER BY count DESC")
    for r in rel_counts:
        print(f"  Relationship: {r['rel']}, Count: {r['count']}")
        
    # 4. Award properties count
    print("\n--- Award Properties (Sample or Keys) ---")
    award_props = query("""
        MATCH (a:Award)
        WITH keys(a) AS keys
        UNWIND keys AS key
        RETURN key, count(*) AS count
        ORDER BY count DESC
    """)
    for r in award_props:
        print(f"  Property '{r['key']}': found in {r['count']} Award nodes")
        
    # 5. Check if Winner nodes are linked to anything
    print("\n--- Winner connections ---")
    winner_rels = query("""
        MATCH (w:Winner)-[r]-()
        RETURN type(r) AS rel, count(r) AS count
    """)
    if winner_rels:
        for r in winner_rels:
            print(f"  Winner -[{r['rel']}]- : Count = {r['count']}")
    else:
        print("  No relationships found for Winner nodes")
        
    # 6. Sample of Winner nodes
    print("\n--- Sample Winner Nodes ---")
    winners = query("MATCH (w:Winner) RETURN w.name AS name LIMIT 5")
    for w in winners:
        print(f"  Winner: {w['name']}")

except Exception as e:
    print(f"Error executing diagnosis: {e}")
finally:
    driver.close()
