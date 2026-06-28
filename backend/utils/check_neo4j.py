import os
import json
from neo4j import GraphDatabase

with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

uri = config.get("NEO4J_URI", "bolt://localhost:7687")
user = config.get("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD")

driver = GraphDatabase.driver(uri, auth=(user, password))

def check_all_unis():
    with driver.session() as session:
        query = "MATCH (a:Buyer) WHERE toLower(a.name) CONTAINS 'πανεπιστημιο' RETURN a.name AS name"
        result = session.run(query)
        names = sorted([record["name"] for record in result])
        
        with open('neo4j_all_unis.txt', 'w', encoding='utf-8') as out:
            out.write(f"Found {len(names)} Authorities with 'πανεπιστημιο':\n")
            for n in names:
                out.write(f"- {n}\n")

if __name__ == "__main__":
    check_all_unis()
    driver.close()
