import json

with open('predefined_queries.json', encoding='utf-8') as f:
    queries = json.load(f)

for q in queries:
    cypher = q.get('cypher', q.get('query', ''))
    if '$name' in cypher:
        print(f"ID: {q['id']}")
        print(cypher)
        print("-" * 40)
