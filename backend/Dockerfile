# ── Build stage: dependencies, including gssapi (Kerberos SSO), which has no
# Linux wheels and is compiled here against MIT Kerberos.
FROM python:3.12-slim AS build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libkrb5-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app
# Same locked dependency versions as local development (uv.lock), without the
# dev group, plus the `sso` extra.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --extra sso

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# libgssapi-krb5-2: Kerberos SSO. tesseract-ocr + spa/eng: OCR of scanned PDFs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates tzdata libgssapi-krb5-2 \
       tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/venv /opt/venv
COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

# Run as an unprivileged user.
RUN useradd --system --uid 10001 --no-create-home corplib
USER corplib

EXPOSE 8000

# The same image runs the API (default) and the worker (`python -m app.worker`).
# The API applies database migrations before starting.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
