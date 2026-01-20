# Multi-stage build for QuoteForge MVP
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Python backend
FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/

# Copy frontend build (if you want to serve it from backend)
# COPY --from=frontend-builder /app/frontend/.next ./frontend/.next

# Copy data directory
COPY data/ ./data/

# Expose port
EXPOSE 8000

# Start the server
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]


