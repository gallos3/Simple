# legal_ingest.py
"""
Ingestion εργαλείο για το νομικό RAG.
Μετατρέπει ένα PDF σε chunks κειμένου και τα προσθέτει στο legal_corpus.jsonl

Χρήση:
    from legal_ingest import ingest_pdf_to_corpus
    ingest_pdf_to_corpus("legal_pdfs/4412_2016_FEK.pdf")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pypdf import PdfReader   # pip install pypdf

BASE_DIR = Path(__file__).resolve().parent.parent
PDF_FOLDER = BASE_DIR / "legal_pdfs"
CORPUS_PATH = BASE_DIR / "legal_corpus.jsonl"


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Βγάζει όλο το κείμενο από PDF, σε ένα μεγάλο string."""
    reader = PdfReader(str(pdf_path))
    parts: List[str] = []

    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        parts.append(t)

    return "\n".join(parts)


def chunk_text(text: str, max_len: int = 800) -> List[str]:
    """
    Σπάει μεγάλο κείμενο σε κομμάτια (chunks) ~max_len χαρακτήρων,
    προσπαθώντας να σέβεται αλλαγές γραμμής.
    """
    chunks: List[str] = []
    current = ""

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        if len(current) + len(line) + 1 <= max_len:
            current += (" " if current else "") + line
        else:
            if current:
                chunks.append(current)
            current = line

    if current:
        chunks.append(current)

    return chunks


def ingest_pdf_to_corpus(pdf_path: str | Path, corpus_path: Path | None = None) -> int:
    """
    Παίρνει ένα PDF, φτιάχνει chunks και τα προσθέτει στο legal_corpus.jsonl.
    Επιστρέφει πόσα chunks γράφτηκαν.

    - pdf_path: path του PDF
    - corpus_path: (προαιρετικά) custom path για το corpus
    """
    pdf_path = Path(pdf_path)
    if corpus_path is None:
        corpus_path = CORPUS_PATH

    if not pdf_path.exists():
        print(f"[legal_ingest] ⚠️ Το PDF δεν βρέθηκε: {pdf_path}")
        return 0

    print(f"[legal_ingest] Επεξεργασία PDF: {pdf_path.name}")

    text = extract_text_from_pdf(pdf_path)
    chunks = chunk_text(text, max_len=800)

    if not chunks:
        print(f"[legal_ingest] ⚠️ Δεν βρέθηκε κείμενο στο PDF: {pdf_path.name}")
        return 0

    base_id = pdf_path.stem  
    source = pdf_path.stem

    written = 0
    with corpus_path.open("a", encoding="utf-8") as out:
        for idx, chunk in enumerate(chunks):
            obj = {
                "id": f"{base_id}_{idx}",
                "source": source,
                "text": chunk,
            }
            out.write(json.dumps(obj, ensure_ascii=False) + "\n")
            written += 1

    print(f"[legal_ingest] ✅ Προστέθηκαν {written} chunks στο {corpus_path.name}")
    return written


if __name__ == "__main__":
    print("[legal_ingest] Μαζική επεξεργασία όλων των PDF στον φάκελο legal_pdfs...")
    PDF_FOLDER.mkdir(exist_ok=True)
    total_chunks = 0
    for pdf_file in PDF_FOLDER.glob("*.pdf"):
        total_chunks += ingest_pdf_to_corpus(pdf_file)
    print(f"[legal_ingest] Τέλος. Συνολικά chunks: {total_chunks}")
