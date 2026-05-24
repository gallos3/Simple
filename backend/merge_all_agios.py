from database import get_session

with get_session() as session:
    # 1. Merge 18932 into 123671
    print("Merging 18932 into 123671...")
    res = session.run("""
        MATCH (a:Buyer), (b:Buyer)
        WHERE id(a) = 123671 AND id(b) = 18932
        CALL apoc.refactor.mergeNodes([a, b], {properties: 'combine', mergeRels: true}) YIELD node
        RETURN id(node) as new_id, node.name as name
    """)
    for r in res:
        print(f"Merged 18932! New node: {r['new_id']} with names: {r['name']}")
    
    # 2. Merge 65349 into 123671
    print("Merging 65349 into 123671...")
    res = session.run("""
        MATCH (a:Buyer), (b:Buyer)
        WHERE id(a) = 123671 AND id(b) = 65349
        CALL apoc.refactor.mergeNodes([a, b], {properties: 'combine', mergeRels: true}) YIELD node
        RETURN id(node) as new_id, node.name as name
    """)
    for r in res:
        print(f"Merged 65349! New node: {r['new_id']} with names: {r['name']}")
