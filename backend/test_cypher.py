import sys
import os
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

from database import execute_cypher
query = """
WITH "foo" as s, ["foo", "bar"] as l
RETURN "foo" CONTAINS s, "foo" IN l
"""
res = execute_cypher(query, format_output=False)
print(res)
