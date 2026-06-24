# legal_rag.py
"""
Simple - Legal RAG module

Υπεύθυνο για:
- φόρτωση νομικού corpus (Ν.4412/2016, Presetex, νομολογία κ.λπ.)
- δημιουργία embeddings
- αναζήτηση σχετικών αποσπασμάτων βάσει ερώτησης (RAG)

ΠΡΟΫΠΟΘΕΣΗ:
- Ένα αρχείο legal_corpus.jsonl στον ίδιο φάκελο, με γραμμές τύπου:
  {"id": "4412_32_2_g", "source": "Ν.4412/2016, άρθρο 32 παρ.2γ", "text": "Το πλήρες κείμενο..."}
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

import numpy as np

try:
    import faiss  # προαιρετικό, για γρηγορότερο search
    FAISS_AVAILABLE = True
except ImportError:
    faiss = None
    FAISS_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    ST_AVAILABLE = True
except ImportError:
    SentenceTransformer = None
    ST_AVAILABLE = False


# =============================================================================
# GLOBALS
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent
CORPUS_PATH = BASE_DIR / "legal_corpus.jsonl"

_MODEL = None
_EMBEDDINGS = None          # np.ndarray [N, dim]
_INDEX = None               # FAISS index ή None
_LEGAL_DOCS: List[Dict[str, Any]] = []  # κάθε στοιχείο: {"id", "source", "text"}


# =============================================================================
# HELPERS
# =============================================================================

def _load_corpus(path: Path) -> List[Dict[str, Any]]:
    """
    Φορτώνει το corpus από legal_corpus.jsonl.
    Κάθε γραμμή πρέπει να είναι JSON με κλειδιά:
      - id: μοναδικό string
      - source: π.χ. "Ν.4412/2016, άρθρο 32 παρ.2γ"
      - text: το κείμενο του αποσπάσματος
    """
    if not path.exists():
        print(f"[legal_rag] [!] Δεν βρέθηκε το corpus: {path}")
        return []

    docs: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if "text" not in obj:
                    continue
                docs.append(obj)
            except json.JSONDecodeError:
                continue

    print(f"[legal_rag] Φορτώθηκαν {len(docs)} νομικά αποσπάσματα από {path.name}")
    return docs


def _get_model() -> Any:
    """
    Φορτώνει (μονό) το SentenceTransformer model.
    Μπορείς να αλλάξεις το path με local model που έχεις ήδη.
    """
    global _MODEL

    if _MODEL is not None:
        return _MODEL

    if not ST_AVAILABLE:
        raise RuntimeError(
            "[legal_rag] Δεν είναι εγκατεστημένο το sentence-transformers. "
            "Εγκατέστησέ το με: pip install sentence-transformers"
        )

    local_path = BASE_DIR / "local_model"
    model_name = str(local_path) if local_path.exists() else os.environ.get(
        "LEGAL_RAG_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )
    print(f"[legal_rag] Φόρτωση embedding model: {model_name}")
    _MODEL = SentenceTransformer(model_name, device='cpu')
    return _MODEL


def _build_index():
    """
    Δημιουργεί embeddings & FAISS index (αν υπάρχει).
    Αν δεν υπάρχει FAISS, κρατάει μόνο το np.ndarray των embeddings
    και θα κάνουμε manual cosine similarity.
    """
    global _LEGAL_DOCS, _EMBEDDINGS, _INDEX

    if _EMBEDDINGS is not None:
        return

    _LEGAL_DOCS = _load_corpus(CORPUS_PATH)
    if not _LEGAL_DOCS:
        print("[legal_rag] [!] Άδειο νομικό corpus.")
        _EMBEDDINGS = np.zeros((0, 384), dtype="float32")
        _INDEX = None
        return

    emb_cache_path = BASE_DIR / "legal_embeddings.npy"
    cache_loaded = False
    
    if emb_cache_path.exists():
        try:
            cached_emb = np.load(str(emb_cache_path))
            if cached_emb.shape[0] == len(_LEGAL_DOCS):
                print(f"[legal_rag] Φόρτωση cached embeddings από {emb_cache_path.name}...")
                _EMBEDDINGS = cached_emb.astype("float32")
                cache_loaded = True
            else:
                print("[legal_rag] [RELOAD] Το corpus άλλαξε, επαναυπολογισμός embeddings...")
        except Exception as e:
            print(f"[legal_rag] [!] Σφάλμα κατά τη φόρτωση του cache: {e}")

    if not cache_loaded:
        model = _get_model()
        texts = [doc["text"] for doc in _LEGAL_DOCS]
        print(f"[legal_rag] Υπολογισμός embeddings για {len(texts)} αποσπάσματα... (ΜΟΝΟ ΜΙΑ ΦΟΡΑ)")
        emb = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        _EMBEDDINGS = emb.astype("float32")
        print(f"[legal_rag] Αποθήκευση embeddings στο {emb_cache_path.name}...")
        np.save(str(emb_cache_path), _EMBEDDINGS)

    if FAISS_AVAILABLE:
        dim = _EMBEDDINGS.shape[1]
        index = faiss.IndexFlatL2(dim)
        index.add(_EMBEDDINGS)
        _INDEX = index
        print(f"[legal_rag] FAISS index έτοιμο με {_EMBEDDINGS.shape[0]} vectors, dim={dim}")
    else:
        _INDEX = None
        print("[legal_rag] FAISS δεν είναι διαθέσιμο. Θα γίνει manual similarity search.")


def _ensure_ready():
    """Lazy init για corpus + embeddings + index."""
    if _EMBEDDINGS is None:
        _build_index()


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Υπολογισμός cosine similarity μεταξύ ερωτήματος (1, dim) και corpus (N, dim)."""
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-9)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-9)
    return np.dot(a_norm, b_norm.T)

import re

def _extract_law_number(text: str) -> Optional[str]:
    patterns = [
        r'ν\.?\s*(\d{4})',
        r'νόμο[ςυ]?\s*(\d{4})',
        r'Ν\.?\s*(\d{4})',
        r'\b(\d{4})/\d{2,4}\b',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None

# =============================================================================
# PUBLIC API
# =============================================================================

# =============================================================================
# SOURCE HIERARCHY (like MedGraphRAG's evidence tiers)
# =============================================================================

# Tier 1: Primary Law (highest authority)
# Tier 2: Court decisions / Authority decisions (binding precedent)
# Tier 3: EU Guidelines & Directives (interpretive framework)
# Tier 4: Other / Unknown

def _classify_source_tier(source: str) -> int:
    """
    Classifies a source into a priority tier.
    Lower tier = higher priority.
    """
    src = source.lower()
    
    # Tier 1: Greek Law & Constitution
    if any(k in src for k in ["ν.4412", "ν.5164", "νόμος", "nomos", "σύνταγμα"]):
        return 1
    
    # Tier 2: Court / Authority Decisions (ΕΑΔΗΣΥ, Ελεγκτικό Συνέδριο, CURIA)
    # Greek ADA codes (e.g. 9Χ9ΜΟΞΤΒ-Δ63) or curia references
    if any(k in src for k in ["οξτβ", "curia", "εαδησυ", "eaadhsy", "απόφαση", "decision"]):
        return 2
    # ADA-style codes: uppercase Greek + digits pattern
    if len(src) > 8 and any(c.isdigit() for c in src) and any(c.isalpha() for c in src) and "-" in src:
        return 2
    
    # Tier 3: EU Guidelines, common errors guides
    if any(k in src for k in ["guidance", "common mistakes", "eu ", "directive", "οδηγ"]):
        return 3
    
    # Tier 4: Everything else
    return 4

def _tier_label(tier: int) -> str:
    """Human-readable label for each tier."""
    labels = {
        1: "LAW",
        2: "AUTHORITY/COURT DECISION", 
        3: "EU GUIDELINE",
        4: "OTHER"
    }
    return labels.get(tier, "OTHER")


def search_legal_corpus(question: str, k: int = 5) -> List[str]:
    """
    Δέχεται νομική ερώτηση (π.χ. 'τι λέει το 32.2γ για απρόβλεπτες περιστάσεις;')
    και επιστρέφει λίστα από τα k πιο σχετικά αποσπάσματα κειμένου,
    ταξινομημένα κατά ιεραρχία πηγής (Νόμος > Αποφάσεις > Οδηγίες > Λοιπά).

    Αυτή τη συνάρτηση θα καλεί ο agent στο engine.py.
    """
    # Αν το preload τρέχει ακόμα, περίμενε (max 30 δευτερόλεπτα)
    if not _preload_done:
        print("[legal_rag] [WAIT] Model loading, waiting...")
        _preload_lock.wait(timeout=30)
    _ensure_ready()
    law_num = _extract_law_number(question)
    docs = _LEGAL_DOCS
    emb = _EMBEDDINGS

    if law_num:
        filtered_idx = [
            i for i, d in enumerate(docs)
            if str(law_num) in str(d.get("source", ""))
        ]
        if filtered_idx:
            docs = [docs[i] for i in filtered_idx]
            emb = emb[filtered_idx, :]

    if _EMBEDDINGS is None or _EMBEDDINGS.shape[0] == 0:
        print("[legal_rag] [!] Δεν υπάρχουν διαθέσιμα νομικά αποσπάσματα για RAG.")
        return []

    model = _get_model()
    q_emb = model.encode([question], convert_to_numpy=True).astype("float32")

    # Fetch more candidates than needed, then re-rank by source hierarchy
    fetch_k = min(k * 3, len(docs))
    
    if FAISS_AVAILABLE and _INDEX is not None:
        D, I = _INDEX.search(q_emb, min(fetch_k, _EMBEDDINGS.shape[0]))
        idxs = I[0]
    else:
        # Manual cosine similarity
        sims = _cosine_sim(q_emb, _EMBEDDINGS)  # (1, N)
        idxs = np.argsort(-sims[0])[: min(fetch_k, _EMBEDDINGS.shape[0])]

    # Build candidates with tier info
    candidates = []
    for rank, idx in enumerate(idxs):
        doc = _LEGAL_DOCS[int(idx)]
        src = doc.get("source", "")
        txt = doc.get("text", "")
        tier = _classify_source_tier(src)
        candidates.append((tier, rank, src, txt))
    
    # Sort by tier (priority) first, then by original similarity rank
    candidates.sort(key=lambda x: (x[0], x[1]))
    
    # Take top k after re-ranking
    passages: List[str] = []
    for tier, rank, src, txt in candidates[:k]:
        label = _tier_label(tier)
        if src:
            passages.append(f"{label} [{src}]\n{txt}")
        else:
            passages.append(f"{label}\n{txt}")

    return passages

import threading

_preload_done = False
_preload_lock = threading.Event()

def _preload_in_background():
    global _preload_done
    try:
        print("[legal_rag] [RELOAD] Background preload starting...")
        _ensure_ready()
        _preload_done = True
        _preload_lock.set()
        print("[legal_rag] [OK] Background preload complete")
    except Exception as e:
        print(f"[legal_rag] [!] Background preload failed: {e}")
        _preload_lock.set()  # ξεμπλοκάρει ακόμα κι αν αποτύχει

def add_documents(new_docs: List[Dict[str, Any]]):
    """
    Προσθέτει νέα έγγραφα στο in-memory RAG index.
    """
    global _LEGAL_DOCS, _EMBEDDINGS, _INDEX
    _ensure_ready()
    
    if not new_docs:
        return

    model = _get_model()
    texts = [d["text"] for d in new_docs]
    new_embs = model.encode(texts, convert_to_numpy=True).astype("float32")
    
    # Update globals
    _LEGAL_DOCS.extend(new_docs)
    if _EMBEDDINGS is None or _EMBEDDINGS.shape[0] == 0:
        _EMBEDDINGS = new_embs
    else:
        _EMBEDDINGS = np.vstack([_EMBEDDINGS, new_embs])
    
    # Rebuild FAISS if available
    if FAISS_AVAILABLE:
        dim = _EMBEDDINGS.shape[1]
        _INDEX = faiss.IndexFlatL2(dim)
        _INDEX.add(_EMBEDDINGS)
    
    print(f"[legal_rag] [OK] Added {len(new_docs)} new chunks to the index.")

def ingest_pdf(pdf_path: str | Path, source_name: str = None):
    """
    Διαβάζει ένα PDF, το σπάει σε παραγράφους και το προσθέτει στο RAG.
    """
    from pypdf import PdfReader
    
    path = Path(pdf_path)
    if not source_name:
        source_name = path.name
        
    reader = PdfReader(path)
    new_docs = []
    
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text:
            continue
            
        # Απλό σπάσιμο ανά 1000 χαρακτήρες ή παραγράφους
        chunks = [text[j:j+1200] for j in range(0, len(text), 1000)]
        for j, chunk in enumerate(chunks):
            new_docs.append({
                "id": f"upload_{path.stem}_{i}_{j}",
                "source": f"Μεταφορτωμένο: {source_name} (σελ. {i+1})",
                "text": chunk.strip()
            })
            
    if new_docs:
        add_documents(new_docs)
    return len(new_docs)

def start_background_preload():
    t = threading.Thread(target=_preload_in_background, daemon=True)
    t.start()


    
