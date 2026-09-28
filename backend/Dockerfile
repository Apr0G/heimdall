# syntax=docker/dockerfile:1.7
# Backend image for Amazon ECS Express Mode. Built by GitHub Actions and pushed
# to ECR (no local Docker needed). Runs uvicorn on 8080; health at /healthz.
# Pinned by digest so the OS/interpreter layer is the same on every build of a
# commit. Bump deliberately: `docker buildx imagetools inspect python:3.11-slim`.
#
# TWO STAGES, TWO TAGS. `api` is the service image (:latest). `deid` is built
# FROM it and adds the de-identification stack — Presidio, torch, the clinical
# transformer weights — for the corpus export / promote tasks (:deid). The
# service never carries a gigabyte of NLP dependencies; the export never installs
# anything at runtime. deploy-backend.yml builds both with --target.
FROM python:3.11-slim@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7 AS api

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies come from the hash-pinned lock (uv pip compile, py3.11/linux), so
# two builds of one commit install byte-identical wheels and a compromised or
# yanked release can't slip in at build time. --no-deps + --require-hashes
# means nothing outside the lock is ever resolved. Dependabot bumps the lock.
COPY requirements.lock ./
RUN pip install --require-hashes --no-deps --only-binary=:all: -r requirements.lock

# Then the application itself, with its deps already satisfied.
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install --no-deps .

# AWS RDS CA bundle for optional verify-full DB TLS (enable via DB_SSL_CA_BUNDLE).
# `ADD` fetches remote files as mode 0600 owned by root; the non-root appuser (set
# below) loads this at import time in db/session.py, so make the (public) CA bundle
# world-readable — otherwise startup dies with PermissionError and ECS rolls back.
# Checksum-verified: this file is the verify-full trust anchor for DB TLS, so a
# substituted download must fail the build, not silently trust a foreign CA.
# Refresh the hash when AWS rotates the bundle (the build will tell you).
ADD --checksum=sha256:e5bb2084ccf45087bda1c9bffdea0eb15ee67f0b91646106e466714f9de3c7e3 \
    https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem /app/rds-ca.pem
RUN chmod 0644 /app/rds-ca.pem

# Run as a non-root user (least privilege). The app writes nothing to disk (S3 +
# DB only) and listens on 8080 (>1024), so no root is needed.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080
# --no-server-header: don't advertise the uvicorn version (matches the header
# posture in app/core/security_headers.py).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]


# =============================================================================
# deid: the corpus export / promote task image. Everything the two PHI detectors
# need is baked here, hash-verified, and the task runs with the Hugging Face
# hub OFFLINE — the container holding DATABASE_URL and the export role never
# resolves a package or fetches a model at runtime.
# =============================================================================
FROM api AS deid
USER root

# Presidio + spaCy models + torch (CPU) + transformers, the whole transitive
# closure hash-pinned in deid.lock (see its header for how it is regenerated).
# Shared pins are asserted equal to requirements.lock by
# tests/test_dependency_locks.py so nothing here downgrades the audited image.
COPY deid.lock deid-model.json ./
RUN pip install --require-hashes --no-deps --only-binary=:all: --disable-pip-version-check \
    -r deid.lock

# The clinical transformer at its pinned revision, into an image-local cache.
# Only the files the manifest names are fetched; then every one of them is
# checked against the manifest's sha256 and the build fails on any mismatch.
# After this layer the hub is never contacted again (offline flags below).
ENV HF_HOME=/app/hf
RUN python - <<'PY'
import json
from huggingface_hub import snapshot_download
m = json.load(open("/app/deid-model.json"))
snapshot_download(m["model"], revision=m["revision"], allow_patterns=list(m["files"]))
PY
RUN python -c "from pathlib import Path; from app.scripts.deid_detectors import verify_model_manifest as v; print('model manifest ok', v(Path('/app/deid-model.json'))[:12])"
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    DEID_NLP_ENGINE=transformers \
    DEID_MODEL_MANIFEST=/app/deid-model.json \
    TOKENIZERS_PARALLELISM=false

RUN chown -R appuser:appuser /app/hf
USER appuser
CMD ["python", "-m", "app.scripts.export_corpus"]
