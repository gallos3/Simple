import json

file_path = 'backend/predefined_queries.json'

with open(file_path, 'r', encoding='utf-8') as f:
    queries = json.load(f)

for q in queries:
    if 'query' in q and isinstance(q['query'], str):
        # Specific fixes for ProcedureType
        if q['id'] == 11:
            q['query'] = "MATCH (c:Award) WHERE c.procedure IS NOT NULL RETURN count(DISTINCT c.procedure) AS διαδικασίες_ανάθεσης"
            continue
        if q['id'] == 32:
            q['query'] = "MATCH b=(a:Buyer)-[r1:AWARDS]-(c:Award) WHERE toLower(coalesce(c.procedure, c.title, \"\")) CONTAINS 'direct award' AND toLower(apoc.text.join(apoc.convert.toList(a.name), ' ')) CONTAINS 'αχεπα' RETURN a, r1, c"
            continue
            
        # General relationship fixes inside the query string
        updated = q['query']
        updated = updated.replace('[:BUY|AWARDS|AWARDS]', '[:AWARDS]')
        updated = updated.replace('[:SELLS|WON]', '[:WON_BY]')
        updated = updated.replace('-[r1:BUY]-', '-[r1:AWARDS]-')
        updated = updated.replace('[:BUY]', '[:AWARDS]')
        
        q['query'] = updated

with open(file_path, 'w', encoding='utf-8') as f:
    json.dump(queries, f, ensure_ascii=False, indent=2)

print('Done applying JSON updates.')
