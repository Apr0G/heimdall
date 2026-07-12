# Backend image for Amazon ECS Express Mode. Built by GitHub Actions and pushed
# to ECR (no local Docker needed). Runs uvicorn on 8080; health at /healthz.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Project metadata + source, then install (pulls deps from pyproject).
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install .

# AWS RDS CA bundle for optional verify-full DB TLS (enable via DB_SSL_CA_BUNDLE).
ADD https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem /app/rds-ca.pem

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
