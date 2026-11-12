# Heimdall

AI-assisted insurance claim-denial appeals for small US healthcare practices. A practice uploads the denial, the original claim and the clinical notes; Heimdall extracts the structured data, classifies the denial, estimates the chance of a successful appeal and drafts the appeal letter. A second flow, the pre-check, reviews a draft claim before submission and returns a denial-risk report.

> Synthetic data only: no real patient information belongs in this repo, its fixtures or its logs. Heimdall produces estimates and drafts; clinical, financial and submission decisions stay with the practice.

---

## How it works

**Appeal pipeline** — text is read from each PDF (`pypdf`, AWS Textract for scans), then a model on AWS Bedrock extracts payer, plan, codes (CPT, ICD-10, CARC/RARC), dates and amounts as validated JSON. The denial is classified, the appeal deadline is estimated by plan type, and a letter is drafted and rendered to PDF.

**Pre-check** — deterministic CMS NCCI edits (PTP bundling, MUE unit limits) plus an AI review of the documentation against the billed codes. Findings are risk flags, never a clean-claim guarantee. For a born-digital or fillable CMS-1500, chosen edits can be applied to the PDF in place.

**Outcomes** — after submitting an appeal, the practice logs the payer's decision, which feeds the dashboard's win-rate and dollars-recovered figures.

**Multi-tenant and PHI-aware** — every row belongs to a practice and every query is scoped to it. Member IDs are stored as keyed hashes, logs carry IDs and lengths rather than document text, the audit log is append-only at the database grant level, and every model call is recorded with model ID, prompt version, tokens and latency.

---

## Stack

Next.js 16 · React 19 · TypeScript · Tailwind · FastAPI · SQLAlchemy 2 · PostgreSQL · AWS Bedrock (Claude Sonnet) · Textract · S3 · Cognito · ECS · Terraform

---

## Running

Needs Python 3.11, Node 20, and an AWS account with the resources the Terraform at the repo root creates (PostgreSQL, S3, Cognito, Bedrock access, Textract, KMS).

```bash
cp .env.example .env.local        # repo root; fill in the AWS, Cognito and database values

cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
python ../scripts/seed_dev.py     # creates a practice and a user row
uvicorn app.main:app --reload     # http://localhost:8000

cd ../frontend
npm install
npm run dev                       # http://localhost:3000
```

There is no sign-up flow: users are invited by an admin. Tests run with `pytest` in `backend/` and `npm test` in `frontend/`.
