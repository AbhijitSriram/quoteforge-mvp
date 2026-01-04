# QuoteForge MVP

A quote generation system for manufacturing parts with CAD file upload support.

## Project Structure

- `backend/` - FastAPI backend server
- `frontend/` - Next.js frontend application
- `data/` - Knowledge base and indexed data

## Setup

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Features

- CAD file upload
- Material and quantity input
- Automated quote generation
- Knowledge base integration

