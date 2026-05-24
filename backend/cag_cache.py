"""
Simple Federated - Cache Augmented Generation (CAG) Module
Αποθηκεύει και ανακτά απαντήσεις βάσει σημασιολογικής ομοιότητας (semantic caching).
"""

import json
import time
import os
from pathlib import Path
import numpy as np
from typing import Optional, Dict, Any, List, Tuple

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    faiss = None
    FAISS_AVAILABLE = False

# Χρήση του ίδιου μοντέλου embedding με το legal_rag
from legal_rag import _get_model as get_embedding_model

BASE_DIR = Path(__file__).resolve().parent
CACHE_DATA_FILE = BASE_DIR / "cag_cache_data.json"
CACHE_EMB_FILE = BASE_DIR / "cag_cache_embs.npy"

# Configuration
SIMILARITY_THRESHOLD = 0.95
DEFAULT_DATA_TTL = 3600 * 24  # 1 μέρα για δεδομένα (μπορεί να γίνει invalidate με ingestion)
DEFAULT_LEGAL_TTL = 3600 * 24 * 30  # 30 μέρες για νομικά θέματα

class CAGCache:
    def __init__(self):
        self.entries: List[Dict[str, Any]] = []
        self.embeddings: Optional[np.ndarray] = None
        self.faiss_index = None
        self.model = None
        self._load()

    def _lazy_init_model(self):
        if self.model is None:
            self.model = get_embedding_model()

    def _load(self):
        if CACHE_DATA_FILE.exists() and CACHE_EMB_FILE.exists():
            try:
                with open(CACHE_DATA_FILE, "r", encoding="utf-8") as f:
                    self.entries = json.load(f)
                
                embs = np.load(str(CACHE_EMB_FILE))
                if embs.shape[0] == len(self.entries):
                    self.embeddings = embs.astype("float32")
                    self._build_index()
                else:
                    print("[CAG] Σφάλμα: Ασυμφωνία μεγέθους μεταξύ data και embeddings. Εκκαθάριση cache.")
                    self.clear()
            except Exception as e:
                print(f"[CAG] Σφάλμα φόρτωσης cache: {e}")
                self.clear()
        else:
            self.embeddings = np.zeros((0, 384), dtype="float32") # Assuming 384 for paraphrase-multilingual-MiniLM-L12-v2

    def _save(self):
        with open(CACHE_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, ensure_ascii=False, indent=2)
        if self.embeddings is not None and self.embeddings.shape[0] > 0:
            np.save(str(CACHE_EMB_FILE), self.embeddings)

    def _build_index(self):
        if FAISS_AVAILABLE and self.embeddings is not None and self.embeddings.shape[0] > 0:
            dim = self.embeddings.shape[1]
            self.faiss_index = faiss.IndexFlatIP(dim) # Inner Product για Cosine Sim (αν κάνουμε normalize)
            # Normalize for cosine similarity
            norms = np.linalg.norm(self.embeddings, axis=1, keepdims=True) + 1e-9
            normalized_embs = self.embeddings / norms
            self.faiss_index.add(normalized_embs)
        else:
            self.faiss_index = None

    def clear(self):
        self.entries = []
        self.embeddings = np.zeros((0, 384), dtype="float32")
        self.faiss_index = None
        if CACHE_DATA_FILE.exists(): CACHE_DATA_FILE.unlink()
        if CACHE_EMB_FILE.exists(): CACHE_EMB_FILE.unlink()

    def invalidate_data_cache(self):
        """Εκκαθαρίζει μόνο τις απαντήσεις δεδομένων (π.χ. μετά από νέο Ingestion)."""
        new_entries = []
        keep_indices = []
        for i, entry in enumerate(self.entries):
            if entry["type"] == "legal":
                new_entries.append(entry)
                keep_indices.append(i)
        
        if len(new_entries) < len(self.entries):
            print(f"[CAG] Invalidation: Διαγράφηκαν {len(self.entries) - len(new_entries)} data entries.")
            self.entries = new_entries
            if self.embeddings is not None and len(keep_indices) > 0:
                self.embeddings = self.embeddings[keep_indices]
            else:
                self.embeddings = np.zeros((0, 384), dtype="float32")
            self._build_index()
            self._save()

    def add(self, query: str, response: str, query_type: str = "data"):
        """Προσθέτει μια απάντηση στο cache."""
        self._lazy_init_model()
        emb = self.model.encode([query], convert_to_numpy=True).astype("float32")
        
        ttl = DEFAULT_LEGAL_TTL if query_type == "legal" else DEFAULT_DATA_TTL
        
        entry = {
            "query": query,
            "response": response,
            "type": query_type,
            "timestamp": time.time(),
            "ttl": ttl
        }
        
        self.entries.append(entry)
        if self.embeddings is None or self.embeddings.shape[0] == 0:
            self.embeddings = emb
        else:
            self.embeddings = np.vstack([self.embeddings, emb])
            
        self._build_index()
        self._save()
        print(f"[CAG] Αποθηκεύτηκε στο cache ({query_type}): {query}")

    def get(self, query: str) -> Optional[str]:
        """Αναζητά την ερώτηση στο cache βάσει σημασιολογικής ομοιότητας."""
        if not self.entries or self.embeddings is None or self.embeddings.shape[0] == 0:
            return None
            
        self._lazy_init_model()
        q_emb = self.model.encode([query], convert_to_numpy=True).astype("float32")
        
        # Normalize
        q_norm = q_emb / (np.linalg.norm(q_emb, axis=1, keepdims=True) + 1e-9)
        
        best_idx = -1
        best_score = -1.0
        
        if FAISS_AVAILABLE and self.faiss_index is not None:
            D, I = self.faiss_index.search(q_norm, 1)
            best_score = D[0][0]
            best_idx = I[0][0]
        else:
            # Manual Cosine Sim
            embs_norm = self.embeddings / (np.linalg.norm(self.embeddings, axis=1, keepdims=True) + 1e-9)
            sims = np.dot(q_norm, embs_norm.T)[0]
            best_idx = np.argmax(sims)
            best_score = sims[best_idx]
            
        if best_score >= SIMILARITY_THRESHOLD:
            entry = self.entries[best_idx]
            # Έλεγχος TTL
            age = time.time() - entry["timestamp"]
            if age <= entry["ttl"]:
                print(f"[CAG] Cache HIT (score: {best_score:.3f}): {query} -> {entry['query']}")
                return entry["response"]
            else:
                print(f"[CAG] Cache EXPIRED (score: {best_score:.3f}, age: {age:.0f}s): {query}")
                # Θα μπορούσαμε να το διαγράψουμε εδώ, αλλά θα το αφήσουμε για το επόμενο cleanup
                
        return None

# Singleton instance
_cache_instance = None

def get_cag_cache() -> CAGCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CAGCache()
    return _cache_instance
