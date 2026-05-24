import urllib.request
import json
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() in ('cp1253', 'cp1252', 'mbcs'):
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

BASE = 'http://localhost:5051'

def ask(question, label):
    payload = json.dumps({'question': question}).encode('utf-8')
    req = urllib.request.Request(BASE + '/ask', data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode('utf-8'))
            ans = data.get('answer', data.get('response', str(data)))
            ans_clean = ans.replace('\n', ' ')
            print(f'[{label}] OK - {ans_clean[:300]}...')
    except Exception as e:
        print(f'[{label}] ERROR - {e}')

def get_hitl(label):
    req = urllib.request.Request(BASE + '/api/pending_reviews?entity=Buyer')
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode('utf-8'))
            if isinstance(data, list):
                print(f'[{label}] OK - Array with {len(data)} items')
            else:
                print(f'[{label}] OK - {str(data)[:200]}')
    except Exception as e:
        print(f'[{label}] ERROR - {e}')

print('Running tests...')
ask('Ποιο είναι το όριο για απευθείας ανάθεση στο Ν.4412/2016;', 'T1-Legal')
ask('Ποια είναι η εντροπία της αγοράς δημοσίων συμβάσεων το 2024;', 'T2-Market')
ask('Κάνε διάγνωση αγοράς για τον Δήμο Αθηναίων', 'T3-AuthorityDiag')
ask('Υπολόγισε τον Institutional Closure Index για τον Δήμο Θεσσαλονίκης', 'T4-ICI')
get_hitl('T5-HITL')
print('Tests completed.')
