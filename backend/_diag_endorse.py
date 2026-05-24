import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from neo4j import GraphDatabase

URI  = "bolt://localhost:7687"
USER = "neo4j"
PASS = "ohi21365pote"

driver = GraphDatabase.driver(URI, auth=(USER, PASS))

def run(db, q, **params):
    with driver.session(database=db) as s:
        return [dict(r) for r in s.run(q, **params)]

# Step 1: List all databases
dbs = run("system", "SHOW DATABASES YIELD name, currentStatus RETURN name, currentStatus")
print("=== Databases ===")
for d in dbs:
    print(f"  {d['name']}  [{d['currentStatus']}]")

# Find ENDORSE database name (case insensitive)
endorse_db = None
for d in dbs:
    if "endorse" in d["name"].lower() and d["currentStatus"] == "online":
        endorse_db = d["name"]
        break

if not endorse_db:
    print("\n[!] ENDORSE database not found or not online!")
    driver.close()
    sys.exit(1)

print(f"\n=== Schema of '{endorse_db}' ===")

# Step 2: What relationships does ContractAward have?
print("\n-- ContractAward relationships --")
rels = run(endorse_db, """
    MATCH (ca:ContractAward)-[r]-()
    RETURN type(r) AS rel, count(r) AS cnt
    ORDER BY cnt DESC LIMIT 15
""")
for r in rels:
    print(f"  {r['rel']}: {r['cnt']}")

# Step 3: What relationships does Authority have?
print("\n-- Authority relationships --")
auth_rels = run(endorse_db, """
    MATCH (a:Authority)-[r]-()
    RETURN type(r) AS rel, count(r) AS cnt
    ORDER BY cnt DESC LIMIT 10
""")
for r in auth_rels:
    print(f"  {r['rel']}: {r['cnt']}")

# Step 4: Sample - show path from Authority to ContractAward
print("\n-- Sample Authority->...->ContractAward path --")
sample = run(endorse_db, """
    MATCH (a:Authority)-[r1]-(n1)-[r2]-(ca:ContractAward)
    RETURN type(r1) AS r1, labels(n1) AS n1_labels, type(r2) AS r2,
           a.legalName AS auth_name LIMIT 3
""")
if sample:
    for s in sample:
        print(f"  Authority-[{s['r1']}]-({s['n1_labels']})-[{s['r2']}]->ContractAward  auth={s['auth_name']}")
else:
    # Try direct
    print("  No 2-hop path found, trying direct...")
    direct = run(endorse_db, """
        MATCH (a:Authority)-[r]-(ca:ContractAward)
        RETURN type(r) AS rel, a.legalName AS auth_name, 
               ca.identifier AS ca_id LIMIT 3
    """)
    for s in direct:
        print(f"  Authority-[{s['rel']}]->ContractAward  auth={s['auth_name']}")

driver.close()
