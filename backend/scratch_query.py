from database import get_session

query = """
MATCH (a:Buyer)-[:AWARDS]->(c:Award)
WHERE a.vat = '090024750'
  AND toString(c.submission_date) STARTS WITH '2023'
RETURN count(c) as count
"""

with get_session() as session:
    res = session.run(query)
    for row in res:
        print(f"AHEPA 2023 count (Active only): {row['count']}")
