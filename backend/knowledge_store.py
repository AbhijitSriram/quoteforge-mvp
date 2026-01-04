import sqlite3
from typing import List, Tuple

DDL = """
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_file TEXT NOT NULL,
  page INTEGER NOT NULL,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_file);
"""

def ensure_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(DDL)
        conn.commit()
    finally:
        conn.close()

def upsert_chunks(db_path: str, rows: List[Tuple[str, int, int, str]]) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM chunks;")
        conn.executemany(
            "INSERT INTO chunks (source_file, page, chunk_index, text) VALUES (?, ?, ?, ?);",
            rows
        )
        conn.commit()
    finally:
        conn.close()

def query_chunks(db_path: str, query: str, top_k: int = 6) -> List[Tuple[str, int, int, str]]:
    """
    Simple keyword search (no embeddings). Good enough for MVP.
    Returns: (source_file, page, chunk_index, text)
    """
    q = f"%{query.strip()}%"
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            """
            SELECT source_file, page, chunk_index, text
            FROM chunks
            WHERE text LIKE ?
            LIMIT ?;
            """,
            (q, top_k),
        )
        return cur.fetchall()
    finally:
        conn.close()

def search_chunks(question: str, top_k: int = 6, db_path: str = None):
    """
    Wrapper used by main.py.
    Reads DB path from env if not passed.
    Returns list of dicts so main.py can render JSON nicely.
    """
    import os

    if db_path is None:
        db_path = os.getenv("KNOWLEDGE_DB_PATH")

    rows = query_chunks(db_path=db_path, query=question, top_k=top_k)

    # Convert tuples -> dicts
    return [
        {
            "source_file": r[0],
            "page": r[1],
            "chunk_index": r[2],
            "text": r[3],
        }
        for r in rows
    ]
