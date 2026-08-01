# Setup Guide

Prerequisites: Python 3.11+, Node.js 20+, Docker + Docker Compose.

## 1. Environment templates

```bash
cp .env.example .env                    # root (docker compose)
cp backend/.env.example backend/.env    # backend (uvicorn)
cp frontend/.env.example frontend/.env.local   # frontend (Next.js)
```

Or run the setup script (creates env files from templates + storage dirs):

```bash
scripts/setup/setup-dev.ps1   # Windows PowerShell
scripts/setup/setup-dev.sh    # Linux / macOS / WSL
```

Edit the copied files with real values (see comments inside).

## 2. Start infrastructure

```bash
docker compose up -d postgres n8n
```

- Postgres: `localhost:5432`
- n8n UI: `http://localhost:5678` (default creds from `.env`)

## 3. Backend

```bash
cd backend
python -m venv .venv
# activate (Windows: .venv\Scripts\activate | Unix: source .venv/bin/activate)
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs: `http://localhost:8000/docs`.

## 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

App: `http://localhost:3000`.

## 5. Verify

```bash
curl http://localhost:8000/api/v1/health   # {"status":"ok",...}
```

## 6. Migrations & seeds

```bash
make migrate    # alembic upgrade head
make seed       # database/seeds
```

## Troubleshooting

- Port conflicts: override `POSTGRES_PORT`, `N8N_PORT`, `BACKEND_PORT` in `.env`.
- `supabase` import error: verify `SUPABASE_URL`/keys in `backend/.env` or leave
  blank until the Supabase project is provisioned (health endpoint doesn't need it).
