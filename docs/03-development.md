# Development workflow

This page describes a contributor-friendly local dev loop.

## Prereqs

- Python 3.12+
- Node 22+
- Docker + Docker Compose v2 (`docker compose`)
- `uv` (installed automatically by `make backend-sync` in CI; for local install see https://docs.astral.sh/uv/)

## Fast local loop (DB in Docker, apps on host)

1) Start Postgres (via compose)

```bash
cp .env.example .env
# Configure .env as needed (see root README for auth-mode notes)

docker compose -f compose.yml --env-file .env up -d db
```

2) Install deps

```bash
make setup
```

3) Apply DB migrations

```bash
make backend-migrate
```

4) Run backend (dev)

```bash
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

5) Run frontend (dev)

In another terminal:

```bash
cd frontend
npm run dev -- --hostname 0.0.0.0 --port 3000
```

Open:
- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/healthz

## Notes

- If you want the fully-containerized stack instead, see the root README’s compose instructions.
- If you add new env vars, prefer documenting them in `.env.example` and linking from docs rather than pasting secrets.
