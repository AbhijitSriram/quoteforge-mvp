# Deployment Guide for QuoteForge MVP

## Quick Deploy Options

### Option 1: Railway (Recommended - Easiest)

Railway can host both your backend and frontend.

**Backend Deployment:**
1. Go to https://railway.app
2. Sign up with GitHub
3. Click "New Project" → "Deploy from GitHub repo"
4. Select your `quoteforge-mvp` repository
5. Railway will auto-detect Python and deploy
6. Add environment variable if needed:
   - `ALLOWED_ORIGINS`: Your frontend URL (e.g., `https://your-app.vercel.app`)
7. Copy the backend URL (e.g., `https://your-backend.railway.app`)

**Frontend Deployment (Vercel):**
1. Go to https://vercel.com
2. Sign up with GitHub
3. Click "Add New Project"
4. Import `quoteforge-mvp` repository
5. Set **Root Directory** to `frontend`
6. Add environment variable:
   - `NEXT_PUBLIC_API_URL`: Your Railway backend URL
7. Deploy!

### Option 2: Render

**Backend:**
1. Go to https://render.com
2. Sign up with GitHub
3. Click "New" → "Web Service"
4. Connect your GitHub repo
5. Settings:
   - **Build Command**: `cd backend && pip install -r requirements.txt`
   - **Start Command**: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Environment**: Python 3
6. Add environment variable:
   - `ALLOWED_ORIGINS`: Your frontend URL

**Frontend:**
1. In Render, click "New" → "Static Site"
2. Connect your GitHub repo
3. Settings:
   - **Root Directory**: `frontend`
   - **Build Command**: `npm install && npm run build`
   - **Publish Directory**: `frontend/.next`

### Option 3: Fly.io

1. Install Fly CLI: `curl -L https://fly.io/install.sh | sh`
2. Run: `fly launch`
3. Follow prompts
4. Deploy: `fly deploy`

## Environment Variables

### Backend:
- `ALLOWED_ORIGINS`: Comma-separated list of frontend URLs
- `KNOWLEDGE_DB_PATH`: (Optional) Path to knowledge database
- `PORT`: (Auto-set by hosting platform)

### Frontend:
- `NEXT_PUBLIC_API_URL`: Your backend API URL

## Important Notes

1. **Database**: Your SQLite database is in `data/knowledge_index/knowledge.sqlite`. For production, consider migrating to PostgreSQL.

2. **File Uploads**: The `backend/uploads/` directory won't persist on most hosting platforms. Consider using cloud storage (AWS S3, Cloudinary) for production.

3. **CORS**: Make sure to update `ALLOWED_ORIGINS` in your backend to include your production frontend URL.

## Testing Locally Before Deploy

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend (in another terminal)
cd frontend
npm install
npm run dev
```

## Post-Deployment Checklist

- [ ] Backend is accessible at your deployment URL
- [ ] Frontend can connect to backend (check browser console)
- [ ] CORS is configured correctly
- [ ] Environment variables are set
- [ ] Test file upload functionality
- [ ] Test quote generation

