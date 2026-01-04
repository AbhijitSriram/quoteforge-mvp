import os
from pathlib import Path
from typing import List, Tuple

from pypdf import PdfReader
from dotenv import load_dotenv

from knowledge_store import upsert_chunks, ensure_db


def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150):
    text = (text or "").strip()
    if not text:
        return []

    chunks = []
    n = len(text)
    start = 0

    while start < n:
        end = min(n, start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # next start (must always move forward)
        next_start = end - overlap
        if next_start <= start:
            next_start = end  # force progress
        start = next_start

    return chunks


def extract_pdf_chunks(pdf_path: Path) -> List[Tuple[str, int, int, str]]:
    """
    Returns rows: (source_file, page, chunk_index, text)
    page is 1-indexed for human-friendly citations.
    """
    reader = PdfReader(str(pdf_path))
    rows: List[Tuple[str, int, int, str]] = []
    source_file = pdf_path.name

    for i, page in enumerate(reader.pages):
        page_num = i + 1
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""

        # Normalize whitespace
        page_text = " ".join(page_text.split())

        if not page_text.strip():
            continue

        chunks = chunk_text(page_text)
        for cidx, ctext in enumerate(chunks):
            rows.append((source_file, page_num, cidx, ctext))
    return rows


def main():
    load_dotenv()
    db_path = os.getenv("KNOWLEDGE_DB_PATH", "../data/knowledge_index/knowledge.sqlite")
    raw_dir = Path("../data/knowledge_raw").resolve()

    ensure_db(db_path)
    if not raw_dir.exists():
        raise SystemExit(f"Missing folder: {raw_dir}")

    pdfs = sorted(raw_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"No PDFs found in: {raw_dir}")

    all_rows: List[Tuple[str, int, int, str]] = []
    for pdf in pdfs:
        rows = extract_pdf_chunks(pdf)
        print(f"Indexed {pdf.name}: {len(rows)} chunks")
        all_rows.extend(rows)

    if not all_rows:
        print("WARNING: No extractable text found. If your PDFs are scanned images, add OCR later.")
        print("Tip: try exporting text or adding a text-based version of the docs.")
    else:
        upsert_chunks(db_path, all_rows)
        print(f"Saved {len(all_rows)} chunks to {db_path}")


if __name__ == "__main__":
    main()
