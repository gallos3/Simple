import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from neo4j import GraphDatabase

URI  = "bolt://localhost:7687"
USER = "neo4j"
PASS = "ohi21365pote"

driver = GraphDatabase.driver(URI, auth=(USER, PASS))

with driver.session() as s:
    # What database are we connected to?
    db_info = s.run("CALL db.info()").single()
    print(f"Current DB name: {db_info['name']}")
    print(f"Current DB id:   {db_info['id']}")
    
    # All labels
    labels = s.run("CALL db.labels()").data()
    print("\nAll node labels in this DB:")
    for l in sorted(labels, key=lambda x: x['label']):
        cnt = s.run(f"MATCH (n:`{l['label']}`) RETURN count(n) as c").single()['c']
        print(f"  {l['label']}: {cnt:,}")

driver.close()
