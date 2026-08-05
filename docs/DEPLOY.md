# Deploy CareOps (Render + Vercel)

Production layout:

```
Vercel (Next.js)  →  Render Web Service (FastAPI)
                           ↓
              Render Postgres + Render Redis + Qdrant Cloud
```

Deploy when you are ready for a live demo URL. Local dev stays unchanged (`docker compose up -d` + README quick start).

---

## Prerequisites

| Account | Purpose |
|---------|---------|
| [Render](https://render.com) | API, Postgres, Redis |
| [Vercel](https://vercel.com) | Next.js frontend |
| [Qdrant Cloud](https://cloud.qdrant.io) | Policy + complaint vectors (free tier) |
| [Groq](https://console.groq.com) + [Gemini](https://aistudio.google.com) | LLM + embeddings |

---

## 1. Qdrant Cloud

1. Create a free cluster.
2. Copy the cluster URL → `QDRANT_URL` (e.g. `https://xxxx.cloud.qdrant.io:6333`).
3. Note the API key if your cluster requires it (add to Render env as needed by your client config).

---

## 2. Render — databases

### PostgreSQL

1. **New → PostgreSQL** (free tier).
2. Name: `careops-postgres`, database: `careops`.
3. Copy **Internal Database URL** (use this on the web service in the same region).

### Redis

1. **New → Redis** (free tier).
2. Name: `careops-redis`.
3. Copy **Internal Redis URL**.

**Alternative:** use the repo blueprint — **New → Blueprint** → connect `shubhangini67/CareOps` → apply `render.yaml`, then fill in sync-false env vars in the dashboard.

---

## 3. Render — API web service

1. **New → Web Service** → connect GitHub repo `CareOps`.
2. Settings:

| Field | Value |
|-------|--------|
| **Root directory** | `apps/api` |
| **Runtime** | Python 3 |
| **Build command** | `pip install -r requirements-prod.txt` |
| **Start command** | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| **Health check path** | `/api/v1/health` |

3. **Environment variables** (minimum):

```bash
APP_ENV=production
APP_DEBUG=false
POSTGRES_URL=<Render internal Postgres URL>
REDIS_URL=<Render internal Redis URL>
QDRANT_URL=<Qdrant Cloud URL>
GROQ_API_KEY=<your key>
GEMINI_API_KEY=<your key>
JWT_SECRET_KEY=<openssl rand -hex 32>
CORS_ORIGINS=https://your-app.vercel.app
```

Set `CORS_ORIGINS` after Vercel gives you a URL (step 5). For preview deploys, comma-separate multiple origins.

4. Deploy. Note the public URL, e.g. `https://careops-api.onrender.com`.

### One-time seed (Render Shell)

Open the web service → **Shell**, then:

```bash
cd /opt/render/project/src
python scripts/seed_demo_data.py
python scripts/seed_hospital_data.py
python scripts/seed_qdrant_memory.py
python scripts/seed_hospital_policies.py
```

Adjust paths if Render’s working directory differs (`pwd` + `ls scripts/`).

Verify: `GET https://careops-api.onrender.com/api/v1/health/dependencies` — Postgres, Redis, Qdrant should report healthy.

---

## 4. Vercel — frontend

1. **Add New → Project** → import `shubhangini67/CareOps`.
2. Settings:

| Field | Value |
|-------|--------|
| **Root Directory** | `apps/web/careops-ui` |
| **Framework** | Next.js (auto-detected) |
| **Build command** | `npm run build` (default) |

3. **Environment variable:**

```bash
NEXT_PUBLIC_API_BASE_URL=https://careops-api.onrender.com
```

No trailing slash. Redeploy after changing this.

4. Deploy → copy URL (e.g. `https://careops.vercel.app`).

---

## 5. Wire CORS + GitHub About

1. Render → `careops-api` → Environment → update:

```bash
CORS_ORIGINS=https://careops.vercel.app
```

2. GitHub repo **About** → Website → paste your Vercel URL (see `docs/GITHUB_SETUP.md`).

3. Smoke test:
   - Open Vercel URL → register a facility → **Scenario Planner** → run `ed_surge`.
   - Confirm streaming planning works (Render free tier may cold-start ~30s on first request).

---

## Env reference

| Variable | Where | Notes |
|----------|-------|-------|
| `NEXT_PUBLIC_API_BASE_URL` | Vercel | Public Render API URL |
| `CORS_ORIGINS` | Render | Must include Vercel origin |
| `JWT_SECRET_KEY` | Render | Required in production |
| `POSTGRES_URL` | Render | Internal URL preferred |
| `REDIS_URL` | Render | Internal URL preferred |
| `QDRANT_URL` | Render | Qdrant Cloud cluster URL |
| `GROQ_API_KEY`, `GEMINI_API_KEY` | Render | Required for planning + RAG |

Optional: `SENTRY_DSN`, Langfuse/LangSmith keys — leave blank for a minimal demo.

---

## Free-tier notes

- **Render web** sleeps after ~15 min idle; first request wakes the service (plan for demo latency).
- **Render Postgres** expires after 90 days on free tier — fine for interviews; upgrade or re-seed for long-lived demos.
- **Prophet** (forecast node) adds build time and memory; if the free instance OOMs, upgrade to Starter or disable heavy scenarios in demo.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| CORS error in browser | Add exact Vercel origin to `CORS_ORIGINS` on Render |
| 401 after login | Same `JWT_SECRET_KEY` across redeploys; clear site cookies |
| Empty policy citations | Re-run Qdrant seed scripts against production `QDRANT_URL` |
| API 502 on first load | Render cold start — retry after ~30s |
| Frontend calls localhost | Redeploy Vercel with `NEXT_PUBLIC_API_BASE_URL` set |

---

## Local vs production

| | Local | Production |
|---|-------|------------|
| Postgres / Redis / Qdrant | `docker compose up -d` | Render + Qdrant Cloud |
| API | `uvicorn … --port 8000` | Render web service |
| UI | `npm run dev` | Vercel |
| Seeds | Run from repo root | Render Shell once |
