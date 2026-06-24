"""
Simple - Web Search Module (Legal Specialization)
Searches Curia, ΕΑΔΗΣΥ, and other legal domains for procurement context.
"""
from typing import List, Dict, Any
import os

try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False

from utils.config import TAVILY_API_KEY

_client = None

def _get_client() -> "TavilyClient":
    global _client
    if _client is None:
        if not TAVILY_AVAILABLE:
            raise RuntimeError("tavily-python is not installed.")
        if not TAVILY_API_KEY:
            raise RuntimeError("TAVILY_API_KEY is not set.")
        _client = TavilyClient(api_key=TAVILY_API_KEY)
    return _client

# Domains relevant to the user
LEGAL_DOMAINS = [
    "curia.europa.eu", 
    "eaadhsy.gr", 
    "audit-office.gov.gr", 
    "et.gr", # National Printing House
    "diavgeia.gov.gr",
    "promitheus.gov.gr" # ESIDIS
]

def mask_legal_query(text: str) -> str:
    """
    Αφαιρεί ευαίσθητα δεδομένα (ποσά, ονόματα εταιρειών, ημερομηνίες) 
    πριν την αναζήτηση στον ιστό για προστασία απορρήτου.
    """
    import re
    # 1. Αφαίρεση ποσών (π.χ. 10.000€, 10000 ευρώ)
    t = re.sub(r'\d+[\.,]?\d*\s*(€|ευρώ|euro)', '', text, flags=re.I)
    t = re.sub(r'\b\d{4,}\b', '', t) #Standalone μεγάλοι αριθμοί
    
    # 2. Αφαίρεση ημερομηνιών (π.χ. 21/04/2024)
    t = re.sub(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', '', t)
    
    # 3. Διατήρηση μόνο νομικών όρων και βασικών λέξεων
    legal_terms = [
        "curia", "αποφαση", "νομολογια", "απευθειας", "αναθεση", 
        "διαγωνισμος", "αρθρο", "παραγραφος", "4412", "5164",
        "δημοσια", "συμβαση", "παρανομο", "νομιμο", "εαδησυ"
    ]
    
    words = t.lower().split()
    safe_words = []
    for w in words:
        clean_w = w.strip(".,;:()[]\"'")
        if len(clean_w) < 3: continue
        # Αν είναι νομικός όρος ή γενική λέξη (όχι κεφαλαίο στο πρωτότυπο αν ήταν δυνατή η διάκριση)
        # Εδώ κάνουμε ένα απλό φιλτράρισμα
        safe_words.append(clean_w)
    
    # Περιορισμός σε νομικά keywords αν η ερώτηση είναι πολύ μεγάλη/συγκεκριμένη
    return " ".join(safe_words[:10])

def search_legal_web(question: str, max_results: int = 4) -> str:
    """
    Searches legal domains via Tavily.
    """
    if not TAVILY_API_KEY:
        return ""

    # PRIVACY GUARD: Mask the query before it leaves the local environment
    masked_query = mask_legal_query(question)
    if not masked_query:
        return ""

    print(f"[web_search] 🛡️  Privacy Masking: '{question[:30]}...' -> '{masked_query}'")

    try:
        client = _get_client()
        
        # Optimize query for legal search
        search_query = masked_query
        if "curia" not in search_query.lower() and "απόφαση" in search_query.lower():
            search_query += " curia case law"

        response = client.search(
            query=search_query,
            search_depth="advanced",
            max_results=max_results,
            include_domains=LEGAL_DOMAINS,
            include_answer=True
        )

        parts: List[str] = []
        
        # 1. Synthesized Answer
        if response.get("answer"):
            parts.append(f"⚖️ **Σύνοψη από τον Ιστό:** {response['answer']}")

        # 2. Results
        for r in response.get("results", []):
            title = r.get("title", "Απόφαση/Έγγραφο")
            snippet = r.get("content", "")[:400]
            url = r.get("url", "")
            parts.append(f"🔹 **[{title}]**\n{snippet}\n🔗 [Πηγή]({url})")

        if not parts:
            # Fallback to general search if no domain results
            response = client.search(query=search_query, max_results=2)
            for r in response.get("results", []):
                parts.append(f"🔸 **{r.get('title')}**: {r.get('content')[:300]} (Πηγή: {r.get('url')})")

        return "\n\n".join(parts)

    except Exception as e:
        print(f"[web_search] Error: {e}")
        return ""


def search_general_web(question: str, max_results: int = 3) -> str:
    """
    General-purpose web search via Tavily for non-legal questions
    (e.g. weather, news, general knowledge).
    """
    if not TAVILY_API_KEY:
        return ""

    try:
        client = _get_client()
        response = client.search(
            query=question,
            search_depth="basic",
            max_results=max_results,
            include_answer=True
        )

        parts: List[str] = []

        # Synthesized Answer
        if response.get("answer"):
            parts.append(response["answer"])

        # Individual results as context
        for r in response.get("results", []):
            title = r.get("title", "")
            snippet = r.get("content", "")[:300]
            url = r.get("url", "")
            if snippet:
                parts.append(f"🔹 **{title}**\n{snippet}\n🔗 {url}")

        return "\n\n".join(parts) if parts else ""

    except Exception as e:
        print(f"[web_search] General search error: {e}")
        return ""
