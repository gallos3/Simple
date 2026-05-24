import json
import re

with open('c:/Simple_Federated/backend/predefined_queries.json', 'r', encoding='utf-8') as f:
    queries = json.load(f)

for q in queries:
    query = q['query']
    
    # Fix relationships
    query = query.replace(':AWARDS_TO', ':WON_BY')
    query = query.replace('c.Value', 'c.value') # federate_data uses 'value' (lowercase)
    query = query.replace('c.Award_REF', 'c.identifier') # federate_data uses 'identifier'
    
    # We want to replace c.procedure with coalesce(c.procedure, c.title) safely, but avoid double replacement
    # Some queries might already have c.procedure, some might not.
    
    # Fix ProcedureType
    # MATCH (a:Buyer)-[:AWARDS]-(c:Award)-[:HAS_TYPE]-(p:ProcedureType) WHERE toLower(p.description) CONTAINS 'direct award'
    
    query = re.sub(r'-\[:HAS_TYPE\]-\([a-z]+:ProcedureType\)', '', query)
    query = re.sub(r'-\[:HAS_TYPE\]->\([a-z]+:ProcedureType\)', '', query)
    query = re.sub(r', \(c\)-\[:HAS_TYPE\]-\([a-z]+:ProcedureType\)', '', query)
    query = re.sub(r'\(c\)-\[:HAS_TYPE\]-\([a-z]+:ProcedureType\)', '(c)', query)
    query = re.sub(r'-\[:HAS_PROCEDURE\]->\([a-z]+:ProcedureType\)', '', query)
    query = re.sub(r'-\[:OF_TYPE\]->\([a-z]+:ProcedureType\)', '', query)
    
    # In queries 101-108, pt is used but not matched anymore because we removed it.
    # The queries have OPTIONAL MATCH (c)-[:HAS_TYPE...]->(pt:ProcedureType)
    query = re.sub(r'OPTIONAL MATCH \(c\)-\[:[^\]]+\]->\([a-z]+:ProcedureType\)', '', query)
    
    # Replace references to ProcedureType description
    query = re.sub(r'toLower\([a-z]+\.description\)', 'toLower(coalesce(c.procedure, c.title, ""))', query)
    query = re.sub(r'[a-z]+\.description', 'coalesce(c.procedure, c.title)', query)
    
    # In queries 101-108: toLower(coalesce(pt.description, c.procedure, ""))
    query = re.sub(r'coalesce\([a-z]+\.description, c\.procedure, ""\)', 'coalesce(c.procedure, c.title, "")', query)

    # Remove pt from WITH clauses
    query = re.sub(r',\s*pt', '', query)

    # Clean up any leftover syntax errors from replacing pt
    query = query.replace('WITH c, a WHERE', 'WITH c, a WHERE') # redundant but safe

    # Fix AwardType if any
    query = re.sub(r'-\[:HAS_TYPE\]-\(ct:AwardType\)', '', query)
    query = query.replace('ct,', 'coalesce(c.procedure, c.title),')
    
    # For graphs
    query = query.replace(', p', '')

    q['query'] = query

with open('c:/Simple_Federated/backend/predefined_queries.json', 'w', encoding='utf-8') as f:
    json.dump(queries, f, ensure_ascii=False, indent=2)
print('Done!')
