from database import execute_cypher

query = """
MATCH (b:Buyer) 
WHERE ANY(n IN b.aliases WHERE toLower(toString(n)) CONTAINS 'αγιος' AND toLower(toString(n)) CONTAINS 'δημητριος')
   OR ANY(n IN CASE WHEN apoc.meta.type(b.name) = 'StringArray' THEN b.name ELSE [b.name] END WHERE toLower(toString(n)) CONTAINS 'αγιος' AND toLower(toString(n)) CONTAINS 'δημητριος')
RETURN id(b) as id, b.name as name
"""
res = execute_cypher(query, format_output=False)
ids_to_merge = [r['id'] for r in res]
print(f"Found {len(ids_to_merge)} nodes to merge: {ids_to_merge}")

if len(ids_to_merge) > 1:
    merge_query = """
    MATCH (b:Buyer) WHERE id(b) IN $ids
    WITH collect(b) as nodes
    CALL apoc.refactor.mergeNodes(nodes, {properties: 'combine', mergeRels: true}) YIELD node
    RETURN node.name
    """
    res2 = execute_cypher(merge_query, params={'ids': ids_to_merge}, format_output=False)
    print("Merged into:", res2)
