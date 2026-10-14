# HaqSetu — AI Welfare and Scholarship Navigator

**Guiding Vision:** *"The opportunity exists. The person who needs it exists. The bridge connecting them is often missing. HaqSetu aims to become that bridge."*

**SDG Alignment:** Primary — **SDG 4 (Quality Education)** | Secondary — **SDG 1 (No Poverty)**, **SDG 10 (Reduced Inequalities)**

---

## 1. Overview & Differentiator

HaqSetu connects students and families to scholarship information through an explainable, evidence-backed pipeline:

```
Eligibility Condition → Supporting Evidence → Decision → Next Action
```

Key design properties:

- **Strict Readiness vs. Outcome Separation**: Real schemes remain `LISTING_ONLY` (`applicant_outcome: null`) until a human verifies official current-cycle guidelines. No eligibility verdict is ever fabricated.
- **Three-Valued Kleene Logic Engine**: Evaluates `global_conditions` (AND), `pathways` (OR of ANDs), and `optional_conditions` (INFO_ONLY) into `ELIGIBLE`, `INELIGIBLE`, or `NEEDS_VERIFICATION`.
- **DAG Action Planner**: Uses standard-library `graphlib.TopologicalSorter` to assign `DONE`, `READY`, `BLOCKED`, and `GATED` states. Completion flags never bypass safety gates.
- **Source-Grounded Policy Q&A**: Standard-library TF-IDF + cosine similarity retrieval over verified policy clauses with explicit refusal on unverified or out-of-scope queries.
- **Zero External ML/LLM Dependencies**: All logic is deterministic, traceable, and locally runnable.

---

## 2. Quick Start (Windows 10 / Python 3.14.5)

From `C:\Users\manme\Desktop\HaqSetu`:

```powershell
# Run the full automated test suite (32 tests)
python -m pytest -v

# Start the local application server (no access logging for applicant privacy)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open `http://127.0.0.1:8000` in your browser.

---

## 3. API Routes Summary

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/api/health` | Service health and scheme counts |
| `GET` | `/api/schemes` | Search/filter real schemes (`q`, `readiness`, `ministry`) |
| `GET` | `/api/schemes/{scheme_id}` | Real scheme details, verification checklist, support channels |
| `POST` | `/api/assess` | Evaluate a real scheme; rejects fictional IDs (400); returns `applicant_outcome: null` for `LISTING_ONLY` |
| `GET` | `/api/demo/scenarios` | Lists all scenarios from `data/fixtures/demo.json` with per-record type labelling |
| `POST` | `/api/demo/assess` | Evaluate the fictional demo scenario with mandatory `FICTIONAL_DEMO_WARNING` |
| `GET` | `/api/evidence/{scheme_id}` | Recorded policy evidence references for a scheme |
| `POST` | `/api/ask` | Source-grounded TF-IDF policy Q&A; never determines eligibility |
| `GET` | `/` | Serves P1 `index.html` with P6 progressive enhancements injected |

---

## 4. Real Scheme Status

Both real candidates remain `LISTING_ONLY`. Assessment is unavailable until human verification:

| Scheme ID | Name | Official Portal |
|-----------|------|-----------------|
| `pmsp-central-sector` | Central Sector Scheme of Scholarship (PM-USP) | https://scholarships.gov.in |
| `up-pre-matric-scholarship` | Uttar Pradesh Pre-Matric Scholarship | https://scholarship.up.gov.in |

See `DATA_VERIFICATION.md` for the human verification protocol.

---

## 5. Fictional Demo

`demo-assessable` (in `data/fixtures/demo.json`) uses entirely invented rules to demonstrate the assessment workflow. Every response carries a persistent `FICTIONAL DEMO WARNING`. Use `POST /api/demo/assess` to exercise it.

`demo-listing-only` is a `REAL_STUB` candidate stored in the fixture file for reference; it is not fictional and carries no fictional warning.

---

## 6. Privacy & Security Design

- Applicant answers are **stateless** — never stored or logged
- **32 KB** request body cap enforced
- Defensive HTTP headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`
- Bound to `127.0.0.1` only — not exposed externally
- No Aadhaar numbers, bank account numbers, or passwords collected
- Errors are structured and client-safe — no stack traces exposed

---

## 7. Troubleshooting

- **Port 8000 in use**: Change `--port 8000` to another port
- **`Module not found`**: Ensure you're running from the project root with the correct Python environment
- **`SchemeValidationError`**: Check `data/schemes.json` and `data/fixtures/demo.json` are present and valid JSON
- **Tests failing**: Run `python -m pytest -v` and check the specific test output; the test suite expects both data files to be present
