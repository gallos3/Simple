from database import execute_cypher
query = """
WITH "foo" as s, ["foo", "bar"] as l
RETURN "foo" CONTAINS s, "foo" IN l
"""
res = execute_cypher(query, format_output=False)
print(res)
