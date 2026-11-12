# Heimdall

AI-assisted automation for insurance **claim-denial appeals**, built for small US
healthcare practices. A doctor uploads three documents (the denial, the original
claim, and clinical notes); Heimdall extracts the structured data, classifies the
denial, estimates the chance of a successful appeal, and drafts the appeal letter.
The practice reviews, downloads, and submits it themselves, then logs the outcome.
A second case type, the **pre-check**, works *before* submission: upload a draft
claim + clinical notes and get a denial-risk report — deterministic CMS NCCI edits
plus an AI documentation-vs-codes review — always framed as risk flags, never a
clean-claim guarantee.

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
- **Case types** — `cases.case_type` is `appeal` or `pre_check`, sharing one
  pipeline architecture. Pre-checks run deterministic CMS NCCI edits (PTP
  bundling + MUE unit limits, `backend/app/services/ncci.py`) plus an AI
  documentation-vs-codes review, and write a denial-risk report (`risk_reports`).
  When the draft claim is a born-digital PDF, the doctor can tick the proposed
  edits and get the same PDF back with them applied in place — no model call,
  old glyphs removed and the result re-read and verified
  (`backend/app/services/claim_patch.py`, `corrected_claims`). A claim typed
  into a fillable CMS-1500 PDF is read through its form fields
  (`services/claim_form.py`, `documents.text_source = form_fields`) and edited
  by rewriting field values — the corrected copy stays fillable. Scanned
  claims get the edits list only.
- **Database** — PostgreSQL (AWS RDS). All money stored as integer cents.
  NCCI reference tables (`ncci_ptp_edits`, `ncci_mue`, `ncci_loads` — no PHI,
  no tenant column) are refreshed monthly by the `load-ncci` workflow.
- **File storage** — S3 (presigned URLs; the backend never streams file bodies).
- **AI** — Claude Sonnet via **AWS Bedrock** (`invoke_model`). Models are invoked
  **only from the backend**. Every call writes a `model_runs` row (provider,
  model id, prompt version, tokens, latency).
- **OCR** — AWS Textract for scanned PDFs (digital PDFs use `pypdf`).
- **Auth** — AWS Cognito, TOTP MFA required. No self-signup; admins invite users from `/admin/users` (temporary password by email). Self-service password reset and authenticator recovery via emailed codes.
- **Background work** — FastAPI `BackgroundTasks` running the pipeline in
  `backend/app/services/pipeline.py`.

---

## Prerequisites

- **Python 3.11** and **Node 20**
  (3.11 is what the Dockerfile builds and what CI runs.)
- An **AWS account** with these already provisioned (all created by the Terraform at the repo root):
  RDS PostgreSQL, an S3 bucket, a Cognito user pool + app client, Bedrock model
  access (an inference profile), Textract, and a KMS key.
- AWS credentials available to the default boto3 chain (e.g. `aws configure`).

---

## Setup

### 1. Backend

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp ../.env.example ../.env.local   # REPO ROOT, not backend/ — core/config.py
                                   # only ever reads the root .env / .env.local

alembic upgrade head            # apply migrations
python ../scripts/seed_dev.py   # create a practice + user row
python ../scripts/seed_case.py  # optional: synthetic demo cases

uvicorn app.main:app --reload   # serves http://localhost:8000
```

Health check: `curl http://localhost:8000/healthz` → `{"status":"ok"}`.

**`.env.local` at the repo root** (mirrors `.env.example`; `core/config.py` reads the repo root, not `backend/`):

```
AWS_REGION=us-east-1
S3_BUCKET_NAME=

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

Open http://localhost:3000 and sign in with a user an admin invited (or one you
created via the `provision-user` workflow). There is no sign-up flow by design.

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
6. **New Pre-Check** → upload a *draft* claim + clinical notes before submitting
   to the payer. The pipeline runs the NCCI edits (PTP bundling, MUE units) and
   the AI documentation-vs-codes review, then shows a denial-risk report — fix
   the flagged issues before the claim goes out.

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
      services/   # pipeline, claude_client, extraction, analysis, letter, ncci, precheck, pdf_gen, s3
      prompts/    # one module per prompt with a VERSION constant (incl. the two pre-check prompts)
      scripts/    # one-off ECS tasks (provision_user, load_ncci, dispose_practice, ...)
      tests/
    alembic/      # migrations
  docs/         # policies/ — Markdown source of the /terms, /privacy and /subprocessors pages
  scripts/      # seed_dev.py, seed_case.py, make_fixtures.py
```
