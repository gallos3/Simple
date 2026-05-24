from database import execute_cypher
res = execute_cypher("MATCH (b:Buyer) WHERE b.name CONTAINS 'ΔΗΜΗΤΡΙΟΣ' RETURN b.name, b.vat LIMIT 10", format_output=False)
for r in res: print(r)
