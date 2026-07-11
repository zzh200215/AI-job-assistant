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
docker compose -f docker-compose.prod.yml --profile tools run --rm migrate
docker compose -f docker-compose.prod.yml up -d
```

See `docs/db-migrations.md` for local Alembic commands and existing database guidance.

## Production Network Isolation

`docker-compose.prod.yml` is designed to minimize the exposed attack surface:

- The backend FastAPI container does **not** bind port `8000` on the host; it is only reachable from the `recruit-net` Docker network.
- MySQL does **not** expose port `3306` on the host; only containers on `recruit-net` can connect.
- The frontend nginx container is the single entry point (port `80`) and proxies `/api/*` and `/ws/*` to the backend.
- Uploads and the Chroma vector store use named Docker volumes and are never mounted to public host paths.

If you need external database access for administration, use a jump host, SSH tunnel, or a separate admin container on the same Docker network.

## Rate Limiting and Brute-Force Protection

The backend uses [slowapi](https://github.com/added-security/slowapi) for rate limiting. Default limits:

- General API endpoints: `100/minute`
- Authentication endpoints: `20/minute`
- Login / register / reset-password: `5/minute`

Configure via environment variables:

```bash
RATE_LIMIT_GENERAL=100/minute
RATE_LIMIT_AUTH=20/minute
RATE_LIMIT_LOGIN=5/minute
```

By default the limiter stores counters in memory. If `REDIS_URL` is configured, it automatically switches to Redis so limits are shared across multiple backend instances.

## Password Policy and Admin Accounts

User passwords must meet the following requirements:

- Minimum length of 8 characters.
- At least 3 of: uppercase letter, lowercase letter, digit, special character (`!@#$%^&*()_+-=[]{}|;:,.<>?`).
- OR at least 12 characters with 2 of the above categories.
- Must not be in the common weak-password blacklist.
- Must not match the username or the local part of the email address.

Create the first admin account with the CLI script:

```bash
cd backend
python scripts/create_admin.py \
  --username admin \
  --email admin@example.com \
  --password-env ADMIN_PASSWORD
```

Admin users have `role=admin` in the database and can access management endpoints such as `/auth/admin/users` and `/system/overview`. Public registration cannot create admin accounts.

## Backup and Recovery

Use the provided scripts to back up MySQL, uploaded files, and Chroma vector data:

```bash
# Manual backup
cd /path/to/project
python backend/scripts/backup.py

# Dry-run
python backend/scripts/backup.py --dry-run

# Cron example: daily at 02:00, keep 7 days
0 2 * * * /path/to/project/backend/scripts/backup.sh --keep 7
```

Restore from a backup directory:

```bash
# Review what will be restored
./backend/scripts/restore.sh backups/20260711_120000 --dry-run

# Perform the restore (requires typing YES)
./backend/scripts/restore.sh backups/20260711_120000
```

See `backend/scripts/backup_readme.md` for more details.

## Production Deployment Checklist

Before running `docker compose -f docker-compose.prod.yml up -d`, verify:

- [ ] You copied `.env.production.example` to `.env` and filled in real values.
- [ ] `MYSQL_PASSWORD` is strong and not one of the default/weak values.
- [ ] `JWT_SECRET` is at least 32 characters long and uniquely generated.
- [ ] `LLM_PROVIDER` and `EMBEDDING_PROVIDER` are explicitly set to real providers (not `mock`).
- [ ] `LLM_API_KEY` and `EMBEDDING_API_KEY` are populated.
- [ ] Alembic migrations have been run with the `migrate` profile.
- [ ] At least one admin account has been created with `backend/scripts/create_admin.py`.
- [ ] Rate-limit values are appropriate for your expected traffic.
- [ ] A backup strategy is in place (cron + off-site storage).
- [ ] HTTPS/TLS termination is handled by an outer reverse proxy or load balancer.

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

## Structured Logging

The backend supports both text and JSON log formats for better integration with log aggregation systems.

### Configuration

Set `STRUCTURED_LOGS=true` in your `.env` file to enable JSON-formatted logs:

```bash
STRUCTURED_LOGS=true
LOG_LEVEL=INFO
```

### Log Context

All log entries automatically include:
- `request_id`: Unique identifier for each HTTP request (from `X-Request-ID` header or auto-generated)
- `user_id`: Authenticated user ID (extracted from JWT token when present)

### Example Output

**Text format** (default):
```
2026-07-11 12:00:00,000 INFO app.main request_id=abc-123 user_id=42 Request completed method=GET path=/api/auth/me status=200 duration_ms=15.23
```

**JSON format** (`STRUCTURED_LOGS=true`):
```json
{
  "timestamp": "2026-07-11T12:00:00.000Z",
  "level": "INFO",
  "logger": "app.main",
  "message": "Request completed method=GET path=/api/auth/me status=200 duration_ms=15.23",
  "request_id": "abc-123",
  "user_id": "42"
}
```

### Dependencies

JSON logging requires `python-json-logger`:

```bash
pip install python-json-logger
```

If not installed, the system falls back to text format automatically.

## Prometheus Metrics

The backend exposes Prometheus metrics at `/api/system/metrics` for monitoring and alerting.

### Available Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `http_requests_total` | Counter | method, status, path | Total HTTP requests |
| `http_request_duration_seconds` | Histogram | method, path | HTTP request duration |
| `llm_requests_total` | Counter | provider, model | Total LLM API calls |
| `llm_request_duration_seconds` | Histogram | provider, model | LLM API call duration |
| `llm_errors_total` | Counter | provider, model, error_type | LLM API errors |
| `embedding_requests_total` | Counter | provider, model | Total embedding API calls |
| `embedding_texts_total` | Counter | provider, model | Total texts sent to embedding API |
| `embedding_errors_total` | Counter | provider, model, error_type | Embedding API errors |
| `sync_jobs_total` | Counter | source_type, status | Job data source sync jobs |
| `sync_job_duration_seconds` | Histogram | source_type | Sync job duration |
| `sync_errors_total` | Counter | source_type, error_type | Sync job errors |
| `auth_login_attempts_total` | Counter | status | Login attempts (success/failed) |
| `auth_rate_limited_total` | Counter | path | Rate-limited requests |

### Accessing Metrics

```bash
# From localhost
curl http://localhost:8000/api/system/metrics

# From Docker network
curl http://backend:8000/api/system/metrics
```

### Prometheus Configuration

Example `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'recruitment-platform'
    scrape_interval: 15s
    metrics_path: '/api/system/metrics'
    static_configs:
      - targets: ['backend:8000']
```

### Grafana Dashboards

Import the metrics into Grafana to visualize:
- API request rates and latency
- LLM/Embedding API usage and error rates
- Data source sync job success/failure rates
- Authentication attempt trends

## Data Source Sync Backoff

When job data source synchronization fails, the system implements exponential backoff to avoid overwhelming failing services:

- **Failure 1**: Wait `sync_interval` minutes
- **Failure 2**: Wait `sync_interval * 2` minutes
- **Failure 3**: Wait `sync_interval * 4` minutes
- **Failure N**: Wait `min(sync_interval * 2^(N-1), 1440)` minutes (max 24 hours)

After a successful sync, the failure counter resets and normal scheduling resumes.

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
