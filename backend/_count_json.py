import json

cnt = 0
with open('data/endorse_extract.json', 'r', encoding='utf-8') as f:
    for line in f:
        if '"ca": {' in line:
            cnt += 1
print('Awards lines count:', cnt)
