# backend/main.py
import os
import shutil
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
    
    # Try to configure tesseract path (needed on some systems)
    # On Railway/Nixpacks, tesseract should be in PATH, but try common locations
    tesseract_cmd = shutil.which("tesseract")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        print(f"Tesseract found at: {tesseract_cmd}")
    else:
        # Try common installation paths
        for path in ["/usr/bin/tesseract", "/usr/local/bin/tesseract"]:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                print(f"Tesseract found at: {path}")
                break
    
    # Test if tesseract is actually working
    try:
        pytesseract.get_tesseract_version()
        OCR_AVAILABLE = True
        print("OCR is available and working")
    except Exception as e:
        print(f"Tesseract found but not working: {e}")
        OCR_AVAILABLE = False
except ImportError as e:
    OCR_AVAILABLE = False
    print(f"Warning: OCR libraries not available: {e}")
    print("Install with: pip install pdf2image pytesseract && system package manager for tesseract/poppler")

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
    "http://localhost:3000,http://127.0.0.1:3000,https://quoteforge-mvp.vercel.app"
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
    For technical drawings, always attempts OCR since dimensions are often graphics.
    Returns tuple: (extracted_text, extraction_method)
    where extraction_method is one of: "direct", "ocr", or "none"
    """
    direct_text = []
    
    # Step 1: Try direct text extraction first (faster, more accurate)
    try:
        reader = PdfReader(str(pdf_path))
        text_length = 0
        
        for page in reader.pages:
            try:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    direct_text.append(page_text)
                    text_length += len(page_text.strip())
            except Exception as e:
                print(f"Error extracting text from page: {e}")
                continue
        
        print(f"Direct extraction: {text_length} characters from {len(direct_text)} pages")
    except Exception as e:
        print(f"PDF reading failed: {e}")
        direct_text = []
    
    # Step 2: Always try OCR for technical drawings
    # Technical drawings often have dimensions as graphics, not searchable text
    # Even if direct extraction found some text, OCR might find more (especially numbers)
    ocr_text = []
    if OCR_AVAILABLE:
        try:
            print(f"Attempting OCR extraction (OCR_AVAILABLE={OCR_AVAILABLE})...")
            # Convert PDF pages to images with higher DPI for better OCR accuracy
            images = convert_from_path(str(pdf_path), dpi=400)
            print(f"Converted PDF to {len(images)} images for OCR")
            
            for page_num, image in enumerate(images):
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
                                print(f"Page {page_num+1}: OCR extracted {len(page_text)} chars with config: {config[:50] or 'default'}")
                        except Exception as config_error:
                            print(f"Page {page_num+1}: OCR config failed: {config_error}, trying next...")
                            continue
                    
                    if best_text.strip():
                        ocr_text.append(best_text)
                        print(f"Page {page_num+1}: Using best OCR result: {best_length} characters")
                    else:
                        print(f"Page {page_num+1}: OCR produced no text")
                except Exception as e:
                    print(f"OCR error on page {page_num+1}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
        except Exception as e:
            # OCR failed (might not have tesseract installed, or pdf2image issues)
            print(f"OCR extraction failed: {e}")
            import traceback
            traceback.print_exc()
            
            # Check if OCR libraries are actually installed
            if not OCR_AVAILABLE:
                print("WARNING: OCR libraries not available. Install with: pip install pdf2image pytesseract && brew install tesseract poppler")
    else:
        print("WARNING: OCR not available. Install pdf2image, pytesseract, tesseract, and poppler for scanned PDF support.")
    
    # Combine direct extraction and OCR text
    # For technical drawings, OCR often finds dimensions that direct extraction misses
    combined_direct = " ".join(direct_text) if direct_text else ""
    ocr_combined = " ".join(ocr_text) if ocr_text else ""
    
    print(f"Text summary: direct={len(combined_direct)} chars, OCR={len(ocr_combined)} chars")
    
    # Strategy: Always prefer OCR for technical drawings since dimensions are often graphics
    # But also combine with direct extraction to get any metadata/text that OCR might miss
    if ocr_combined:
        # OCR found text - use it (prefer OCR for dimensions)
        if combined_direct:
            # Combine both for maximum coverage (direct might have metadata, OCR has dimensions)
            full_text = " ".join((combined_direct + " " + ocr_combined).split())
            print(f"Using combined direct+OCR: {len(full_text)} chars (direct={len(combined_direct)}, OCR={len(ocr_combined)})")
            return full_text, "ocr"
        else:
            # Only OCR worked
            full_text = " ".join(ocr_combined.split())  # Normalize whitespace
            print(f"Using OCR only: {len(full_text)} chars")
            return full_text, "ocr"
    elif combined_direct:
        # Only direct extraction worked (OCR failed or not available)
        full_text = " ".join(combined_direct.split())  # Normalize whitespace
        print(f"Using direct only: {len(full_text)} chars (OCR not available or failed)")
        return full_text, "direct"
    
    # No text found via either method
    print("WARNING: No text extracted from PDF via direct extraction or OCR")
    print(f"  - Direct extraction: {len(direct_text)} pages processed")
    print(f"  - OCR available: {OCR_AVAILABLE}")
    print(f"  - OCR text pages: {len(ocr_text)}")
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
    ocr_status = "unknown"
    tesseract_path = "not found"
    if OCR_AVAILABLE:
        try:
            import pytesseract
            tesseract_path = pytesseract.pytesseract.tesseract_cmd or "not configured"
            version = pytesseract.get_tesseract_version()
            ocr_status = f"available (version: {version})"
        except Exception as e:
            ocr_status = f"error: {e}"
    else:
        ocr_status = "not available"
    
    return {
        "status": "ok",
        "db_path": str(DB_PATH),
        "db_exists": DB_PATH.exists(),
        "ocr_available": OCR_AVAILABLE,
        "ocr_status": ocr_status,
        "tesseract_path": tesseract_path,
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

    # Get OCR diagnostic info
    ocr_diagnostic = {
        "available": OCR_AVAILABLE,
        "status": "unknown"
    }
    if OCR_AVAILABLE:
        try:
            import pytesseract
            ocr_diagnostic["tesseract_path"] = pytesseract.pytesseract.tesseract_cmd or "not configured"
            ocr_diagnostic["status"] = "working"
        except Exception as e:
            ocr_diagnostic["status"] = f"error: {str(e)}"
    else:
        ocr_diagnostic["status"] = "not available"
    
    return {
        "quote_id": None,
        "uploaded_file": file.filename,
        "pdf_text_extracted": len(pdf_text) > 0,
        "extraction_method": extraction_method,
        "ocr_available": OCR_AVAILABLE,
        "ocr_diagnostic": ocr_diagnostic,
        "pdf_text_length": len(pdf_text),
        "pdf_text_preview": pdf_text[:500] if pdf_text else "",
        "raw_text_preview": pdf_text[:500] if pdf_text else "",  # Alias for frontend compatibility
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
