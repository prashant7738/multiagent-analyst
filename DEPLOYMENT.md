# Deployment

Backend on Render, database on Supabase, frontend on Vercel. `render.yaml`
(repo root) and `frontend/AnalyzeAI/vercel.json` already define most of the
infrastructure — you just need to connect your accounts and fill in secrets,
since those steps require your own login and can't be automated for you.

## 1. Database (Supabase)

1. Go to [supabase.com](https://supabase.com), sign in (or create an account), and click **New Project**.
2. Pick an organization, name the project (e.g. `multiagent-analyst`), set a database password (save it somewhere — you'll need it in the connection string), and choose a region close to you. Wait a minute or two for provisioning.
3. In the project, open **Settings > Database**. Under **Connection string**, copy the **direct connection** URI (not the pooled/transaction one — the app already pools connections itself, see below, so the direct connection avoids some transaction-pooler quirks around prepared statements). It looks like:
   `postgresql://postgres:[YOUR-PASSWORD]@db.xxxxxxxxxxxx.supabase.co:5432/postgres`
4. Replace `[YOUR-PASSWORD]` with the password from step 2. You'll paste this whole string into Render as `DATABASE_URL` in step 2.5 below.

pgvector is available on Supabase's free tier by default — the app creates the `vector` extension itself on first use (`CREATE EXTENSION IF NOT EXISTS vector`), no manual step needed.

**Free-tier notes:** 500MB storage, and the project **pauses after 7 days of no database activity** (not deleted — your data is safe, you just click "Restore" in the Supabase dashboard to bring it back). This is different from a typical managed-Postgres free tier that gets deleted outright; pausing is the tradeoff for it never expiring for good.

## 2. Backend (Render)

1. Go to [render.com](https://render.com), sign in (or create an account), and click **New > Blueprint**.
2. Connect your GitHub account if you haven't, then select the `multiagent-analyst` repo. Render will detect `render.yaml` at the repo root and show you the `multiagent-analyst-api` web service it defines.
3. Click **Apply**. The first build takes a few minutes (installing pandas/scipy/langgraph etc.).
4. Once the service exists, open it in the Render dashboard and go to **Environment**. Fill in the env vars `render.yaml` deliberately left blank (`sync: false` means Render prompts you instead of storing them in the repo):
   - `DATABASE_URL` — the Supabase connection string from step 1.4
   - `GROQ_API_KEY`
   - `GEMINI_API_KEY`
   - `HF_TOKEN`

   Use your own keys here — this is also where you'd rotate a key if the app's original one gets revoked or runs out of quota.
5. Save, which triggers a redeploy. Once it's live, copy the service's public URL (top of the Render dashboard page, looks like `https://multiagent-analyst-api.onrender.com`) — you'll need it for step 3.

**Free-tier notes:**
- The free web service spins down after ~15 minutes with no traffic and takes ~50s to wake back up on the next request. A pipeline run in progress with no open connection to it (e.g. you closed the browser tab mid-analysis) could theoretically get interrupted by a spin-down — not a concern for active use, worth knowing if you leave something running unattended.
- Uploaded CSVs and generated charts/reports live on the service's local disk, which is wiped on every redeploy/restart (a deliberate call to keep the initial setup simple — a persistent disk can be added later if needed).
- PDF report export needs system libraries (Cairo/Pango) that Render's base Python image doesn't include — it already falls back to HTML export automatically, so this degrades gracefully rather than breaking.
- The backend pools its own database connections (10 max, shared across requests) rather than opening one per request, so it stays well under both Render's and Supabase's connection limits even under concurrent use.

## 3. Frontend (Vercel)

1. Go to [vercel.com](https://vercel.com), sign in, and click **Add New > Project**.
2. Import the same `multiagent-analyst` GitHub repo.
3. In the project's configuration step, set **Root Directory** to `frontend/AnalyzeAI` (this is a monorepo — Vercel needs to know where the actual app lives). Framework preset should auto-detect as Vite.
4. Under **Environment Variables**, add:
   - `VITE_API_BASE_URL` = the Render backend URL from step 2.5 (e.g. `https://multiagent-analyst-api.onrender.com`, no trailing slash)
5. Click **Deploy**. `vercel.json` in that folder already handles client-side routing (React Router) so refreshing on `/profile`, `/analyze/:jobId`, etc. won't 404.

## 4. Tighten CORS (final step)

Right now the backend accepts requests from any origin (`API_CORS_ORIGINS=*`) so step 3 could deploy without knowing the Vercel URL in advance. Once you have it:

1. Back in Render, open the `multiagent-analyst-api` service > **Environment**.
2. Set `API_CORS_ORIGINS` to your exact Vercel URL, e.g. `https://your-app.vercel.app` (comma-separate if you also want to keep `http://localhost:5173` for local dev against the deployed backend).
3. Save — this redeploys with the origin restricted.

## Redeploying after future pushes

Render and Vercel both auto-deploy on push to `main` by default — no extra steps needed for routine updates. Supabase needs no redeploy at all (it's just the database).
