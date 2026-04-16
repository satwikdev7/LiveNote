# Deployment Guide

## Stack
- **Frontend** → Vercel
- **Backend** → Render (Docker, Standard plan)
- **Database + Storage** → Supabase

---

## Step 1 — Supabase Setup

1. Create a new Supabase project at [supabase.com](https://supabase.com).
2. Go to **Storage** and create a bucket named `meeting-exports`.
3. Go to **SQL Editor** and run the schema from `docs/supabase.sql`.
4. Collect these values (you'll need them in Step 2):
   - **Project URL** (`SUPABASE_URL`) — Settings → API → Project URL
   - **Service Role Key** (`SUPABASE_SERVICE_ROLE_KEY`) — Settings → API → service_role key

---

## Step 2 — Backend on Render

1. Push this repo to GitHub (if not done already).
2. Go to [render.com](https://render.com) → **New** → **Blueprint**.
3. Connect your GitHub repo. Render will detect `render.yaml` automatically.
4. After the service is created, go to the service **Environment** tab and fill in these secrets:

   | Key | Value |
   |-----|-------|
   | `FRONTEND_ORIGIN` | `https://<your-vercel-domain>` (set after Step 3) |
   | `DEEPSEEK_API_KEY` | Your DeepSeek API key |
   | `HUGGINGFACE_TOKEN` | Your Hugging Face token (for pyannote diarization) |
   | `SUPABASE_URL` | From Step 1 |
   | `SUPABASE_SERVICE_ROLE_KEY` | From Step 1 |

5. Click **Manual Deploy** → **Deploy latest commit**.
6. Wait for the build to finish (first build takes ~5–10 min due to ML model downloads).
7. Note your backend URL: `https://livenote-backend.onrender.com` (or similar).

> **Memory note**: Standard plan gives 2 GB RAM, which is required for pyannote diarization.
> If you want to skip diarization to save resources, set `DIARIZATION_ENABLED=false`.

---

## Step 3 — Frontend on Vercel

1. Go to [vercel.com](https://vercel.com) → **Add New Project** → import your GitHub repo.
2. In the **Configure Project** screen:
   - Set **Root Directory** to `frontend`
   - Framework will be auto-detected as Next.js
3. Add these **Environment Variables**:

   | Key | Value |
   |-----|-------|
   | `NEXT_PUBLIC_BACKEND_WS_URL` | `wss://livenote-backend.onrender.com/ws/meeting` |
   | `NEXT_PUBLIC_APP_NAME` | `LiveNote` |

4. Click **Deploy**.
5. Note your Vercel URL: `https://livenote.vercel.app` (or similar).

---

## Step 4 — Wire Up CORS

Go back to Render → your backend service → **Environment** and set:

```
FRONTEND_ORIGIN = https://<your-vercel-domain>
```

Then trigger a redeploy: **Manual Deploy** → **Deploy latest commit**.

---

## Step 5 — Smoke Test

1. Open your Vercel URL.
2. Enter a meeting title and click **Start the Meeting**.
3. Speak for ~20 seconds and confirm the transcript appears.
4. End the meeting and confirm the export panel appears.

---

## Notes

- The first request after Render spins up (cold start) can take 30–60 seconds — this is normal on Render's free/standard tier.
- Use `wss://` (not `ws://`) for the deployed WebSocket URL.
- If you change your Vercel domain later, update `FRONTEND_ORIGIN` in Render and redeploy.
