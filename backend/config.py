"""
Simple - Centralized Configuration
Όλες οι ρυθμίσεις και constants σε ένα σημείο.
"""

import os
import json
from pathlib import Path

# =============================================================================
# PATHS
# =============================================================================
BASE_DIR = Path(__file__).parent
CONFIG_FILE = BASE_DIR / "config.json"

# Load config.json
if CONFIG_FILE.exists():
    with open(CONFIG_FILE, encoding="utf-8") as f:
        _config = json.load(f)
else:
    _config = {}

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", _config.get("TAVILY_API_KEY"))

# =============================================================================
# NEO4J CONNECTION
# =============================================================================
NEO4J_URI = os.environ.get("NEO4J_URI", _config.get("NEO4J_URI", "bolt://localhost:7687"))
NEO4J_USER = os.environ.get("NEO4J_USER", _config.get("NEO4J_USER", "neo4j"))
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", _config.get("NEO4J_PASSWORD", "password"))
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", _config.get("NEO4J_DATABASE", "neo4j"))

# =============================================================================
# MODEL PATHS
# =============================================================================
MODEL_PATH = os.environ.get("MODEL_PATH", _config.get("MODEL_PATH", "models/qwen2.5-3b-instruct-q4_k_m.gguf"))
EMBEDDINGS_PATH = os.environ.get("EMBEDDINGS_PATH", _config.get("EMBEDDINGS_PATH", "models/miniLM"))

# =============================================================================
# DIRECT AWARD THRESHOLDS (N.4412/2016)
# =============================================================================
class DirectAwardThresholds:
    """Όρια απευθείας ανάθεσης κατά Ν.4412/2016"""
    GENERAL = 30_000.0          # €30.000 για γενικές υπηρεσίες/προμήθειες
    CONSTRUCTION = 60_000.0     # €60.000 για έργα (CPV 45xxx)
    SECURITY = 60_000.0         # €60.000 για υπηρεσίες ασφαλείας

DirectContractThresholds = DirectAwardThresholds # Alias for compatibility with engine.py

# =============================================================================
# CPV CODES
# =============================================================================
# Κατασκευαστικά έργα - όριο €60.000
CONSTRUCTION_CPV_CODES = frozenset({
    "45000000", "45100000", "45110000", "45111000", "45112000",
    "45200000", "45210000", "45211000", "45212000", "45213000",
    "45220000", "45230000", "45231000", "45232000", "45233000",
    "45234000", "45240000", "45250000", "45260000", "45261000",
    "45262000", "45300000", "45310000", "45320000", "45330000",
    "45340000", "45400000", "45410000", "45420000", "45430000",
    "45440000", "45450000"
})

# Υπηρεσίες ασφαλείας - όριο €60.000
SECURITY_CPV_CODES = frozenset({
    "79710000", "79711000", "79713000", "79714000", "79715000"
})

# Εξαιρούμενοι CPV (για queries 101-108)
EXCLUDED_CPV_CODES = CONSTRUCTION_CPV_CODES | SECURITY_CPV_CODES

def get_threshold_for_cpv(cpv_code: str) -> float:
    """Επιστρέφει το όριο απευθείας ανάθεσης για συγκεκριμένο CPV."""
    if cpv_code and len(cpv_code) >= 8:
        prefix = cpv_code[:8]
        if prefix in CONSTRUCTION_CPV_CODES:
            return DirectAwardThresholds.CONSTRUCTION
        if prefix in SECURITY_CPV_CODES:
            return DirectAwardThresholds.SECURITY
    return DirectAwardThresholds.GENERAL

# =============================================================================
# NLU SETTINGS
# =============================================================================
SIMILARITY_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "0.55"))
ENTITY_MIN_SCORE = float(os.environ.get("ENTITY_MIN_SCORE", "0.8"))

# =============================================================================
# PROCEDURE TYPE ALIASES
# =============================================================================
PROCEDURE_ALIASES = {
    "απευθείας ανάθεση": ["απευθείας", "direct", "απ' ευθείας", "απ ευθειας"],
    "ανοικτός διαγωνισμός": ["ανοικτός", "ανοιχτός", "open", "διαγωνισμός"],
    "κλειστός διαγωνισμός": ["κλειστός", "restricted"],
    "διαπραγμάτευση": ["διαπραγμάτευση", "negotiated"],
    "συνοπτικός διαγωνισμός": ["συνοπτικός", "summary"],
}

# =============================================================================
# SECURITY
# =============================================================================
DANGEROUS_PHRASES = frozenset({
    "delete", "drop", "remove", "truncate", "detach",
    "διαγραφή", "κατάργηση", "καταστροφή", "format", "shutdown"
})

STOPWORDS = frozenset({
    # Articles & prepositions
    "για", "το", "της", "του", "στην", "στο", "ένα", "την",
    "τον", "με", "από", "σε", "και", "ή", "που", "να", "θα",
    "είναι", "έχει", "μου", "σου", "τους", "όλα", "αυτό",
    # Common question/command words - DO NOT use for entity matching
    "δωσε", "δώσε", "πες", "πεσ", "δειξε", "δείξε", "φτιαξε", "φτιάξε",
    "εκθεση", "έκθεση", "αναφορα", "αναφορά", "ελεγχου", "ελέγχου", "ελεγχος", "έλεγχος",
    "συμβασεις", "συμβάσεις", "συμβαση", "σύμβαση",
    "ποσες", "πόσες", "ποσα", "πόσα", "ποιες", "ποιές", "ποιοι", "ποιοί",
    "μια", "μία", "ενα", "ένα",
    "report", "audit", "check"
})

def is_dangerous_query(text: str) -> bool:
    """Ελέγχει αν το query περιέχει επικίνδυνες εντολές."""
    lowered = text.lower()
    return any(phrase in lowered for phrase in DANGEROUS_PHRASES)

# =============================================================================
# API SETTINGS
# =============================================================================
API_HOST = os.environ.get("API_HOST", "localhost")
API_PORT = int(os.environ.get("API_PORT", str(_config.get("API_PORT", 5051))))
_frontend_port = _config.get("FRONTEND_PORT", 5174)
FRONTEND_URL = os.environ.get("FRONTEND_URL", f"http://localhost:{_frontend_port}")

# =============================================================================
# DIRECTORIES
# =============================================================================
UPLOAD_FOLDER = BASE_DIR / "RAG"
EXPORT_FOLDER = BASE_DIR / "exports"
REPORTS_FOLDER = BASE_DIR / "reports"
DATA_FOLDER = BASE_DIR / "data"
TEMPLATES_FOLDER = BASE_DIR / "templates"
LEGAL_PDFS_FOLDER = BASE_DIR / "legal_pdfs"

# Create directories if they don't exist
for folder in [
    UPLOAD_FOLDER,
    EXPORT_FOLDER,
    REPORTS_FOLDER,
    DATA_FOLDER,
    TEMPLATES_FOLDER,
    LEGAL_PDFS_FOLDER
    ]:
    folder.mkdir(exist_ok=True)


# =============================================================================
# ROLES & PERMISSIONS
# =============================================================================
ROLE_AUDITOR = "AUDITOR"
ROLE_TRAINEE = "TRAINEE"

# Mapping of roles to allowed intents
ROLE_PERMISSIONS = {
    ROLE_AUDITOR: [
        "report", "legal", "mixed_legal_data", "market_diagnostic",
        "data_risk", "data_simple", "general", 
        "procurement_simulation"
    ],
    ROLE_TRAINEE: [
        "legal", "general", "procurement_simulation"
    ]
}

DEFAULT_ROLE = ROLE_AUDITOR

# =============================================================================
# DEBUG
# =============================================================================
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

if DEBUG:
    print(f"[Config] NEO4J_URI: {NEO4J_URI}")
    print(f"[Config] MODEL_PATH: {MODEL_PATH}")
    print(f"[Config] SIMILARITY_THRESHOLD: {SIMILARITY_THRESHOLD}")
    print(f"[Config] DEFAULT_ROLE: {DEFAULT_ROLE}")
