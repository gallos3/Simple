from database import execute_cypher
import json

res = execute_cypher("MATCH (b:Buyer) RETURN id(b) as id, b.name as name", format_output=False)
lines = []
for r in res:
    if r['name']:
        n = str(r['name']).upper()
        if '3Η ΥΓΕΙΟΝΟΜΙΚΗ' in n:
            lines.append(f"{r['id']}: {r['name']}")

with open('scratch/yg_nodes.txt', 'w', encoding='utf-8') as f:
    for l in lines:
        f.write(l + '\n')
