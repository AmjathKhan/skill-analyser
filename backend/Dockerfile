FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System packages: build tools for wheels, poppler/tesseract for document + OCR support
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libpq5 \
        poppler-utils \
        tesseract-ocr \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG INSTALL_AI_EXTRAS=true

COPY requirements.txt requirements-ai.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    if [ "$INSTALL_AI_EXTRAS" = "true" ]; then \
        pip install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-ai.txt && \
        python -m spacy download en_core_web_sm ; \
    fi

COPY . .

RUN chmod +x /app/entrypoint.sh && \
    mkdir -p /app/storage /app/.hf_cache && \
    adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["api"]
