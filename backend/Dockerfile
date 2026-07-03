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

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
