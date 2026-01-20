# backend/main.py
import os
import sqlite3
from pathlib import Path
from typing import Optional, Any, Dict

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pypdf import PdfReader

# OCR imports (optional - will gracefully degrade if not available)
try:
    from pdf2image import convert_from_path
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("Warning: OCR libraries not available. Install pdf2image and pytesseract for scanned PDF support.")

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

# CORS origins - add your production frontend URL here
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# PDF Text Extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: Path) -> tuple[str, str]:
    """
    Extract all text from a PDF file.
    First tries direct text extraction, then falls back to OCR for scanned images.
    Returns tuple: (extracted_text, extraction_method)
    where extraction_method is one of: "direct", "ocr", or "none"
    """
    all_text = []
    
    # Step 1: Try direct text extraction first (faster, more accurate)
    try:
        reader = PdfReader(str(pdf_path))
        extracted_any_text = False
        text_length = 0
        
        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    all_text.append(page_text)
                    extracted_any_text = True
                    text_length += len(page_text.strip())
            except Exception as e:
                # Skip pages that can't be extracted
                continue
        
        # If we got substantial text (more than just a watermark), return it
        # Otherwise, we'll try OCR as the text might be graphics-based (like dimension numbers)
        if extracted_any_text and text_length > 200:  # Threshold: more than just a watermark
            full_text = " ".join(all_text)
            full_text = " ".join(full_text.split())  # Normalize whitespace
            return full_text, "direct"
        elif extracted_any_text:
            # We got some text but it's minimal - might be a watermark, try OCR anyway
            # Store what we have as fallback
            pass  # Will fall through to OCR
    except Exception as e:
        # PDF reading failed, will try OCR
        pass
    
    # Step 2: Try OCR (for scanned PDFs/drawings or when minimal text extracted)
    # OCR is needed when dimensions are embedded as graphics/fonts rather than searchable text
    ocr_text = []
    if OCR_AVAILABLE:
        try:
            # Convert PDF pages to images with higher DPI for better OCR accuracy
            images = convert_from_path(str(pdf_path), dpi=400)
            
            for image in images:
                try:
                    # Configure Tesseract for better results with technical drawings
                    # PSM 11: Sparse text (better for drawings with scattered numbers/dimensions)
                    # PSM 6: Uniform block of text (fallback)
                    # Add whitelist to focus on numbers and common dimension symbols
                    configs = [
                        '--psm 11 --oem 3 -c tessedit_char_whitelist=0123456789.,+-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzØ°"\'/RLxX× ',  # Sparse text with whitelist
                        '--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789.,+-ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzØ°"\'/RLxX× ',  # Uniform block with whitelist
                        '--psm 11 --oem 3',  # Sparse text without whitelist
                        '--psm 6 --oem 3',   # Uniform block without whitelist
                        '',  # Default - last resort
                    ]
                    
                    page_text = ""
                    best_text = ""
                    best_length = 0
                    
                    for config in configs:
                        try:
                            page_text = pytesseract.image_to_string(image, config=config if config else None)
                            if page_text.strip() and len(page_text.strip()) > best_length:
                                best_text = page_text
                                best_length = len(page_text.strip())
                                print(f"OCR extracted {len(page_text)} chars with config: {config or 'default'}")
                        except Exception as config_error:
                            print(f"OCR config {config} failed: {config_error}, trying next...")
                            continue
                    
                    if best_text.strip():
                        ocr_text.append(best_text)
                        print(f"Using best OCR result: {best_length} characters")
                    else:
                        print("OCR produced no text for this page")
                except Exception as e:
                    print(f"OCR error on page: {e}")
                    continue
        except Exception as e:
            # OCR failed (might not have tesseract installed, or pdf2image issues)
            print(f"OCR extraction failed (is tesseract installed?): {e}")
            import traceback
            traceback.print_exc()
            
            # Check if OCR libraries are actually installed
            if not OCR_AVAILABLE:
                print("WARNING: OCR libraries not available. Install with: pip install pdf2image pytesseract && brew install tesseract poppler")
    
    # Combine direct extraction and OCR text
    # Prefer OCR if it gives us more text (dimensions are often graphics)
    combined_text = " ".join(all_text) if all_text else ""
    ocr_combined = " ".join(ocr_text) if ocr_text else ""
    
    if ocr_combined and len(ocr_combined) > len(combined_text):
        # OCR gave us more text, use it
        full_text = " ".join(ocr_combined.split())  # Normalize whitespace
        return full_text, "ocr"
    elif ocr_combined:
        # OCR gave us some text, combine with direct extraction
        full_text = " ".join((combined_text + " " + ocr_combined).split())
        return full_text, "ocr"
    elif combined_text:
        # Only direct extraction worked
        full_text = " ".join(combined_text.split())  # Normalize whitespace
        return full_text, "direct"
    
    # No text found via either method
    return "", "none"


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

    # 1) Save file
    uploads_dir = Path(__file__).resolve().parent / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    saved_path = uploads_dir / file.filename
    contents = await file.read()
    saved_path.write_bytes(contents)

    # 2) Extract text from PDF (tries direct extraction first, then OCR for scanned images)
    pdf_text, extraction_method = extract_text_from_pdf(saved_path)
    
    # Debug: Log extraction status
    print(f"\n{'='*60}")
    print(f"PDF Text Extraction: method={extraction_method}, text_length={len(pdf_text)}")
    print(f"OCR Available: {OCR_AVAILABLE}")
    print(f"Text preview (first 500 chars):\n{pdf_text[:500]}")
    print(f"{'='*60}\n")
    
    # 3) Extract signals from PDF text
    base_signals: Dict[str, Any] = extract_signals_from_text(pdf_text)

    # 4) Merge user inputs on top of base signals
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

    # 5) Pull a few reference chunks (by material + rate keywords)
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

    # 6) Run estimate engine
    estimate = compute_estimate(signals)

    return {
        "quote_id": None,
        "uploaded_file": file.filename,
        "pdf_text_extracted": len(pdf_text) > 0,
        "extraction_method": extraction_method,
        "ocr_available": OCR_AVAILABLE,
        "pdf_text_preview": pdf_text[:500] if pdf_text else "",
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
