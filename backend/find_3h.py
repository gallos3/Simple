from database import execute_cypher

res = execute_cypher("MATCH (b:Buyer) RETURN id(b) as id, b.name as name", format_output=False)
with open('scratch/3h_dump.txt', 'w', encoding='utf-8') as f:
    for r in res:
        n = str(r['name'])
        if '3η Υγειονομική' in n:
            f.write(f"{r['id']}: {n}\n")
