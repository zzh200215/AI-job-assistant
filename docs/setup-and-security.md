# Setup And Security Notes

Last updated: 2026-06-10

## Environment

1. Copy `backend/.env.example` to `backend/.env`.
2. Fill in real values for:
   - `MYSQL_PASSWORD`
   - `JWT_SECRET`
   - `LLM_*`
   - `EMBEDDING_*`
3. Do not commit `backend/.env`.

## Key Config Flags

- `APP_ENV`
  - `development` by default.
  - Set to `production` for production deployments.
- `APP_DEBUG`
  - Defaults to `False` in code.
  - Must remain `False` when `APP_ENV=production`.
- `JWT_ACCESS_TOKEN_EXPIRE_DAYS`
  - Controls access-token lifetime in days.
  - Default is `7`.

## Production Safety Checks

When `APP_ENV=production`, startup validation now rejects unsafe defaults:

- `APP_DEBUG=True`
- default `JWT_SECRET`
- weak or empty `MYSQL_PASSWORD`
- `JWT_SECRET` shorter than 32 characters

These checks live in `backend/app/core/config.py`.

Production deployments should run database migrations before starting the backend:

```bash
APP_ENV=production AUTO_CREATE_TABLES=false docker compose --profile tools run --rm migrate
APP_ENV=production AUTO_CREATE_TABLES=false docker compose up -d backend frontend
```

See `docs/db-migrations.md` for local Alembic commands and existing database guidance.

## Authenticated File Access

Uploaded/exported files are no longer exposed by a public static `/uploads` mount.

Current download flows require authentication and ownership checks:

- `GET /api/resume/{resume_id}/download`
- `GET /api/knowledge/{doc_id}/download`

This means links should be opened through the frontend request flow, not by assuming a public file path.

## Public JD Semantics

The project now treats `JobDescription.user_id = null` as a public JD.

Public JDs can be used in these flows:

- analysis
- interview session creation
- job recommendation
- job pipeline creation
- legacy agent and multi-agent entrypoints
- resume optimization target JD
- JD detail read

Private JDs remain isolated to their owner.

## Intentional JD API Behavior

- `GET /api/jd/{id}` can return an owned JD or a public JD.
- `GET /api/jd/list` remains owner-scoped.

This keeps "My JD list" behavior stable while allowing shared/public JDs to participate in downstream flows.

## Recommended Local Startup

Backend:

```bash
cd backend
copy .env.example .env
python -m uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```
