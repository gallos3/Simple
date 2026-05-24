import sys
sys.path.insert(0, 'backend')
from query_matcher import _keyword_based_match
import json

db = json.load(open('backend/predefined_queries.json', encoding='utf-8'))

tests = [
    ("posses anathetoues arches echo", 1, "skip"),  # skip Greek terminal issues
    ("deixe top 10 etaireies", 12, "skip"),
]

# Real tests
test_pairs = [
    ("\u03b4\u03b5\u03af\u03be\u03b5 top 10 \u03b5\u03c4\u03b1\u03b9\u03c1\u03b5\u03af\u03b5\u03c2", 12),
    ("\u03c0\u03bf\u03b9\u03b5\u03c2 \u03b5\u03af\u03bd\u03b1\u03b9 \u03bf\u03b9 top 10 \u03b5\u03c4\u03b1\u03b9\u03c1\u03b5\u03af\u03b5\u03c2", 12),
    ("top 10 \u03b5\u03c4\u03b1\u03b9\u03c1\u03b5\u03af\u03b5\u03c2", 12),
    ("\u03c0\u03cc\u03c3\u03b5\u03c2 \u03b1\u03bd\u03b1\u03b8\u03ad\u03c4\u03bf\u03c5\u03c3\u03b5\u03c2 \u03b1\u03c1\u03c7\u03ad\u03c2 \u03ad\u03c7\u03c9", 1),
    ("\u03c0\u03cc\u03c3\u03b5\u03c2 \u03b5\u03c4\u03b1\u03b9\u03c1\u03af\u03b5\u03c2 \u03ad\u03c7\u03c9", 2),
    ("\u03c0\u03cc\u03c3\u03b5\u03c2 \u03c3\u03c5\u03bc\u03b2\u03ac\u03c3\u03b5\u03b9\u03c2 \u03ad\u03c7\u03c9", 3),
]

print("=== Keyword Match Test ===")
for q, expected_id in test_pairs:
    r = _keyword_based_match(q, db, has_entity=False)
    if r:
        matched_id = r[0]['id']
        status = "OK" if matched_id == expected_id else f"WRONG (got {matched_id})"
        print(f"  ID:{matched_id} score:{r[1]:.2f} expected:{expected_id} [{status}]")
    else:
        print(f"  NO MATCH expected:{expected_id} [FAIL]")
