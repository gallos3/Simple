import json
from pathlib import Path
from pypdf import PdfReader  # pip install pypdf

LEGAL_PDFS_DIR = Path("legal_pdfs")           # φάκελος με τα PDFs
OUTPUT_PATH = Path("legal_corpus.jsonl")      # το corpus για το legal_rag.py

def extract_text_from_pdf(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    texts = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        texts.append(t)
    return "\n".join(texts)

import re

def chunk_text(text: str, max_len: int = 1200, overlap: int = 150) -> list[str]:
    # Σπάμε σε "προτάσεις" με βάση τελείες/ερωτηματικά/παραγράφους
    sentences = re.split(r'(?<=[\.;;!])\s+', text)
    chunks = []
    current = ""

    for sent in sentences:
        s = sent.strip()
        if not s:
            continue

        if len(current) + len(s) + 1 <= max_len:
            current += (" " if current else "") + s
        else:
            if current:
                chunks.append(current)
                # overlap: κρατάμε την ουρά του προηγούμενου chunk
                tail = current[-overlap:]
                current = tail + " " + s
            else:
                current = s

    if current:
        chunks.append(current)
    return chunks

def build_corpus():
    with OUTPUT_PATH.open("w", encoding="utf-8") as out:
        for pdf_path in LEGAL_PDFS_DIR.glob("*.pdf"):
            print(f"→ Επεξεργασία {pdf_path.name}...")
            text = extract_text_from_pdf(pdf_path)
            chunks = chunk_text(text, max_len=800)

            base_id = pdf_path.stem  # π.χ. "4412_2016_FEK"
            source = pdf_path.stem   # μπορείς να το κάνεις πιο φιλικό αν θέλεις

            for i, chunk in enumerate(chunks):
                obj = {
                    "id": f"{base_id}_{i}",
                    "source": source,
                    "text": chunk,
                }
                out.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(f"✅ Έτοιμο corpus στο {OUTPUT_PATH}.")

if __name__ == "__main__":
    build_corpus()
