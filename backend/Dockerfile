# syntax=docker/dockerfile:1.7
# Backend image for Amazon ECS Express Mode. Built by GitHub Actions and pushed
# to ECR (no local Docker needed). Runs uvicorn on 8080; health at /healthz.
# Pinned by digest so the OS/interpreter layer is the same on every build of a
# commit. Bump deliberately: `docker buildx imagetools inspect python:3.11-slim`.
FROM python:3.11-slim@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7

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

# Pinned + hash-verified dependency set for the one-off corpus-export NER task.
# NOT installed here — the API image must not carry a 382 MB NLP model, and
# nothing in the request path imports Presidio. It ships as a manifest so the
# export task installs a reproducible, tamper-evident set instead of resolving
# `pip install presidio-analyzer` live against PyPI inside a PHI container.
COPY deid.lock ./

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
# DB only) and listens on 8080 (>1024), so no root is needed. The one-off export
# NER task installs presidio + a spaCy model at RUNTIME with PIP_USER=1, so those
# land in this user's site (~/.local) rather than the root-owned system path.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080
# --no-server-header: don't advertise the uvicorn version (matches the header
# posture in app/core/security_headers.py).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
