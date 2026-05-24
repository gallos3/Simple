import json
import codecs

with open('entity_cache.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    authorities = data.get('Buyer.name', [])

search_terms = ['ΑΡΙΣΤΟΤΕΛΕΙΟ', 'ΘΕΣΣΑΛΟΝΙΚΗΣ', 'ΑΠΘ', 'Α.Π.Θ.', 'ΠΑΝΕΠΙΣΤΗΜΙΟ']

with codecs.open('search_results.txt', 'w', encoding='utf-8') as out:
    for term in search_terms:
        matches = [a for a in authorities if term in a]
        out.write(f"--- Matches for {term} ({len(matches)}) ---\n")
        for m in matches[:50]: # top 50
            out.write(f"- {m}\n")
        out.write("\n")
