import sys, io
sys.path.append('c:\\Simple_Federated\\backend')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from database import execute_cypher

print("=== Federated Database Verification ===\n")

# 1. Total node counts
q_nodes = """
MATCH (n)
RETURN labels(n)[0] as Label, count(n) as Count
ORDER BY Count DESC
"""
print("-- Node Counts --")
print(execute_cypher(q_nodes, format_output=False))

# 2. Check for "UNKNOWN" buyer (should not exist with 2.8 million relations anymore)
q_unknown = """
MATCH (b:Buyer {name: 'UNKNOWN'})-[r]-()
RETURN type(r) as RelType, count(r) as RelCount
"""
print("\n-- 'UNKNOWN' Buyer Relationships --")
print(execute_cypher(q_unknown, format_output=False))

# 3. Check for isolated buyers
q_isolated = """
MATCH (b:Buyer)
WHERE NOT (b)-[:AWARDS]->()
RETURN count(b) as Isolated_Buyers
"""
print("\n-- Isolated Buyers (0 awards) --")
print(execute_cypher(q_isolated, format_output=False))

# 4. Check Awards by Source
q_awards_src = """
MATCH (a:Award)
RETURN a.source as Source, count(a) as AwardCount
"""
print("\n-- Awards by Source --")
print(execute_cypher(q_awards_src, format_output=False))

# 5. Check connected buyers by source
q_conn_buyers = """
MATCH (b:Buyer)-[:AWARDS]->(a:Award)
RETURN a.source as Source, count(DISTINCT b) as Distinct_Buyers, count(a) as Connected_Awards
"""
print("\n-- Connected Buyers by Source --")
print(execute_cypher(q_conn_buyers, format_output=False))

# 6. Sample top buyers from TED
q_top_ted = """
MATCH (b:Buyer)-[:AWARDS]->(a:Award {source: 'TED'})
RETURN b.name as BuyerName, count(a) as AwardCount
ORDER BY AwardCount DESC LIMIT 5
"""
print("\n-- Top 5 TED Buyers --")
print(execute_cypher(q_top_ted, format_output=False))
