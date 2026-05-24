
import json
import sys
import os
import io

# Set encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from entity_extractor import load_entity_cache, extract_entity_composite, normalize_greek, tokenize

try:
    load_entity_cache()
except Exception as e:
    print(f"Error loading cache: {e}")
    sys.exit(1)

question = "ποσε συμβασεισ ειχε το 2025 ο Δημος Θεσσαλονικης?"
cache = load_entity_cache()

# Manually inspect "Δήμος Θεσσαλονίκης"
authorities = cache.get("Buyer.name", [])
found = [a for a in authorities if "Θεσσαλον" in a]
print(f"Found {len(found)} entities with 'Θεσσαλον'")
for f in found[:20]:
    print(f"  - {f}")

result = extract_entity_composite(question, cache)
print("\nExtraction Result:")
print(json.dumps(result, indent=2, ensure_ascii=False))
