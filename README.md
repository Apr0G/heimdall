# Heimdall

AI-assisted insurance **claim-denial appeal automation** for small US healthcare
practices. A doctor uploads three documents (the denial, the original claim, and
clinical notes); Heimdall extracts the structured claim data, classifies the
denial, estimates appeal success, and drafts the appeal letter. MVP stage:
manual upload, no EHR/clearinghouse integration, no automated submission.

> **Synthetic data only.** No real PHI ever enters this codebase, its logs,
> fixtures, tests, or commits.

## Architecture

Monorepo with two apps. The **backend** (FastAPI + SQLAlchemy 2.x async +
Pydantic v2) owns all business logic and every AWS interaction: Postgres on RDS,
documents in S3 (via presigned URLs — the backend never streams file bodies),
OCR via Textract, and the LLM (Claude Sonnet 4.6 via an **AWS Bedrock inference
profile**) called *only* from the backend. The **frontend** (Next.js 14+ App
Router + TypeScript + Tailwind + shadcn/ui) is a thin client that talks only to
the backend API — it never holds AWS credentials or calls models directly. Auth
is AWS Cognito (login-only; users are provisioned manually). Money is stored as
integer cents; member IDs are stored SHA-256 hashed.

```
heimdall/
  frontend/   # Next.js (App Router, TS, Tailwind, shadcn/ui)
  backend/    # FastAPI (SQLAlchemy async, Alembic, Pydantic v2)
  docs/       # full build spec + domain reference
  scripts/    # dev helper scripts
  main.tf     # AWS infra (managed out-of-band; do not modify here)
```

## Prerequisites

- **Node 20 LTS** (Next 16 requires it). This repo was set up with `nvm`:
  `nvm install 20 && nvm use 20`.
- **Python 3.11+** (3.12 used here).
- AWS CLI configured with credentials that can read the Terraform state and call
  Bedrock/S3/Textract/Cognito (`aws sts get-caller-identity` should work).

## Environment variables

The backend reads a **repo-root `.env.local`** (gitignored). Copy the template
and fill in real values:

```bash
cp .env.example .env.local
```

Values come from the Terraform outputs and Bedrock (run from the repo root):

```bash
terraform output -raw s3_bucket_name      # -> S3_BUCKET_NAME
terraform output -raw db_endpoint         # -> host:port for DATABASE_URL
terraform output -raw cognito_pool_id     # -> COGNITO_USER_POOL_ID
terraform output -raw cognito_client_id   # -> COGNITO_CLIENT_ID
aws bedrock list-inference-profiles --region us-east-1 \
  --query "inferenceProfileSummaries[?contains(inferenceProfileId,'sonnet-4-6')].inferenceProfileId" \
  --output text                           # -> BEDROCK_MODEL_ID (use the us.* one)
```

`DATABASE_URL` format (the DB password lives in the gitignored Terraform vars):

```
postgresql+asyncpg://heimdall_admin:<DB_PASSWORD>@<db_endpoint>/heimdall
```

## Running locally

**Backend** (FastAPI on `:8000`):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload          # http://localhost:8000/healthz -> {"status":"ok"}
pytest                                  # run tests
```

**Frontend** (Next.js on `:3000`):

```bash
cd frontend
nvm use 20
npm install
npm run dev                             # http://localhost:3000
```

## Code quality

Pre-commit hooks run `ruff` + `black` (backend) and `eslint` (frontend):

```bash
pip install pre-commit       # installed with the backend dev deps
pre-commit install           # enable the git hook
pre-commit run --all-files   # run on demand
```
