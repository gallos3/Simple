"""
Simple - Database Module
Neo4j connection, query execution, and result formatting.
"""

import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE, BASE_DIR

# =============================================================================
# NEO4J CONNECTION
# =============================================================================
_driver = None

def get_driver():
    """Singleton pattern for Neo4j driver."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            NEO4J_URI, 
            auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        # Ensure constraints are set
        try:
            init_schema()
        except Exception as e:
            print(f" Warning: Could not initialize schema constraints: {e}")
    return _driver

def get_session():
    """Return a session connected to the correct database."""
    return get_driver().session(database=NEO4J_DATABASE)

def init_schema():
    """Ensure database constraints and indexes exist."""
    constraints = [
        ("award_id", "Award", "identifier"),
        ("buyer_name", "Buyer", "name"),
        ("winner_name", "Winner", "name"),
        ("cpv_code", "CPV", "code"),
        ("legal_rule_id", "LegalRule", "id")
    ]
    
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        # Create Constraints (Idempotent)
        for name, label, prop in constraints:
            try:
                session.run(f"CREATE CONSTRAINT {name} IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE")
            except Exception as e:
                print(f" Note: Constraint {name} setup note: {e}")
        
        # 2. Create Indexes
        session.run("CREATE INDEX award_date IF NOT EXISTS FOR (c:Award) ON (c.signed_date)")
        
    print(" Database schema initialized.")

def close_driver():
    """Close the Neo4j driver connection."""
    global _driver
    if _driver:
        _driver.close()
        _driver = None

# =============================================================================
# SCHEMA
# =============================================================================
def get_schema() -> str:
    """  schema  ."""
    driver = get_driver()
    with get_session() as session:
        result = session.run("CALL db.schema.visualization()")
        record = result.single()
        
        if not record:
            return "  schema."
        
        nodes = record["nodes"]
        rels = record["relationships"]
        
        node_labels = sorted({next(iter(n.labels)) for n in nodes})
        
        relationship_types = []
        for rel in rels:
            start_label = next(iter(rel.start_node.labels))
            end_label = next(iter(rel.end_node.labels))
            rel_type = rel.type
            relationship_types.append(f"(:{start_label})-[:{rel_type}]->(:{end_label})")
        
        schema_text = ":\n"
        schema_text += "\n".join(f"- :{label}" for label in node_labels)
        schema_text += "\n\n:\n"
        schema_text += "\n".join(f"- {rel}" for rel in relationship_types)
        
        return schema_text

# =============================================================================
# PREDEFINED QUERIES
# =============================================================================
_predefined_queries = None

def load_predefined_queries() -> Dict:
    """Load predefined queries from JSON file."""
    global _predefined_queries
    if _predefined_queries is None:
        queries_path = BASE_DIR / "predefined_queries.json"
        with open(queries_path, encoding="utf-8") as f:
            data = json.load(f)
        
        # Handle both formats:
        # Format 1: {"queries": [...]}
        # Format 2: [...] (direct list)
        if isinstance(data, dict) and "queries" in data:
            queries_list = data["queries"]
        elif isinstance(data, list):
            queries_list = data
        else:
            queries_list = []
        
        # Normalize field names (query -> cypher, question -> description)
        _predefined_queries = {}
        for q in queries_list:
            query_id = str(q.get("id", ""))
            # Description: use 'description' field, or first item of 'question'/'questions' list
            desc = q.get("description", "")
            if not desc:
                qfield = q.get("question") or q.get("questions", "")
                if isinstance(qfield, list):
                    desc = qfield[0] if qfield else ""
                else:
                    desc = str(qfield) if qfield else ""
            
            normalized = {
                "id": query_id,
                "cypher": q.get("cypher") or q.get("query", ""),
                "query": q.get("query") or q.get("cypher", ""),  # keep both keys
                "description": desc,
                "graph": q.get("graph", False),
                "action": q.get("action", ""),  # preserve action field!
                "question": q.get("question") or q.get("questions", []),
            }
            _predefined_queries[query_id] = normalized
        
        print(f" Loaded {len(_predefined_queries)} predefined queries")
    
    return _predefined_queries

def get_predefined_query(query_id: Union[int, str]) -> Optional[Dict]:
    """Get a predefined query by ID."""
    queries = load_predefined_queries()
    return queries.get(str(query_id))

def get_all_predefined_queries() -> List[Dict]:
    """Get all predefined queries as a list."""
    queries = load_predefined_queries()
    return list(queries.values())

# =============================================================================
# QUERY EXECUTION
# =============================================================================
def execute_cypher(
    query: str, 
    params: Optional[Dict] = None,
    format_output: bool = True
) -> Union[str, List[Dict]]:
    """
    Execute a Cypher query and return results.
    
    Args:
        query: Cypher query string
        params: Query parameters
        format_output: If True, return formatted string; if False, return raw records
    
    Returns:
        Formatted string or list of record dictionaries
    """
    driver = get_driver()
    params = params or {}
    
    try:
        with get_session() as session:
            result = session.run(query, params)
            records = [dict(record) for record in result]
            
            if format_output:
                return format_result(records)
            return records
    except Exception as e:
        return f"  : {str(e)}"

def replace_entity_in_query(query: str, entity_value: str) -> str:
    """Replace $name placeholder with actual entity value."""
    return query.replace("$name", f'"{entity_value}"')

# =============================================================================
# RESULT FORMATTING
# =============================================================================
def make_serializable(obj: Any) -> Any:
    """Convert Neo4j types to JSON-serializable Python types."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if hasattr(obj, '__iter__') and not isinstance(obj, (str, dict)):
        return [make_serializable(item) for item in obj]
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    return obj

def format_result(records: List[Dict]) -> str:
    """
    Format query results into a readable string.
    Handles various result patterns.
    """
    if not records:
        return "  ."
    
    # Pattern 1: Single count value
    if len(records) == 1 and len(records[0]) == 1:
        key, value = next(iter(records[0].items()))
        if isinstance(value, (int, float)):
            return f" {key}: {value:,}".replace(",", ".")
    
    # Pattern 2: Single record with few fields
    if len(records) == 1 and len(records[0]) <= 3:
        record = records[0]
        parts = [f"**{k}**: {make_serializable(v)}" for k, v in record.items()]
        return " | ".join(parts)
    
    # Pattern 3: List of names/values
    if len(records) <= 20 and all(len(r) == 1 for r in records):
        key = next(iter(records[0].keys()))
        values = [str(make_serializable(r[key])) for r in records]
        return f" {key} ({len(values)} ):\n" + "\n".join(f"   {v}" for v in values)
    
    # Pattern 4: Table-like results
    if len(records) <= 50:
        lines = []
        for i, record in enumerate(records, 1):
            parts = [f"{k}: {make_serializable(v)}" for k, v in record.items()]
            lines.append(f"{i}. " + " | ".join(parts))
        return "\n".join(lines)
    
    # Pattern 5: Large result set - summarize
    return f"  {len(records)} .    20:\n" + \
           format_result(records[:20])

# =============================================================================
# GRAPH EXTRACTION (for Cytoscape visualization)
# =============================================================================
def extract_graph_elements(records: List[Dict]) -> List[Dict]:
    """
    Extract nodes and edges with Centrality Scoring and Temporal metadata.
    """
    elements = []
    seen_nodes = {} # id -> node_data for easy access
    edges = []
    
    # 1. First pass: Collect nodes and edges
    for record in records:
        for key, value in record.items():
            # Handle nodes
            if hasattr(value, 'labels') and hasattr(value, 'element_id'):
                node_id = value.element_id
                if node_id not in seen_nodes:
                    label = next(iter(value.labels), "Node")
                    node_data = dict(value)
                    name = node_data.get('name', node_data.get('code', node_data.get('Contract_REF', node_data.get('description', node_data.get('title', str(node_id))))))
                    
                    # Risk & Temporal Logic
                    risk_level = "low"
                    timestamp = 0
                    date_str = ""
                    
                    if label in ["Contract", "Award"]:
                        val = float(node_data.get('value', node_data.get('amount', node_data.get('Value', 0))))
                        if val > 60000: risk_level = "high"
                        elif val > 30000: risk_level = "medium"
                        
                        # Handle Neo4j Date or String date
                        sd = node_data.get('submission_date', node_data.get('date', node_data.get('signed_date')))
                        if sd:
                            try:
                                if hasattr(sd, 'year'): # Neo4j Date
                                    date_str = f"{sd.year}-{sd.month:02d}-{sd.day:02d}"
                                else:
                                    date_str = str(sd).split('T')[0]
                                
                                import datetime
                                timestamp = datetime.datetime.strptime(date_str, "%Y-%m-%d").timestamp()
                            except: pass

                    seen_nodes[node_id] = {
                        "id": node_id,
                        "label": f"{label}: {name}"[:50],
                        "group": label,
                        "risk": risk_level,
                        "value": val if label in ["Contract", "Award"] else 0,
                        "date": date_str,
                        "timestamp": timestamp,
                        "degree": 0 # to be calculated
                    }
            
            # Handle relationships
            if hasattr(value, 'type') and hasattr(value, 'start_node'):
                start_id = value.start_node.element_id
                end_id = value.end_node.element_id
                edges.append({
                    "start": start_id,
                    "end": end_id,
                    "type": value.type
                })

    # 2. Second pass: Calculate centrality (degree)
    for edge in edges:
        if edge["start"] in seen_nodes: seen_nodes[edge["start"]]["degree"] += 1
        if edge["end"] in seen_nodes: seen_nodes[edge["end"]]["degree"] += 1

    # 3. Build final elements list
    for node in seen_nodes.values():
        # Centrality score (degree normalized/scaled)
        node["centrality"] = 1.0 + (node["degree"] * 0.5)
        elements.append({"data": node})
    
    for edge in edges:
        weight = 0
        end_node = seen_nodes.get(edge["end"])
        if end_node and end_node.get("value"):
            weight = float(end_node.get("value", 0))
        
        elements.append({
            "data": {
                "id": f"e_{edge['start']}_{edge['end']}_{edge['type']}",
                "source": edge["start"],
                "target": edge["end"],
                "label": edge["type"],
                "weight": weight
            }
        })
    
    return elements

# =============================================================================
# BATCH EXECUTION
# =============================================================================
def run_queries_batch(
    authority: str, 
    year: str, 
    query_ids: List[int]
) -> Dict[int, List[Dict]]:
    """
    Run multiple predefined queries for a specific authority and year.
    Returns dict mapping query_id to results.
    """
    results = {}
    
    for qid in query_ids:
        query_def = get_predefined_query(qid)
        if not query_def:
            continue
        
        cypher = query_def["cypher"]
        # Replace placeholders
        cypher = cypher.replace("$name", f'"{authority}"')
        cypher = cypher.replace("$year", f'"{year}"')
        
        raw_results = execute_cypher(cypher, format_output=False)
        if isinstance(raw_results, list):
            results[qid] = raw_results
        else:
            results[qid] = []
    
    return results
from typing import Optional, Dict, Any, List

def get_authority_nuts_name(authority_name: str) -> Optional[str]:
    """
    Returns Authority.NUTS_name for a given authority name (best-effort match).
    """
    if not authority_name:
        return None

    cypher = """
    MATCH (a:Buyer)
    WHERE a.name IS NOT NULL AND (
        toLower(a.name) = toLower($name)
        OR toLower(a.name) CONTAINS toLower($name)
        OR toLower($name) CONTAINS toLower(a.name)
    )
    RETURN a.nuts_code AS nuts_name, a.name AS matched_name
    ORDER BY
      CASE WHEN toLower(a.name) = toLower($name) THEN 0 ELSE 1 END,
      size(a.name) ASC
    LIMIT 1
    """

    try:
        rows = execute_cypher(cypher, {"name": authority_name})
        if isinstance(rows, list) and rows:
            return rows[0].get("nuts_name")
    except Exception:
        pass

    return None

# =============================================================================
# STATISTICS
# =============================================================================
def get_authority_statistics(authority: str, year: str) -> Dict:
    """Get basic statistics for an authority."""
    stats = {}
    
    # Total contracts
    query = '''
    MATCH (a:Buyer {name: $name})-[:AWARDS]->(c:Award)
    WHERE c.submission_date STARTS WITH $year
    RETURN count(c) as total, sum(toFloat(c.value)) as total_value
    '''
    result = execute_cypher(query, {"name": authority, "year": year}, format_output=False)
    if result and isinstance(result, list) and result:
        stats["total_contracts"] = result[0].get("total", 0)
        stats["total_value"] = result[0].get("total_value", 0)
    
    return stats
