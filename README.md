# HaqSetu — AI Welfare and Scholarship Navigator

> From scheme to next step, with evidence.

HaqSetu helps students navigate public scholarship information through a transparent flow: **Discover → Understand → Prepare**.

**SDG alignment:** SDG 4 — Quality Education (primary); SDG 1 — No Poverty and SDG 10 — Reduced Inequalities (related).

---

## Why HaqSetu

Scholarship information is often spread across portals and policy documents. HaqSetu combines scheme discovery, evidence-grounded policy retrieval, explainable preliminary assessment, and prerequisite-aware action planning — while refusing to invent eligibility decisions when current official policy evidence is missing.

---

## What is implemented

- **Deterministic eligibility engine:** three-valued evaluation distinguishes `ELIGIBLE`, `INELIGIBLE`, and `NEEDS_VERIFICATION` for assessable data.
- **Dependency-aware action planner:** prerequisite steps use `DONE`, `READY`, `BLOCKED`, and `GATED` states. Completing a task cannot override a safety gate.
- **Intent classification:** a pure-Python Multinomial Naive Bayes classifier routes natural-language queries to the relevant workflow or a safe fallback.
- **Scheme recommendation:** TF-IDF content similarity ranks schemes using catalogue metadata. A recommendation is not an eligibility decision.
- **Policy Q&A:** text retrieval and ranking surface relevant evidence and refuse unsupported or unverified real-scheme questions.
- **Safety separation:** real candidate schemes and fictional demonstration data are kept separate. ML components do not determine or override eligibility.
- **API-backed UI:** scheme catalogue, questionnaire, condition-level results, action plan, assistant, recommendations, and ML benchmark panel.

The ML components use lightweight, pure-Python implementations and do not require a hosted LLM. Their evaluation results are disclosed below rather than presented as production accuracy.

---

## Current scheme verification status

The current real candidate records remain `LISTING_ONLY`:

| Scheme ID | Scheme | Portal |
|-----------|--------|--------|
| `pmsp-central-sector` | PM-USP Central Sector Scholarship | [National Scholarship Portal](https://scholarships.gov.in) |
| `up-pre-matric-scholarship` | Uttar Pradesh Pre-Matric Scholarship | [UP Scholarship Portal](https://scholarship.up.gov.in) |

A portal link does not verify current-cycle eligibility clauses. Until official policy is reviewed and evidence is recorded, the real records must not produce automated eligibility outcomes. The fictional `demo-assessable` fixture exists only to demonstrate the workflow and must not be mistaken for government policy.

---

## AI/ML evaluation — limitations are explicit

The last reported run of `python scripts/train_evaluate_ml.py` produced these synthetic smoke-test results:

- **Intent classifier:** accuracy 0.9812, macro F1 0.9814, measured in-sample on the same 160 synthetic utterances used for training.
- **Policy retrieval:** 10 synthetic queries; six supported queries use fictional demo evidence, and four test refusal behaviour. Reported Top-1, Top-3, MRR, and refusal accuracy were each 1.0000.
- **Scheme recommender:** 12 synthetic queries; reported Top-1 accuracy and MRR were each 1.0000.

These results show that the implemented paths execute on controlled, in-distribution examples. They do not establish generalisation to unseen real-world student queries or validate actual scholarship policy. Independent evaluation with representative, held-out queries remains future work.

---

## Run locally (Windows / PowerShell)

Use Python 3.13 or another Python version supported by the installed dependencies. Run commands from the repository root.

```powershell
# Install the pinned runtime dependencies
python -m pip install -r requirements.txt

# Start the full FastAPI application (not a static file server)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open:
- **App:** http://127.0.0.1:8000/
- **API health:** http://127.0.0.1:8000/api/health
- **Interactive API docs:** http://127.0.0.1:8000/docs

If port 8000 is already occupied, check which process owns it before stopping anything, or use another available port. Opening `index.html` with `file://` or using `python -m http.server` does not start the FastAPI routes.

---

## Run tests and ML evaluation

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python scripts/train_evaluate_ml.py
node --check js/app.js
node --check js/haqsetu_api_client.js
```

The latest reported local verification for the application-improvement candidate was **53 pytest tests passed** (with two third-party deprecation warnings) and **14 HTTP smoke checks passed**. Treat this as a historical result; rerun these commands after changes or deployment.

---

## API overview

| Method | Route | Purpose |
|--------|-------|---------|
| `GET` | `/api/health` | Health and catalogue counts |
| `GET` | `/api/schemes` | Search/filter real scheme candidates |
| `GET` | `/api/schemes/{scheme_id}` | Real scheme detail and verification checklist |
| `POST` | `/api/assess` | Real-scheme assessment; `LISTING_ONLY` records fail closed |
| `GET` | `/api/demo/scenarios` | Explicitly labelled demonstration scenarios |
| `POST` | `/api/demo/assess` | Fictional demonstration assessment with warning |
| `GET` | `/api/evidence/{scheme_id}` | Evidence references; demo scope requires explicit opt-in |
| `POST` | `/api/ask` | Evidence-grounded policy retrieval and refusal |
| `POST` | `/api/assistant` | Intent classification and safe query routing |
| `POST` | `/api/recommend` | Metadata-based scheme recommendations, not eligibility |
| `GET` | `/api/ml/metrics` | Synthetic benchmark summary |

See `/docs` for actual request and response schemas.

---

## Security and privacy notes

- The current MVP does not use a persistent applicant database, and source inspection found no application code path that explicitly writes applicant answers to disk or logs them. This is a code-level observation, not a privacy certification or security audit.
- The app enforces a 32 KB request-body limit and sets defensive response headers.
- The local startup command uses `--no-access-log` to suppress Uvicorn's per-request access log lines. Reverse proxies, hosting platforms, and other infrastructure may have separate logging settings that must be reviewed before deployment.
- Only the explicitly intended fictional demo fixture should be publicly served as static data; scheme records and internal evaluation datasets should remain behind the API or unavailable as direct static files.
- HaqSetu does not submit scholarship applications on a user's behalf.

---

## Deployment

A `Dockerfile` and Render Blueprint configuration are included in the application-improvement candidate. After committing the verified files to GitHub:

1. Open the [Render Dashboard](https://dashboard.render.com/).
2. Choose **New → Blueprint** and connect `Manjeet2684/HaqSetu`.
3. Review the service configuration from `render.yaml` and deploy.
4. Verify the deployed `/`, `/api/health`, and `/docs` routes.

A configured Blueprint is deployment preparation, not proof of a successful deployment. Confirm the real public URL and repeat API smoke checks after the service is live.

---

## Project structure

```
app/                  FastAPI routes, schemas, engine, planner, catalogue, AI/ML
css/                  Civic Ledger theme and enhancements
js/                   Frontend interactions and API bridge
data/                 Scheme records, isolated demo fixture, evaluation datasets
scripts/              ML evaluation and HTTP smoke testing
tests/                Eligibility, planner, retrieval, API/security, and ML tests
Dockerfile            Container startup configuration
render.yaml           Render Blueprint configuration
requirements.txt      Pinned runtime dependencies
requirements-dev.txt  Test/development dependencies
```

---

## Current limitations

- Real candidate schemes are not yet policy-verified for automated eligibility.
- ML evaluation relies on small synthetic datasets; independent real-world generalisation is not established.
- Full browser/device testing and successful public deployment must be verified separately.
- The current catalogue is intentionally small and supports a demonstration, not comprehensive national scheme coverage.

---

*HaqSetu — an evidence-first bridge from scholarship information to the next practical step.*
