import json

def validate_scenario_graph(graph: dict) -> dict:
    result = {
        "valid": True,
        "errors": [],
        "warnings": []
    }
    
    # Check top-level keys
    required_keys = ["scenario_id", "version", "validation_status", "start_node", "max_steps", "nodes"]
    for k in required_keys:
        if k not in graph:
            result["errors"].append(f"Missing required key: {k}")
            result["valid"] = False
            
    if not result["valid"]:
        return result
        
    if graph["validation_status"] not in ["draft", "needs_review", "approved", "active"]:
        result["errors"].append(f"Invalid validation_status: {graph['validation_status']}")
        result["valid"] = False
        
    if "source_basis" not in graph:
        result["errors"].append("Missing required key: source_basis (can be empty, but must exist)")
        result["valid"] = False
        
    if graph["validation_status"] == "active":
        review = graph.get("review", {})
        if review.get("approval_status") != "approved":
            result["errors"].append("Active graph must have review.approval_status == 'approved'")
            result["valid"] = False
            
    start_node = graph["start_node"]
    nodes = graph["nodes"]
    
    if start_node not in nodes:
        result["errors"].append(f"start_node '{start_node}' not found in nodes")
        result["valid"] = False
        
    # Check nodes
    for node_id, node in nodes.items():
        if "text" not in node or "challenge" not in node or "options" not in node:
            result["errors"].append(f"Node '{node_id}' missing text, challenge, or options")
            result["valid"] = False
            continue
            
        options = node["options"]
        if set(options.keys()) != {"A", "B", "C"}:
            result["errors"].append(f"Node '{node_id}' options must be exactly A, B, C")
            result["valid"] = False
            
        for opt_key, opt in options.items():
            required_opt_keys = [
                "text", "next_node", "score_delta", "time_delta", 
                "audit_risk_delta", "admin_burden_delta", "value_for_money_risk_delta",
                "feedback", "expert_log"
            ]
            for ok in required_opt_keys:
                if ok not in opt:
                    result["errors"].append(f"Node '{node_id}' Option '{opt_key}' missing required key: {ok}")
                    result["valid"] = False
                    
            if "next_node" in opt:
                nn = opt["next_node"]
                if nn != "END" and nn not in nodes:
                    result["errors"].append(f"Node '{node_id}' Option '{opt_key}' next_node '{nn}' does not exist")
                    result["valid"] = False
                    
            for delta_key in ["score_delta", "time_delta", "audit_risk_delta", "admin_burden_delta", "value_for_money_risk_delta"]:
                if delta_key in opt and not isinstance(opt[delta_key], int):
                    result["errors"].append(f"Node '{node_id}' Option '{opt_key}' {delta_key} must be an integer")
                    result["valid"] = False
                    
    if not result["valid"]:
        return result
        
    # Reachability and depth check
    visited = set()
    ends_reached = 0
    
    def dfs(node_id, depth):
        nonlocal ends_reached
        if depth > graph["max_steps"]:
            return False
            
        visited.add(node_id)
        
        node = nodes[node_id]
        for opt in node["options"].values():
            nn = opt["next_node"]
            if nn == "END":
                ends_reached += 1
            else:
                if not dfs(nn, depth + 1):
                    return False
        return True
        
    if not dfs(start_node, 1):
        result["errors"].append(f"Path depth exceeds max_steps ({graph['max_steps']})")
        result["valid"] = False
        
    if ends_reached == 0:
        result["errors"].append("No path reaches 'END'")
        result["valid"] = False
        
    unreachable = set(nodes.keys()) - visited
    if unreachable:
        result["errors"].append(f"Unreachable nodes detected: {', '.join(unreachable)}")
        result["valid"] = False
        
    return result

def validate_graph_file(filepath: str) -> dict:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            graph = json.load(f)
        return validate_scenario_graph(graph)
    except Exception as e:
        return {"valid": False, "errors": [f"File parsing error: {e}"], "warnings": []}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        res = validate_graph_file(sys.argv[1])
        print(json.dumps(res, indent=2))
