# backend/main.py
import os
import sqlite3
from pathlib import Path
from typing import Optional, Any, Dict

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from knowledge_store import query_chunks
from quote_engine import compute_estimate, extract_signals_from_text

app = FastAPI(title="QuoteForge MVP API")

# ---------------------------------------------------------------------------
# DB path
# ---------------------------------------------------------------------------

DEFAULT_DB = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "knowledge_index"
    / "knowledge.sqlite"
)
DB_PATH = Path(os.getenv("KNOWLEDGE_DB_PATH", str(DEFAULT_DB))).expanduser().resolve()


# ---------------------------------------------------------------------------
# CORS (for Next.js dev)
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str
    top_k: int = 5


# ---------------------------------------------------------------------------
# Basic endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
    }


@app.get("/sources")
def sources():
    if not DB_PATH.exists():
        return {
            "db_path": str(DB_PATH),
            "sources": [],
            "warning": "DB file not found",
        }

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "SELECT DISTINCT source_file FROM chunks ORDER BY source_file;"
        )
        return {
            "db_path": str(DB_PATH),
            "sources": [r[0] for r in cur.fetchall()],
        }
    finally:
        conn.close()


@app.post("/ask")
def ask(req: AskRequest):
    q = (req.question or "").strip()
    if not q:
        return {
            "question": req.question,
            "results": [],
            "warning": "Empty question",
        }

    rows = query_chunks(str(DB_PATH), q, top_k=req.top_k)
    return {
        "question": req.question,
        "db_path": str(DB_PATH),
        "result_count": len(rows),
        "results": [
            {
                "source": r[0],
                "page": r[1],
                "chunk_index": r[2],
                "preview": (r[3][:250] + "...") if len(r[3]) > 250 else r[3],
                "text": r[3],
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Quote endpoint – single-shot Phase 2
# ---------------------------------------------------------------------------

@app.post("/quote")
async def quote(
    file: UploadFile = File(...),

    # core user inputs (material required, rest optional)
    material: str = Form(...),
    qty: Optional[int] = Form(1),
    machining_minutes: Optional[float] = Form(None),
    material_weight_lbs: Optional[float] = Form(None),

    # optional geometry helpers
    length_in: Optional[float] = Form(None),
    width_in: Optional[float] = Form(None),
    height_in: Optional[float] = Form(None),

    # optional knobs
    complexity: Optional[str] = Form("moderate"),
    size: Optional[str] = Form("medium"),
    tolerance: Optional[str] = Form("normal"),
):
    """
    Upload drawing/CAD + simple inputs → immediate quote.
    """

    # 1) Save file (optional, but nice to have)
    uploads_dir = Path(__file__).resolve().parent / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    saved_path = uploads_dir / file.filename
    contents = await file.read()
    saved_path.write_bytes(contents)

    # 2) Placeholder text extraction (can plug OCR later)
    # For now, we just pass empty text into extract_signals_from_text
    base_signals: Dict[str, Any] = extract_signals_from_text("")

    # 3) Merge user inputs on top of base signals
    #    (user inputs override anything inferred from text)
    user_inputs: Dict[str, Any] = {
        "material": material,
        "qty": qty,
        "machining_minutes": machining_minutes,
        "material_weight_lbs": material_weight_lbs,
        "length_in": length_in,
        "width_in": width_in,
        "height_in": height_in,
        "complexity": complexity,
        "size": size,
        "tolerance": tolerance,
        "notes": f"Uploaded {file.filename}",
    }

    signals: Dict[str, Any] = dict(base_signals)
    for k, v in user_inputs.items():
        if v is not None and v != "":
            signals[k] = v

    # 4) Pull a few reference chunks (by material + rate keywords)
    reference_query = " ".join(
        x
        for x in [
            signals.get("material"),
            "rate",
            "cost",
            "multiplier",
            "lead time",
        ]
        if x
    )

    if reference_query:
        refs = query_chunks(str(DB_PATH), reference_query, top_k=5)
    else:
        refs = []

    # 5) Run estimate engine
    estimate = compute_estimate(signals)

    return {
        "quote_id": None,
        "uploaded_file": file.filename,
        "signals": signals,
        "references": [
            {
                "source": r[0],
                "page": r[1],
                "chunk_index": r[2],
                "text": r[3][:600],
            }
            for r in refs
        ],
        "estimate": estimate,
        "next_step": "Quote complete" if estimate.get("ready") else "Ask user for missing inputs",
    }
