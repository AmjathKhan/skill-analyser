# AI Skill Analyser — Graph RAG HR Recruitment Platform

Upload resumes, extract candidate data with AI, normalize every skill against an authoritative Skills
Knowledge Base, and rank candidates with an **explainable Graph RAG** engine that walks a knowledge graph
of candidates, skills, technologies, companies, certifications and job roles.

```
PDF / DOC / DOCX  ─▶  parse  ─▶  extract entities  ─▶  normalize skills  ─▶  embed  ─▶  knowledge graph
                                                                                          │
                       search · skill match · gap analysis · reports  ◀───  Graph RAG  ◀──┘
```

- **Backend** — FastAPI, PostgreSQL + pgvector, Redis, Celery, Neo4j or NetworkX, SQLAlchemy 2, Alembic
- **Frontend** — React 18, TypeScript, Vite, Material UI, TanStack Query, Recharts, force-directed graph
- **AI** — rule-based + spaCy extraction, sentence-transformers or deterministic hash embeddings,
  pgvector / FAISS / NumPy vector search, template or OpenAI reasoning

Every AI dependency has an **offline fallback**, so the whole platform runs with no model downloads,
no API keys and no GPU. Turn the heavy backends on with environment variables when you want them.

---

## Table of contents

1. [Quick start with Docker](#quick-start-with-docker)
2. [Local development](#local-development)
3. [Default accounts](#default-accounts)
4. [Configuration](#configuration)
5. [Skills Knowledge Base](#skills-knowledge-base)
6. [How the Graph RAG pipeline works](#how-the-graph-rag-pipeline-works)
7. [Scoring model](#scoring-model)
8. [REST API](#rest-api)
9. [Frontend pages](#frontend-pages)
10. [Testing and quality gates](#testing-and-quality-gates)
11. [Project layout](#project-layout)
12. [Deployment](#deployment)
13. [Troubleshooting](#troubleshooting)

---

## Quick start with Docker

```bash
cp .env.example .env          # adjust SECRET_KEY at minimum
docker compose up -d --build
docker compose exec backend python -m scripts.seed --all
```

| Service | URL | Notes |
| --- | --- | --- |
| Frontend | http://localhost:8080 | nginx serving the built SPA, proxies `/api` |
| API docs | http://localhost:8000/docs | Swagger UI (disabled when `ENVIRONMENT=production`) |
| API health | http://localhost:8000/api/health | Reports every backend it resolved |
| Neo4j browser | http://localhost:7474 | `neo4j` / value of `NEO4J_PASSWORD` |

`docker compose up` starts PostgreSQL (with pgvector), Redis, Neo4j, the API, a Celery worker and the
frontend. The API container runs migrations on boot; `scripts.seed --all` imports the skills CSV,
creates the users, adds two demo job requirements, ingests the five sample resumes and builds the graph.

Verify a deployment end to end at any time:

```bash
docker compose exec backend python scripts/smoke_api.py http://localhost:8000
```

## Local development

Requirements: Python 3.11+, Node 20+, and PostgreSQL 15+ (or use SQLite for a quick spin).

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows;  source .venv/bin/activate on Linux/macOS
pip install -r requirements-dev.txt
pip install -r requirements-ai.txt  # optional: spaCy, transformers, torch, FAISS, OCR

alembic upgrade head
python -m scripts.seed --all
uvicorn app.main:app --reload
```

To run without PostgreSQL, point the app at SQLite — everything except pgvector search works:

```bash
set DATABASE_URL=sqlite:///./local.db     # export DATABASE_URL=... on Linux/macOS
set VECTOR_BACKEND=numpy
set GRAPH_BACKEND=networkx
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to http://localhost:8000
```

`npm run build` type-checks and produces `dist/`; `npm run typecheck` runs `tsc --noEmit` alone.

## Default accounts

Created by `python -m scripts.seed --users` (change them before any real deployment):

| Role | Email | Password | Can do |
| --- | --- | --- | --- |
| HR Admin | `admin@skillanalyser.ai` | `Admin@12345` | Everything, including users, audit and the skills KB |
| Recruiter | `recruiter@skillanalyser.ai` | `Recruiter#2024` | Upload, edit candidates, match, search, report |
| Hiring Manager | `manager@skillanalyser.ai` | `Manager#2024` | Read candidates, match, search, report |

Roles are enforced by a permission matrix in `backend/app/core/constants.py` and applied as FastAPI
dependencies (`require_permission("candidate:write")`), so the UI and the API cannot drift apart.

## Configuration

All settings live in `.env` (see `.env.example` for the annotated list). The switches that matter most:

| Variable | Values | Effect |
| --- | --- | --- |
| `EMBEDDING_BACKEND` | `hash` · `sentence-transformers` | `hash` is deterministic and offline; the transformer backend gives real semantics |
| `VECTOR_BACKEND` | `numpy` · `faiss` · `pgvector` | Where similarity search runs |
| `GRAPH_BACKEND` | `networkx` · `neo4j` | In-process graph vs. a real graph database |
| `LLM_BACKEND` | `template` · `openai` | Deterministic explanations vs. LLM-written narratives |
| `USE_CELERY` | `false` · `true` | Inline background tasks vs. a Celery worker |
| `ENABLE_OCR` | `false` · `true` | Tesseract fallback for scanned PDFs |
| `FILE_ENCRYPTION_ENABLED` | `false` · `true` | Fernet encryption of stored resumes at rest |

If a preferred backend is unavailable at runtime (no FAISS wheel, Neo4j down, no API key), the app logs
a warning and falls back instead of failing. `GET /api/health` always reports what is actually in use.

## Skills Knowledge Base

`backend/data/skills.csv` is the authoritative taxonomy — 145 skills across programming languages,
frameworks, databases, cloud, DevOps, data, AI/ML and soft skills:

```csv
skill_id,skill_name,category,parent_skill,related_skills,technology_stack,job_role,experience_level,skill_synonyms,skill_description
SK001,Python,Programming Language,,Django;Flask;FastAPI;Pandas,Backend,Backend Developer;Data Engineer,intermediate,Python3;CPython;Py,General purpose language…
```

The importer turns each row into a `Skill` plus `SkillSynonym` and `SkillRelation` records, and the
in-memory `SkillTaxonomy` resolves raw resume phrases through four strategies, in order:

1. **Exact** match on the normalized name (`Node.js` → `nodejs`)
2. **Synonym** match (`K8s` → `Kubernetes`, `RN` → `React Native`)
3. **Fuzzy** match above a similarity threshold (`Kubernetess` → `Kubernetes`, confidence < 1.0)
4. **Graph expansion** — parent, child and related skills reached through the taxonomy

Replace the CSV and re-import from the UI (Skills page → *Upload CSV*) or the API
(`POST /api/skills/import/upload`); nothing else needs to change.

## How the Graph RAG pipeline works

**1. Ingest.** `pdfplumber` → PyMuPDF → `python-docx` → LibreOffice/antiword → binary scrape, with an
optional Tesseract OCR pass. Files are checksummed, so re-uploading the same resume is detected as a
duplicate rather than creating a second candidate.

**2. Extract.** Regex and heuristics (optionally spaCy NER) pull out personal details, work history with
date ranges, education, projects, certifications and skill mentions, then compute total experience from
merged, de-overlapped employment intervals.

**3. Normalize.** Every raw skill phrase is resolved against the taxonomy, keeping the match type,
confidence and the evidence sentence — that provenance is what makes the final score explainable.

**4. Build the graph.** Nodes: `Candidate`, `Skill`, `Category`, `Technology`, `JobRole`, `Company`,
`Project`, `Certification`, `Education`. Edges: `HAS_SKILL`, `WORKED_AT`, `USED_SKILL`, `COMPLETED`,
`HOLDS`, `STUDIED_AT`, `BELONGS_TO`, `PART_OF`, `RELATED_TO`, `PARENT_OF`, `DEPENDS_ON`, `REQUIRED_FOR`.
The five sample resumes produce roughly 356 nodes and 1 351 edges.

**5. Embed.** Candidate profiles, resume chunks and skill descriptions are embedded and stored for
cosine search through pgvector, FAISS or NumPy.

**6. Retrieve and rank.** A query is parsed into skills plus constraints, expanded through the graph,
fused with vector hits, filtered in SQL, scored, and finally explained.

## Scoring model

`overall = 0.40·skill + 0.20·semantic + 0.20·experience + 0.10·certification + 0.10·project`

Weights are configurable per request (the Skill Match page exposes sliders) and via `MATCH_WEIGHT_*`.
Skill credit degrades with match quality — exact 1.0, synonym 0.95, fuzzy ~0.8, related/parent/child
0.55–0.85, graph-only 0.5 — and a missing **mandatory** skill caps the candidate regardless of the rest.
Each result carries the component breakdown, matched/related/missing skills with the graph path that
justified them, strengths, gaps, suggested interview questions and a recommendation band
(Highly Recommended ≥ 85, Recommended ≥ 70, Consider ≥ 55, Not Recommended below).

## REST API

Base path `/api`. Interactive docs at `/docs`, OpenAPI JSON at `/openapi.json`.

| Area | Endpoints |
| --- | --- |
| Auth | `POST /login` · `POST /refresh` · `POST /logout` · `GET /me` · `GET /me/sessions` · `POST /forgot-password` · `POST /reset-password` · `POST /change-password` |
| Users & audit | `GET/POST /users` · `GET/PUT/DELETE /users/{id}` · `GET /users/audit/logs` |
| Resumes | `POST /upload` · `GET /resumes` · `GET /resume/{id}` · `GET /resume/{id}/status` · `GET /resume/{id}/download` · `POST /resume/{id}/reprocess` · `DELETE /resume/{id}` |
| Candidates | `GET /candidates` · `GET/PUT/DELETE /candidate/{id}` · `PATCH /candidate/{id}/status` · `POST /candidate/{id}/notes` · `POST /candidate/{id}/score` · `GET /candidate/{id}/similar` |
| Matching | `POST /skill-match` · `GET /skill-match/runs` · `GET /skill-match/runs/{id}` · `POST /skill-match/gap-analysis` |
| Search | `POST /search` · `GET /search/suggest` |
| Graph | `POST /graph/build` · `GET /graph/stats` · `GET /graph/overview` · `GET /graph/candidate/{id}` · `GET /graph/skill/{name}` · `GET /graph/skills` |
| Skills KB | `GET /skills` · `GET /skills/categories` · `GET /skills/stats` · `POST /skills/import` · `POST /skills/import/upload` |
| Jobs | `GET/POST /job-requirements` · `GET/PUT/DELETE /job-requirements/{id}` |
| Analytics | `GET /dashboard` · `GET /reports` · `GET /reports/export?format=pdf\|csv\|excel` · `GET /reports/candidates/export` |
| System | `GET /health` · `GET /system/info` |

Example — rank candidates for a role:

```bash
curl -X POST http://localhost:8000/api/skill-match \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"required_skills":["Python","FastAPI","PostgreSQL","Docker"],
       "mandatory_skills":["Python"],
       "preferred_skills":["AWS","Kubernetes"],
       "min_experience_years":5,
       "top_k":10}'
```

## Frontend pages

| Route | Page | Highlights |
| --- | --- | --- |
| `/login`, `/forgot-password` | Authentication | JWT login, remember me, password reset |
| `/dashboard` | Dashboard | Cards, hiring trends, skill and technology charts, recent activity, AI recommendations |
| `/upload` | Upload | Drag & drop batch upload with per-file parse results and duplicate detection |
| `/candidates` | Candidate list | Server-side paged data grid, skill/status/experience/location filters, CSV export |
| `/candidates/:id` | Candidate profile | AI summary, grouped skills with evidence, timeline, education, projects, notes, similar candidates, personal subgraph, resume download |
| `/skill-match` | AI skill match | Criteria builder, live weight sliders, ranked results with full score breakdown and graph evidence |
| `/search` | Search | Natural language query across hybrid / semantic / keyword / graph / skill modes with a RAG answer |
| `/graph` | Knowledge graph | Interactive force-directed graph, skill focus, depth control, node and relation statistics, rebuild |
| `/skills` | Skills KB | Taxonomy browser by category with synonyms and relations, CSV re-import |
| `/jobs` | Job requirements | CRUD for reusable role definitions that feed the matcher |
| `/reports` | Reports | KPIs, pipeline, trends, gap analysis, PDF/CSV/Excel export |
| `/users` | Users & audit | Account management, roles, activation, full audit trail |
| `/settings` | Settings | Profile, permissions, password change, sessions, live platform status |

Light and dark themes, responsive layout down to mobile, and permission-aware navigation throughout.

## Testing and quality gates

```bash
cd backend
python -m pytest                       # 138 unit + integration tests
python -m pytest --cov=app             # with coverage
python -m ruff check app scripts tests # lint
python -m mypy app                     # types

cd ../frontend
npm run typecheck
npm run build
```

The backend suite spins up an isolated SQLite database, seeds users, uploads the five sample resumes
through the real HTTP API and then exercises parsing, taxonomy resolution, embeddings, graph traversal,
matching, search, dashboards, reports and RBAC — no external services required.

## Project layout

```
backend/
  app/
    ai/            document parsing, extraction, embeddings, vector store, Graph RAG, reasoning
    api/v1/        FastAPI routers, one module per domain
    core/          settings, security, RBAC, logging, rate limiting, exceptions
    db/            SQLAlchemy base and session management
    graph/         graph interface, NetworkX and Neo4j backends, knowledge graph builder
    models/        ORM models
    repositories/  query layer
    schemas/       Pydantic request/response contracts
    services/      business logic (auth, resumes, candidates, matching, search, reports, graph)
    workers/       Celery app and tasks
  alembic/         migrations
  data/            skills.csv and sample resumes
  scripts/         seed.py, smoke_api.py, generate_sample_resumes.py
  tests/           pytest suite
frontend/
  src/
    api/           axios client with token refresh, typed endpoint functions
    auth/          authentication context
    components/    layout, shared UI, graph canvas
    pages/         one file per route
docker-compose.yml
```

## Deployment

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for production hardening, scaling the worker pool,
switching to Neo4j and pgvector, backups and observability.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `skills_loaded: 0` in `/api/health` | The taxonomy was never imported — run `python -m scripts.seed --skills` |
| Resume parses but no skills are matched | Same cause: skills are normalized against the taxonomy, so import the CSV first |
| Upload succeeds but the text is empty | Scanned PDF — set `ENABLE_OCR=true` and install Tesseract |
| Graph endpoints return zero nodes | Run `POST /api/graph/build` (or the *Rebuild graph* button); it also happens automatically at startup |
| `sentence-transformers` model download fails | Keep `EMBEDDING_BACKEND=hash`; matching still works, only semantic nuance is reduced |
| Neo4j connection errors | The app falls back to NetworkX automatically; check `NEO4J_*` values in `.env` |
| 429 responses during bulk upload | Rate limiting — raise `RATE_LIMIT_REQUESTS` or set `RATE_LIMIT_ENABLED=false` in development |
