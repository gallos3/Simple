from database import execute_cypher

res = execute_cypher("MATCH (b:Buyer) RETURN id(b) as id, b.name as name", format_output=False)
lines = []
for r in res:
    if r['name'] and ('ΔΗΜΗΤΡΙΟΣ' in str(r['name']).upper() or 'ΔΗΜΗΤΡΙΟΥ' in str(r['name']).upper()):
        lines.append(f"{r['id']}: {r['name']}")

with open('scratch/agios_nodes.txt', 'w', encoding='utf-8') as f:
    for l in lines:
        f.write(l + '\n')
