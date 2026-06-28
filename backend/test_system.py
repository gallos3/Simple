
import sys
import os
from pathlib import Path

# Add current dir and core dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

from llm_interface import call_llm
from legal_rag import search_legal_corpus

def test():
    print("=== Testing Legal RAG ===")
    try:
        passages = search_legal_corpus("τι λέει το άρθρο 32 για την απευθείας ανάθεση;")
        if passages:
            print(f"Found {len(passages)} passages.")
            print(f"First passage snippet: {passages[0][:100]}...")
        else:
            print("No passages found.")
    except Exception as e:
        print(f"RAG Error: {e}")

    print("\n=== Testing LLM ===")
    try:
        # Check if model exists at the path from config
        from config import MODEL_PATH
        print(f"Looking for model at: {MODEL_PATH}")
        if not os.path.exists(MODEL_PATH):
            print(f"ERROR: Model file not found at {MODEL_PATH}")
            # Try to fix it for this test
            local_model = Path(__file__).parent.parent / "models" / "qwen2.5-3b-instruct-q4_k_m.gguf"
            if local_model.exists():
                print(f"Found model at local path: {local_model}")
                os.environ["MODEL_PATH"] = str(local_model)
                # We might need to re-import or re-init, but let's see if we can just set it
            else:
                print("Model also not found at local path.")
        
        response = call_llm("Πες μου μια σύντομη καλημέρα.")
        print(f"LLM Response: {response}")
    except Exception as e:
        print(f"LLM Error: {e}")

if __name__ == "__main__":
    test()
