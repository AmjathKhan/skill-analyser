# Slim single-container image for OpenShift Developer Sandbox / other PaaS.
# Serves the React SPA and FastAPI together. Uses SQLite + hash embeddings + NetworkX.
# Does not include Postgres, Redis, Neo4j, Celery, or PyTorch.

FROM node:20-alpine AS frontend

WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci || npm install
COPY frontend/ .
ENV VITE_API_BASE_URL=/api \
    NODE_OPTIONS=--max-old-space-size=3072
# Skip tsc in the image build to keep memory under OpenShift sandbox limits.
RUN npx vite build


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080 \
    FRONTEND_DIST=/app/frontend_dist \
    DATABASE_URL=sqlite:////tmp/skill_analyser.db \
    STORAGE_DIR=/tmp/storage \
    USE_CELERY=false \
    EMBEDDING_BACKEND=hash \
    VECTOR_BACKEND=numpy \
    GRAPH_BACKEND=networkx \
    LLM_BACKEND=template \
    ENVIRONMENT=production \
    DEBUG=false

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/ ./
COPY --from=frontend /ui/dist /app/frontend_dist

RUN sed -i 's/\r$//' /app/entrypoint.sh && \
    chmod +x /app/entrypoint.sh && \
    mkdir -p /tmp/storage /tmp/storage/resumes /app/.hf_cache && \
    chgrp -R 0 /app /tmp/storage && \
    chmod -R g=u /app /tmp/storage

EXPOSE 8080

# OpenShift assigns a random non-root UID; group 0 must be able to write.
USER 1001

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["api"]
