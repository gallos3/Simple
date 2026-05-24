import json
with open('entity_cache.json', encoding='utf-8') as f:
    d = json.load(f)
lines = [v for v in d['Buyer.name'] if 'ΔΗΜΗΤΡΙ' in v.upper() or 'ΔΗΜΗΤΡΊ' in v.upper()]
with open('scratch/cache_dump.txt', 'w', encoding='utf-8') as f:
    for l in lines:
        f.write(l + '\n')
