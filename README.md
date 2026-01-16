# TruthSig Phase 2 — Next.js + Tailwind + shadcn UI (Render-ready)

This repo includes:
- **FastAPI backend** (provenance + metadata + PDF report)
- **Next.js web UI** (Tailwind + shadcn-style components)

## Deploy on Render (Free) using Blueprint
1) Push this repo to GitHub.
2) Render Dashboard → **New +** → **Blueprint** → select your repo → **Apply**.
3) Render deploys:
   - `truthsig-api`
   - `truthsig-web`
## IMPORTANT: set Web → API URL
After API deploys:
1) Open `truthsig-api` → copy its public URL.
2) Render → `truthsig-web` → Environment:
   - `NEXT_PUBLIC_API_URL` = your API URL
3) Redeploy `truthsig-web`.

## Local run (optional)
Backend:
```bash
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Web:
```bash
cd web
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Open http://localhost:3000

## Production readiness
Before deploying to production, set required environment variables and harden defaults:
- `TRUTHSIG_ENV=production`
- `JWT_SECRET` (must not be `dev-secret-change-me`)
- `TRUTHSIG_ADMIN_API_KEY`
- `CORS_ORIGINS` (explicit list, no wildcard)
- `TRUSTED_HOSTS` (explicit list for your domains)

See `.env.example` for a full list of configuration knobs.

## YC readiness
This repo includes a YC readiness checklist and wedge-focused execution plan in
`docs/YC_READY_CHECKLIST.md`.