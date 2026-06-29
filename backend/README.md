# Simple - Procurement Audit Tool

Σύστημα ελέγχου δημοσίων συμβάσεων με φυσική γλώσσα.

## 🐳 Quick Start με Docker

```bash
# 1. Βάλε τα data files (δες παρακάτω)
# 2. Τρέξε:
docker-compose up

# 3. Άνοιξε: http://localhost:5173
```

**Αυτό είναι!** Το Docker σηκώνει Neo4j + Backend + Frontend μαζί.

## 📁 Δομή Φακέλων

```
Simple/
├── backend/
│   ├── config.py           # Κεντρικές ρυθμίσεις
│   ├── config.json         # Configuration file
│   ├── server.py           # Flask API
│   ├── engine.py           # Main orchestration
│   ├── database.py         # Neo4j connection
│   ├── entity_extractor.py # Entity recognition
│   ├── query_matcher.py    # Semantic matching
│   ├── llm_interface.py    # Qwen LLM
│   ├── report_generator.py # Word reports
│   ├── requirements.txt    # Python dependencies
│   ├── predefined_queries.json  # ⚠️ ΑΝΤΕΓΡΑΨΕ ΑΠΟ ΠΑΛΙΟ
│   └── entity_cache.json        # ⚠️ ΑΝΤΕΓΡΑΨΕ ΑΠΟ ΠΑΛΙΟ
│
├── frontend/
│   ├── package.json
│   ├── index.html
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   └── src/
│       ├── main.jsx
│       ├── index.css
│       └── App.jsx
│
├── models/                      # ⚠️ ΑΝΤΕΓΡΑΨΕ ΑΠΟ ΠΑΛΙΟ
│   ├── miniLM/
│   └── qwen2.5-3b-instruct-q4_k_m.gguf
│
└── start_all.bat
```

## ⚠️ Αρχεία που πρέπει να αντιγράψεις

Από τον παλιό φάκελο, αντέγραψε:

1. **`predefined_queries.json`** → `backend/`
2. **`entity_cache.json`** → `backend/`
3. **`models/miniLM/`** → `models/` (ολόκληρος φάκελος)
4. **Qwen2.5 model** → `models/` (ή κατέβασε νέο)

## 🚀 Εγκατάσταση

### 1. Backend
```bash
cd backend
pip install -r requirements.txt
```

### 2. Frontend
```bash
cd frontend
npm install
```

### 3. Download Qwen2.5 (αν δεν το έχεις)
```
https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf
```
Βάλε το στο `models/` και ενημέρωσε το path στο `backend/config.json`.

## ▶️ Εκκίνηση

### Windows
```batch
start_all.bat
```

### Manual
```bash
# Terminal 1
cd backend && python server.py

# Terminal 2
cd frontend && npm run dev
```

## 🔗 URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:5050 |
| Neo4j Browser | http://localhost:7474 |

## 📋 API Endpoints

| Endpoint | Method | Περιγραφή |
|----------|--------|-----------|
| `/ask` | POST | Ερώτηση με φυσική γλώσσα |
| `/upload_csv` | POST | Upload CSV αρχείου |
| `/export_docx` | GET | Έκθεση για συγκεκριμένη αρχή |
| `/export_summary` | GET | Συγκεντρωτική έκθεση |
| `/latest_export` | GET | Τελευταία έκθεση |
| `/health` | GET | Health check |

## 🔧 Configuration

Επεξεργάσου το `backend/config.json`:

```json
{
  "MODEL_PATH": "C:/Simple/models/qwen2.5-3b-instruct-q4_k_m.gguf",
  "EMBEDDINGS_PATH": "models/miniLM",
  "NEO4J_URI": "bolt://localhost:7687",
  "NEO4J_USER": "neo4j",
  "NEO4J_PASSWORD": "your_password"
}
```
## Data Availability and Usage

This repository includes a sample Parquet dataset (`simple_public_procurement_sample.parquet`) to allow users to explore the structure and schema of the underlying data.

⚠️ Important:
The main application does NOT operate directly on the Parquet file.

The system is designed to work with a Neo4j graph database, which contains the full dataset and supports all query and simulation functionalities.

### How to use the sample dataset

The provided Parquet file can be loaded independently for inspection:

```python
import pandas as pd
df = pd.read_parquet("path_to_file")
print(df.head())