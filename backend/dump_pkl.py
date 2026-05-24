import pickle
import unicodedata

with open('entity_cache.index.pkl', 'rb') as f:
    idx, norm_cache = pickle.load(f)

def strip_accents(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn').upper()

lines = []
for entry in norm_cache:
    name = str(entry[0])
    if 'ΔΗΜΗΤΡΙ' in strip_accents(name):
        lines.append(name)

with open('scratch/pickle_dump.txt', 'w', encoding='utf-8') as f:
    for l in lines:
        f.write(l + '\n')
