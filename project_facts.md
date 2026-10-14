# HaqSetu — Single Source of Truth (`project_facts.md`)

## 1. Implemented & Tested Features (Stages P1–P8)

- **P1 Visual Frontend**: Civic Ledger responsive HTML/CSS/vanilla JS UI with native radio mutual exclusion fix. Preserved unchanged.
- **P2 Eligibility Engine & Schemas**: Pydantic v2 validation, `ASSESSABLE` vs. `LISTING_ONLY` separation, deterministic three-valued Kleene logic (`ELIGIBLE`, `INELIGIBLE`, `NEEDS_VERIFICATION`), and fail-closed verification guards.
- **P3 DAG Action Planner**: Standard-library `graphlib.TopologicalSorter` with explicit unknown-prerequisite and cycle detection and non-bypassable `GATED` submission protection.
- **P4 FastAPI Backend & Catalogue Service**: `/api/health`, `/api/schemes`, `/api/schemes/{id}`, `/api/assess`, `/api/demo/scenarios`, `/api/demo/assess`, `/api/evidence/{id}`, `/api/ask`, 32 KB payload cap, privacy-preserving headers, and per-record type labelling in demo endpoint.
- **P5 Classical Policy Retriever**: Pure-Python standard-library TF-IDF + cosine similarity clause search evaluated on 10 labelled synthetic queries (`data/eval_queries.json`). Top-1=1.0, Top-3=1.0, MRR=1.0, Refusal=1.0 on this small synthetic corpus.
- **P6 Progressive UI Bridge**: Additive `js/haqsetu_api_client.js` and `css/haqsetu_p6_enhancements.css` connecting discovery, verification checklists, official helpdesk/grievance channels, fictional demo assessment questionnaire (wired to `/api/demo/assess`), and policy Q&A (wired to `/api/ask`). Safe `textContent` DOM rendering only. Clickable official source links (`https:` only, `rel="noopener noreferrer"`).
- **P7 Test Suite**: 32 pytest cases collected and passing (Python 3.14.5, pytest 9.1.1).
- **P8 Documentation & Deliverables**: `README.md`, `ARCHITECTURE.md`, `DATA_VERIFICATION.md`, `TESTING.md`, `project_facts.md`, `scripts/generate_submission_docs.py`, `deliverables/HaqSetu_Lean_Canvas.pdf`, `deliverables/HaqSetu_Concept_Note.docx`, `deliverables/HaqSetu_Presentation_Outline.md`.

---

## 2. Test Suite Count

**32 pytest cases** (verified by running `python -m pytest -v`):
- `tests/test_engine_and_schema.py`: 11 cases
- `tests/test_planner.py`: 7 cases (including 3 parametrized)
- `tests/test_retriever.py`: 5 cases
- `tests/test_api_and_security.py`: 9 cases

The PDF reference document claimed "26 tests" — the actual implemented count is 32. All documentation reflects this actual measured number.

---

## 3. Verified Official Portal Facts vs. Unverified Policy Candidates

### PM-USP Central Sector Scheme (`pmsp-central-sector`)

| Item | Status |
|------|--------|
| Portal: https://scholarships.gov.in | ✅ Observed fact |
| Helpdesk email/phone (https://scholarships.gov.in/fresh1819/nsphelpdesk) | ✅ Source-backed (page updated June 2026) |
| NSP Nodal Officer directory (https://scholarships.gov.in/iver/nodelOfficerDetails) | ✅ Source-backed (page updated June 2026) |
| Income ceiling, marks cutoff, course exclusions, application window | ❌ Not verified — LISTING_ONLY |

### UP Pre-Matric Scholarship (`up-pre-matric-scholarship`)

| Item | Status |
|------|--------|
| Portal: https://scholarship.up.gov.in | ✅ Observed fact |
| CPGRAMS: https://pgportal.gov.in/Home/ (general route) | ✅ Source-backed (general GoI portal) |
| Category variant, class eligibility, income threshold, documents | ❌ Not verified — LISTING_ONLY |

---

## 4. Key Design Decisions (Audit Compliance)

| Audit Item | Resolution |
|------------|-----------|
| #2 Action submission inference | Uses label-only check (`lower_label.startswith("submit")`), not ID substring. `act-post-submit-receipt` correctly stays non-gated. |
| #3 Fail-closed | Global mandatory failure overrides passing pathway; non-exhaustive pathways return NEEDS_VERIFICATION; no pathway → NEEDS_VERIFICATION |
| #4 Strict bool validation | `item.get("human_verified") is True` — string `"false"` is not truthy |
| #5 Support channel source notes | `verified_portal_fact=True` only when a specific source URL backs the claim |
| #6 Real/demo boundary | `GET /api/demo/scenarios` labels each record by `data_type` and `is_fictional` per record |
| #7 Body limit | Content-Length pre-check + bounded `asyncio.wait_for(request.body(), timeout=10.0)` + actual length check |
| #10 Test count | 32 actual (not PDF's claimed 26); documentation updated |
| #11 No PowerPoint claim | No PPTX generated; Markdown outline provided; docstring corrected |
| RAM claim | No `< 50 MB RAM` claim published anywhere — not measured |

---

## 5. Remaining Manual Tasks

1. **Human verification of real schemes**: Inspect Tier 1 official sources for PM-USP and UP Pre-Matric for the current academic year; record verbatim clauses, section/page, reviewer, date; then change `readiness` to `ASSESSABLE`.
2. **Browser layout verification**: Manually check `http://127.0.0.1:8000` at `393x852` (mobile) and `1280x800` (desktop) after starting uvicorn.
3. **Screenshot capture**: Capture live screenshots of discovery, demo assessment, and Q&A panels for presentation slides (see `deliverables/HaqSetu_Presentation_Outline.md`).
4. **UP Pre-Matric variant selection**: Decide which beneficiary category variant to model when human verification is performed.

---

## 6. Files NOT Modified from P1 (Integrity Preserved)

- `index.html`
- `css/style.css`
- `js/app.js`
- `data/schemes.json`
- `data/fixtures/demo.json`
