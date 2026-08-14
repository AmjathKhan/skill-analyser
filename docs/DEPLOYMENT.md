# Deployment guide

This covers running the AI Skill Analyser beyond a laptop: hardening, scaling, the heavier AI backends,
backups and observability. For a first run see the [README](../README.md).

## 1. Architecture in production

```
                    ┌────────────┐
   users  ───────▶  │  nginx /   │ ──── static SPA (frontend container)
                    │  ingress   │ ──── /api ──▶ FastAPI (2+ replicas, gunicorn/uvicorn workers)
                    └────────────┘                    │
                                                      ├──▶ PostgreSQL 16 + pgvector   (candidates, skills, embeddings)
                                                      ├──▶ Redis                      (rate limits, Celery broker, cache)
                                                      ├──▶ Neo4j 5                    (knowledge graph)
                                                      └──▶ object storage / volume    (resume files)
                                                      
   Celery workers (N replicas) ──▶ same PostgreSQL / Redis / Neo4j / storage
```

The API is stateless apart from the file volume, so it scales horizontally. Two things must be shared
between replicas in production:

- **Rate limiting** — set `REDIS_URL`, otherwise each replica keeps its own in-memory window.
- **The graph** — set `GRAPH_BACKEND=neo4j`. NetworkX lives inside a single process, so with more than
  one replica each would hold a private copy and rebuilds would not propagate.

## 2. Production environment

Start from `.env.example` and change at least these:

```bash
ENVIRONMENT=production
DEBUG=false                    # also disables /docs and /redoc
SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(64))")

POSTGRES_HOST=...              # managed PostgreSQL with pgvector enabled
POSTGRES_PASSWORD=...          # from your secret manager, never committed
REDIS_URL=redis://:password@redis:6379/0

BACKEND_CORS_ORIGINS=https://recruiting.example.com

GRAPH_BACKEND=neo4j
NEO4J_URI=bolt://neo4j:7687
NEO4J_PASSWORD=...

VECTOR_BACKEND=pgvector
EMBEDDING_BACKEND=sentence-transformers
USE_CELERY=true

FILE_ENCRYPTION_ENABLED=true
FILE_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

FIRST_SUPERUSER_EMAIL=hr.admin@example.com
FIRST_SUPERUSER_PASSWORD=...   # rotate immediately after the first login
```

Losing `FILE_ENCRYPTION_KEY` makes stored resumes unreadable — treat it like a database credential and
back it up in your secret manager.

## 3. Build and run

```bash
docker compose --env-file .env.production up -d --build
docker compose exec backend python -m scripts.seed --skills --users
docker compose exec backend python scripts/smoke_api.py http://localhost:8000
```

Migrations run automatically from `entrypoint.sh` before the API starts. To run them explicitly:

```bash
docker compose exec backend alembic upgrade head
```

Scale the pieces independently:

```bash
docker compose up -d --scale worker=4 --scale backend=3
```

The frontend image bakes `VITE_API_BASE_URL` in at build time. Keep the default `/api` and let nginx
proxy to the API, or rebuild the image when the API moves to a different origin.

## 3b. OVHcloud Public Cloud

This repo cannot create an OVH instance by itself (that needs your OVH account). Once you have an
Ubuntu 24.04 Public Cloud VM (4 vCPU / 8 GB RAM or more, SSH key added, ports 22/80/443 open):

**From this Windows PC**, after you know the instance IPv4:

```powershell
powershell -File deploy\ovh\push.ps1 -Server YOUR_OVH_IP -User ubuntu
```

That packs the project, copies it over SSH, installs Docker if needed, and starts:

`docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production`

The production overlay keeps Postgres, Redis, Neo4j and the API off the public internet. Caddy
listens on 80/443 and proxies to the frontend. First boot uses `SITE_ADDRESS=:80`, so the URL is:

`http://YOUR_OVH_IP`

Sign in with `FIRST_SUPERUSER_EMAIL` / `FIRST_SUPERUSER_PASSWORD` from `.env.production` on the VM,
then change the password.

**With a domain:** create an A record to the VM IP, then on the VM edit `.env.production`:

```bash
SITE_ADDRESS=skills.yourdomain.com
ACME_EMAIL=you@yourdomain.com
BACKEND_CORS_ORIGINS=https://skills.yourdomain.com
```

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d --build caddy frontend
```

Caddy will obtain a Let's Encrypt certificate. The public URL is then `https://skills.yourdomain.com`.

**Manual path** (already SSH'd into the VM):

```bash
# copy the repo onto the VM first, then:
chmod +x deploy/ovh/bootstrap.sh
bash deploy/ovh/bootstrap.sh
```

## 4. Enabling the heavy AI stack

The default image installs the AI extras (`INSTALL_AI_EXTRAS=true`), which adds roughly 2 GB for torch,
transformers, spaCy and FAISS. Set `INSTALL_AI_EXTRAS=false` for a slim image that uses the hash
embedder and rule-based extraction.

With extras installed, switch the backends on:

| Feature | Setting | Extra requirement |
| --- | --- | --- |
| Semantic embeddings | `EMBEDDING_BACKEND=sentence-transformers` | ~90 MB model download, cached in the `hf_cache` volume |
| spaCy NER | `SPACY_MODEL=en_core_web_sm` | `python -m spacy download en_core_web_sm` |
| OCR for scanned PDFs | `ENABLE_OCR=true` | `tesseract-ocr` package (already in the backend image) |
| LLM narratives | `LLM_BACKEND=openai`, `OPENAI_API_KEY=...` | Outbound network access |

Changing the embedding backend or dimension invalidates stored vectors. Re-index afterwards:

```bash
docker compose exec backend python -c "from app.workers.tasks import reindex_vectors_task; reindex_vectors_task()"
```

### pgvector

The compose file uses the `pgvector/pgvector` image and the app creates the extension on startup. On a
managed database, enable it once by hand:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

### Neo4j

Point `NEO4J_*` at the server and rebuild the graph once after switching backends:

```bash
curl -X POST https://api.example.com/api/graph/build -H "Authorization: Bearer $TOKEN" -d '{"clear":true}'
```

## 5. Security checklist

- [ ] `SECRET_KEY` is random per environment and stored in a secret manager
- [ ] `DEBUG=false` and `ENVIRONMENT=production` (Swagger and tracebacks are off)
- [ ] TLS terminated at the ingress; HSTS enabled
- [ ] `BACKEND_CORS_ORIGINS` lists only your real front-end origins
- [ ] Bootstrap admin password rotated; demo accounts removed
- [ ] `RATE_LIMIT_ENABLED=true` with Redis so limits are shared across replicas
- [ ] `FILE_ENCRYPTION_ENABLED=true` with a backed-up key
- [ ] Database and Redis reachable only from the application network
- [ ] Audit log retention agreed with your compliance team (`audit_logs` grows with usage)

Passwords are hashed with bcrypt, access tokens are short-lived JWTs paired with revocable refresh
sessions, uploads are validated by extension, size and content sniffing, and every mutating action is
written to `audit_logs` with the actor, IP and user agent.

## 6. Backups and recovery

| What | How | Frequency |
| --- | --- | --- |
| PostgreSQL | `pg_dump -Fc` (holds candidates, skills, embeddings, audit) | Daily + WAL archiving |
| Resume files | Snapshot the `resume_storage` volume or sync the bucket | Daily |
| Encryption key | Secret manager backup | On change |
| Neo4j | `neo4j-admin database dump` — or skip it, the graph is rebuildable | Weekly |

Recovery order: restore PostgreSQL → restore the file volume → `alembic upgrade head` →
`POST /api/graph/build` to regenerate the graph → run `scripts/smoke_api.py` to verify.

## 7. Observability

- **Health** — `GET /api/health` returns database connectivity plus the resolved graph, vector,
  embedding and LLM backends. Use it as the liveness and readiness probe (the compose file already does).
- **Logs** — structured lines with a per-request id (`rid=`) that is also returned in the
  `X-Request-ID` response header, so a user-reported error maps to exact log lines.
- **Timing** — every response carries `X-Process-Time-Ms`; slow requests are logged with their duration.
- **Audit** — `GET /api/users/audit/logs` (HR Admin) or the Users & audit page.

Suggested alerts: health endpoint failing, resume `failed` count rising, Celery queue depth growing,
p95 latency on `/api/skill-match`, and disk usage on the resume volume.

## 8. Operational tasks

```bash
# Re-import the skills taxonomy after editing the CSV
docker compose exec backend python -m scripts.seed --skills

# Rebuild the knowledge graph
docker compose exec backend python -c "from app.workers.tasks import rebuild_graph_task; rebuild_graph_task()"

# Re-embed every candidate (after changing the embedding backend)
docker compose exec backend python -c "from app.workers.tasks import rebuild_candidate_embeddings_task; rebuild_candidate_embeddings_task()"

# Reprocess a resume that failed to parse
curl -X POST https://api.example.com/api/resume/42/reprocess -H "Authorization: Bearer $TOKEN"
```

Celery Beat schedules a nightly graph rebuild and vector re-index; adjust the schedule in
`backend/app/workers/celery_app.py`.

## 9. Upgrades

1. Back up PostgreSQL and the resume volume.
2. Pull the new images and run `alembic upgrade head`.
3. Restart the API and workers (rolling restart is safe — the API is stateless).
4. Rebuild the graph if the release notes mention graph schema changes.
5. Run `scripts/smoke_api.py` against the upgraded environment.
