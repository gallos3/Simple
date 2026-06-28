import json
import os
from typing import Dict

def generate_scenario_graph_draft(topic: str, rag_ctx: str) -> dict:
    """
    Offline Authoring Skeleton: Uses LLM + RAG to generate a new labyrinth scenario graph.
    Currently returns a safe placeholder draft. Do NOT wire to live gameplay.
    """
    
    # Safe fallback/placeholder structure
    draft_graph = {
        "scenario_id": topic.lower().replace(" ", "_").replace("-", "_")[:50],
        "version": "1.0.0",
        "validation_status": "draft",
        "authoring_source_mode": "rag_assisted_draft",
        "title": f"Draft Scenario: {topic}",
        "source_basis": rag_ctx[:2000] if rag_ctx else "No RAG context provided.",
        "learning_objectives": ["TBD: Objective 1", "TBD: Objective 2"],
        "red_flags": ["TBD: Red flag 1"],
        "review": {
            "reviewed_by": "",
            "review_date": "",
            "review_notes": "",
            "approval_status": "pending"
        },
        "start_node": "n1",
        "max_steps": 6,
        "nodes": {
            "n1": {
                "text": "Placeholder scenario context generated for topic.",
                "challenge": "What is your next step?",
                "options": {
                    "A": {
                        "text": "Placeholder Option A",
                        "next_node": "END",
                        "score_delta": 0,
                        "time_delta": 0,
                        "audit_risk_delta": 0,
                        "admin_burden_delta": 0,
                        "value_for_money_risk_delta": 0,
                        "feedback": "Placeholder feedback for A",
                        "expert_log": "Placeholder log A"
                    },
                    "B": {
                        "text": "Placeholder Option B",
                        "next_node": "END",
                        "score_delta": -5,
                        "time_delta": 1,
                        "audit_risk_delta": 1,
                        "admin_burden_delta": 1,
                        "value_for_money_risk_delta": 1,
                        "feedback": "Placeholder feedback for B",
                        "expert_log": "Placeholder log B"
                    },
                    "C": {
                        "text": "Placeholder Option C",
                        "next_node": "END",
                        "score_delta": -10,
                        "time_delta": 2,
                        "audit_risk_delta": 2,
                        "admin_burden_delta": 2,
                        "value_for_money_risk_delta": 2,
                        "feedback": "Placeholder feedback for C",
                        "expert_log": "Placeholder log C"
                    }
                }
            }
        }
    }
    
    return draft_graph

def save_draft_graph(graph: dict, output_path: str):
    """
    Saves a generated draft graph to disk for expert review.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)
