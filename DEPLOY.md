# 🚀 Deployment Guide - QuoteForge MVP

This guide will help you deploy your QuoteForge MVP to the web so it's publicly accessible.

## 📋 Quick Start (Recommended: Railway + Vercel)

**Railway** (Backend) + **Vercel** (Frontend) is the easiest and fastest way to deploy.

---

## Step 1: Deploy Backend to Railway

### 1.1 Create Railway Account
1. Go to https://railway.app
2. Sign up with your **GitHub** account
3. Click **"New Project"** → **"Deploy from GitHub repo"**
4. Select your `quoteforge-mvp` repository
5. Railway will auto-detect it's a Python project

### 1.2 Configure Backend Service
1. Railway will create a service automatically
2. Click on the service to open settings
3. Go to **"Settings"** → **"Variables"**
4. Add these environment variables:
   ```
   ALLOWED_ORIGINS=https://your-frontend.vercel.app,https://your-frontend.vercel.app
   ```
   (We'll update this after deploying the frontend)

5. Railway will automatically:
   - Install dependencies from `backend/requirements.txt`
   - Run the start command from `railway.json`
   - Assign a public URL (e.g., `https://your-app.railway.app`)

### 1.3 Get Your Backend URL
1. Go to **"Settings"** → **"Networking"**
2. Click **"Generate Domain"** to get a public URL
3. Copy this URL (e.g., `https://quoteforge-backend.railway.app`)

### 1.4 Install System Dependencies (for OCR)
Railway uses Nixpacks which should auto-detect dependencies, but if OCR doesn't work:

1. Create a `nixpacks.toml` file in the project root:
   ```toml
   [phases.setup]
   nixPkgs = ["tesseract", "poppler_utils"]
   
   [phases.install]
   cmds = ["pip install -r backend/requirements.txt"]
   
   [start]
   cmd = "cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT"
   ```

---

## Step 2: Deploy Frontend to Vercel

### 2.1 Create Vercel Account
1. Go to https://vercel.com
2. Sign up with your **GitHub** account
3. Click **"Add New Project"**
4. Import your `quoteforge-mvp` repository

### 2.2 Configure Frontend
1. **Root Directory**: Set to `frontend`
2. **Framework Preset**: Next.js (auto-detected)
3. **Build Command**: `npm run build` (default)
4. **Output Directory**: `.next` (default)

### 2.3 Add Environment Variables
1. In the **"Environment Variables"** section, add:
   ```
   NEXT_PUBLIC_API_BASE=https://your-backend-url.railway.app
   ```
   (Replace with your actual Railway backend URL)

2. Click **"Deploy"**

### 2.4 Get Your Frontend URL
1. After deployment, Vercel will give you a URL like:
   `https://quoteforge-mvp.vercel.app`

---

## Step 3: Update CORS Settings

### 3.1 Update Backend CORS
1. Go back to Railway → Your backend service → **"Variables"**
2. Update `ALLOWED_ORIGINS`:
   ```
   ALLOWED_ORIGINS=https://quoteforge-mvp.vercel.app,https://quoteforge-mvp.vercel.app
   ```
   (Use your actual Vercel frontend URL)

3. Railway will automatically redeploy with the new environment variable

---

## Step 4: Test Your Deployment

1. Visit your Vercel frontend URL
2. Try uploading a PDF drawing
3. Check the browser console (F12) for any errors
4. Verify the quote is generated correctly

---

## 🔧 Alternative Deployment Options

### Option A: Render.com

**Backend:**
1. Go to https://render.com
2. Sign up with GitHub
3. Click **"New"** → **"Web Service"**
4. Connect your GitHub repo
5. Settings:
   - **Name**: `quoteforge-backend`
   - **Environment**: `Python 3`
   - **Build Command**: `cd backend && pip install -r requirements.txt`
   - **Start Command**: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Add environment variable:
   - `ALLOWED_ORIGINS`: Your frontend URL

**Frontend:**
1. In Render, click **"New"** → **"Static Site"**
2. Connect your GitHub repo
3. Settings:
   - **Root Directory**: `frontend`
   - **Build Command**: `npm install && npm run build`
   - **Publish Directory**: `frontend/.next`

### Option B: Fly.io

1. Install Fly CLI:
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. Login:
   ```bash
   fly auth login
   ```

3. Initialize:
   ```bash
   fly launch
   ```

4. Deploy:
   ```bash
   fly deploy
   ```

---

## 📝 Important Notes

### 1. Database Persistence
- Your SQLite database (`data/knowledge_index/knowledge.sqlite`) is included in the repo
- For production, consider migrating to PostgreSQL (Railway offers free PostgreSQL)

### 2. File Uploads
- Uploaded PDFs are stored in `backend/uploads/`
- This directory is **ephemeral** on most platforms (files are lost on redeploy)
- For production, consider using:
  - **AWS S3**
  - **Cloudinary**
  - **Railway Volumes** (persistent storage)

### 3. OCR Dependencies
- OCR requires system-level dependencies (Tesseract, Poppler)
- Railway's Nixpacks should handle this automatically
- If OCR fails, check the deployment logs

### 4. Environment Variables Summary

**Backend (Railway):**
```
ALLOWED_ORIGINS=https://your-frontend.vercel.app
PORT=8000 (auto-set by Railway)
```

**Frontend (Vercel):**
```
NEXT_PUBLIC_API_BASE=https://your-backend.railway.app
```

---

## 🐛 Troubleshooting

### Backend not accessible
- Check Railway logs: Railway dashboard → Your service → "Deployments" → Click latest → "View Logs"
- Verify the service is running (green status)

### CORS errors
- Make sure `ALLOWED_ORIGINS` includes your exact frontend URL (with `https://`)
- No trailing slashes
- Redeploy backend after changing environment variables

### Frontend can't connect to backend
- Check `NEXT_PUBLIC_API_BASE` is set correctly in Vercel
- Verify backend URL is accessible (try opening it in browser)
- Check browser console for error messages

### OCR not working
- Check Railway logs for OCR-related errors
- Verify Tesseract and Poppler are installed (may need `nixpacks.toml`)

---

## ✅ Post-Deployment Checklist

- [ ] Backend is accessible at Railway URL
- [ ] Frontend is accessible at Vercel URL
- [ ] Frontend can connect to backend (no CORS errors)
- [ ] Test file upload works
- [ ] Test quote generation works
- [ ] OCR is working (for scanned PDFs)
- [ ] Environment variables are set correctly

---

## 🎉 You're Done!

Your QuoteForge MVP should now be live and accessible to the public!

**Frontend URL**: `https://your-app.vercel.app`  
**Backend URL**: `https://your-backend.railway.app`

Share your frontend URL with others to test it out!

