# Backend Setup & Running Instructions

## Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

## Quick Start

### 1. Navigate to the backend directory
```bash
cd backend
```

### 2. Create a virtual environment (recommended)
```bash
python3 -m venv venv
```

### 3. Activate the virtual environment

**On macOS/Linux:**
```bash
source venv/bin/activate
```

**On Windows:**
```bash
venv\Scripts\activate
```

### 4. Install dependencies
```bash
pip install -r requirements.txt
```

**Note:** Some dependencies are optional:
- `pythonocc-core` - Can be skipped if you're not using STEP/STP files
- `pdf2image` and `pytesseract` - For OCR (scanned PDF support)

### 5. Install OCR dependencies (Optional - for scanned PDF support)

**On macOS:**
```bash
brew install tesseract poppler
```

**On Ubuntu/Debian:**
```bash
sudo apt-get install tesseract-ocr poppler-utils
```

**On Windows:**
Download Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki

### 6. Run the server

**Development mode (with auto-reload):**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Production mode:**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

Or use the provided script:
```bash
chmod +x start.sh
./start.sh
```

## Access the API

Once running, you can access:
- **API Docs (Swagger UI):** http://localhost:8000/docs
- **Alternative API Docs (ReDoc):** http://localhost:8000/redoc
- **Health Check:** http://localhost:8000/health

## Troubleshooting

### If pip install fails:
- Make sure you have the latest pip: `pip install --upgrade pip`
- Try installing packages individually: `pip install fastapi uvicorn[standard] pydantic pypdf`

### If OCR doesn't work:
- The app will still work without OCR, just won't read scanned PDFs
- Make sure Tesseract is installed: `tesseract --version`
- On macOS, make sure poppler is installed: `brew install poppler`

### If you get import errors:
- Make sure you're in the backend directory
- Verify your virtual environment is activated
- Check that all dependencies are installed: `pip list`

## Testing the API

You can test the `/health` endpoint:
```bash
curl http://localhost:8000/health
```

Test the `/quote` endpoint with a PDF:
```bash
curl -X POST "http://localhost:8000/quote" \
  -F "file=@path/to/your/drawing.pdf" \
  -F "material=aluminum" \
  -F "qty=10"
```


