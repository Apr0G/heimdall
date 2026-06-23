# Heimdall

AI-assisted automation for insurance **claim-denial appeals**, built for small US
healthcare practices. A doctor uploads three documents (the denial, the original
claim, and clinical notes); Heimdall extracts the structured data, classifies the
denial, estimates the chance of a successful appeal, and drafts the appeal letter.
The practice reviews, downloads, and submits it themselves, then logs the outcome.

> **Synthetic data only.** This is an MVP. No real PHI ever belongs in this repo,
> its fixtures, logs, or commits. Use names like "Jane Doe" and claims like
> `CLM-TEST-0001`.

> **Disclaimer.** Heimdall provides AI-assisted estimates and drafts. All clinical,
> financial, and submission decisions remain with the practice. Heimdall is not a
> medical, legal, or billing advisor.

---

## Architecture

- **Monorepo** — `frontend/` (Next.js 16 App Router, TypeScript, Tailwind,
  shadcn-on-Base-UI) and `backend/` (FastAPI, SQLAlchemy 2 async, Alembic,
  Pydantic v2).
- **Database** — PostgreSQL (AWS RDS). All money stored as integer cents.
- **File storage** — S3 (presigned URLs; the backend never streams file bodies).
- **AI** — Claude Sonnet via **AWS Bedrock** (`invoke_model`). Models are invoked
  **only from the backend**. Every call writes a `model_runs` row (provider,
  model id, prompt version, tokens, latency).
- **OCR** — AWS Textract for scanned PDFs (digital PDFs use `pypdf`).
- **Auth** — AWS Cognito (login only; users are created manually in Cognito).
- **Background work** — FastAPI `BackgroundTasks` running the pipeline in
  `backend/app/services/pipeline.py`.

Full design and the phased build plan live in `docs/`.

---

## Prerequisites

- **Python 3.12** and **Node 20**
- An **AWS account** with these already provisioned (see `docs/` for details):
  RDS PostgreSQL, an S3 bucket, a Cognito user pool + app client, Bedrock model
  access (an inference profile), Textract, and a KMS key.
- AWS credentials available to the default boto3 chain (e.g. `aws configure`).

---

## Setup

### 1. Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env.local      # then fill in the values (see below)

alembic upgrade head            # apply migrations
python ../scripts/seed_dev.py   # create a practice + user row
python ../scripts/seed_case.py  # optional: synthetic demo cases

uvicorn app.main:app --reload   # serves http://localhost:8000
```

Health check: `curl http://localhost:8000/healthz` → `{"status":"ok"}`.

**`backend/.env.local`** (mirrors `.env.example`):

```
AWS_REGION=us-east-1
S3_BUCKET_NAME=
KMS_KEY_ALIAS=alias/heimdall

DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DBNAME

COGNITO_USER_POOL_ID=
COGNITO_CLIENT_ID=
COGNITO_REGION=us-east-1

BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-...   # inference profile id

APP_ENV=development
FRONTEND_URL=http://localhost:3000
LOG_LEVEL=INFO
```

### 2. Frontend

```bash
cd frontend
nvm use 20      # or otherwise ensure Node 20
npm install
npm run dev     # serves http://localhost:3000
```

Optional `frontend/.env.local`:

```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000   # defaults to this if unset
```

### 3. Log in

Open http://localhost:3000 and sign in with a user you created in your Cognito
pool. There is no sign-up flow by design — users are provisioned manually.

---

## Using it

1. **New Appeal** → upload the denial, the original claim, and clinical notes (PDF).
2. You land on the case page, which polls while the pipeline runs
   (extract → analyze → draft letter).
3. Review the analysis and the drafted letter; **copy** it, **download the PDF**,
   then **mark it submitted**.
4. When the payer responds, **log the outcome** — the dashboard tracks your win
   rate and dollars recovered, and reminds you about appeals left unreported.
5. If the analysis asks for a prior authorization or prior-treatment record,
   upload it from the case page to **re-draft** the letter (a new version).

Synthetic test PDFs can be generated with `python scripts/make_fixtures.py`
(written to the gitignored `fixtures/`).

---

## Common commands

```bash
# Backend (from backend/, venv active)
uvicorn app.main:app --reload                 # dev server
alembic revision --autogenerate -m "msg"      # new migration
alembic upgrade head                          # apply migrations
pytest                                         # run tests
ruff check . && black --check .               # lint + format check

# Frontend (from frontend/)
npm run dev                                    # dev server
npm run build                                  # production build + type-check
npm run lint                                   # lint
```

---

## Repo layout

```
heimdall/
  frontend/   # Next.js app (routes in src/app, shared UI in src/components, api/auth in src/lib)
  backend/
    app/
      api/        # FastAPI routers (one per resource)
      core/       # config, auth, logging
      db/         # session, base, mixins
      models/     # SQLAlchemy models
      schemas/    # Pydantic request/response + LLM I/O
      services/   # pipeline, claude_client, extraction, analysis, letter, pdf_gen, s3
      prompts/    # one module per prompt with a VERSION constant
      tests/
    alembic/      # migrations
  docs/         # design docs, full spec, domain reference
  scripts/      # seed_dev.py, seed_case.py, make_fixtures.py
```
