# Deployment

Backend + Postgres on Render, frontend on Vercel. `render.yaml` (repo root) and
`frontend/AnalyzeAI/vercel.json` already define the infrastructure — you just
need to connect your accounts and fill in secrets, since those steps require
your own login and can't be automated for you.

## 1. Backend + database (Render)

1. Go to [render.com](https://render.com), sign in (or create an account), and click **New > Blueprint**.
2. Connect your GitHub account if you haven't, then select the `multiagent-analyst` repo. Render will detect `render.yaml` at the repo root and show you the two resources it defines: the `multiagent-analyst-api` web service and the `multiagent-analyst-db` Postgres database.
3. Click **Apply** to create both. The first build takes a few minutes (installing pandas/scipy/langgraph etc.).
4. Once the service exists, open it in the Render dashboard and go to **Environment**. Fill in the three secrets `render.yaml` deliberately left blank (`sync: false` means Render prompts you instead of storing them in the repo):
   - `GROQ_API_KEY`
   - `GEMINI_API_KEY`
   - `HF_TOKEN`

   Use your own keys here — this is also where you'd rotate a key if the app's original one gets revoked or runs out of quota.
5. Save, which triggers a redeploy. Once it's live, copy the service's public URL (top of the Render dashboard page, looks like `https://multiagent-analyst-api.onrender.com`) — you'll need it for step 2.

**Free-tier notes, so nothing here surprises you later:**
- The free Postgres database **expires 30 days after creation** (14-day grace period after that), capped at 1GB. Fine for testing; upgrade the database's plan in Render before day 30 if you want it to persist.
- The free web service spins down after ~15 minutes with no traffic and takes ~50s to wake back up on the next request. A pipeline run in progress with no open connection to it (e.g. you closed the browser tab mid-analysis) could theoretically get interrupted by a spin-down — not a concern for active use, worth knowing if you leave something running unattended.
- Uploaded CSVs and generated charts/reports live on the service's local disk, which is wiped on every redeploy/restart (this was a deliberate call to keep the initial setup simple — see the note in the PR/commit if you want to add a persistent disk later).
- PDF report export needs system libraries (Cairo/Pango) that Render's base Python image doesn't include — it already falls back to HTML export automatically, so this degrades gracefully rather than breaking.

## 2. Frontend (Vercel)

1. Go to [vercel.com](https://vercel.com), sign in, and click **Add New > Project**.
2. Import the same `multiagent-analyst` GitHub repo.
3. In the project's configuration step, set **Root Directory** to `frontend/AnalyzeAI` (this is a monorepo — Vercel needs to know where the actual app lives). Framework preset should auto-detect as Vite.
4. Under **Environment Variables**, add:
   - `VITE_API_BASE_URL` = the Render backend URL from step 1.4 (e.g. `https://multiagent-analyst-api.onrender.com`, no trailing slash)
5. Click **Deploy**. `vercel.json` in that folder already handles client-side routing (React Router) so refreshing on `/profile`, `/analyze/:jobId`, etc. won't 404.

## 3. Tighten CORS (final step)

Right now the backend accepts requests from any origin (`API_CORS_ORIGINS=*`) so step 2 could deploy without knowing the Vercel URL in advance. Once you have it:

1. Back in Render, open the `multiagent-analyst-api` service > **Environment**.
2. Set `API_CORS_ORIGINS` to your exact Vercel URL, e.g. `https://your-app.vercel.app` (comma-separate if you also want to keep `http://localhost:5173` for local dev against the deployed backend).
3. Save — this redeploys with the origin restricted.

## Redeploying after future pushes

Both platforms auto-deploy on push to `main` by default (Render via the Blueprint, Vercel via its GitHub integration) — no extra steps needed for routine updates.
