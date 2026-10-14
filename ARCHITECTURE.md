# HaqSetu Architecture & Data Flow

## 1. Design Philosophy

HaqSetu is a **layered modular monolith** where every arrow is a strict one-way import dependency. No circular imports. No external databases. No cloud infrastructure.

```
Browser (index.html + P1 CSS/JS + P6 CSS/JS)
        ↕ HTTP JSON (stateless, 32 KB cap, no PII logs)
app/main.py          (FastAPI routes + security middleware + static mount)
    ↙           ↘           ↘
app/catalog.py   app/engine.py   app/schemas.py
    ↙               ↘
app/retriever.py   app/planner.py
    ↘               ↗
           app/schemas.py   ← leaf module (stdlib + pydantic only)
```

**Dependency order (leaves first):**
1. `app/schemas.py` — depends only on stdlib and pydantic
2. `app/planner.py` — depends on `app/schemas.py`
3. `app/engine.py` — depends on `app/schemas.py` and `app/planner.py`
4. `app/retriever.py` — depends on `app/schemas.py`
5. `app/catalog.py` — depends on `app/schemas.py` and `app/retriever.py`
6. `app/main.py` — depends on `app/catalog.py`, `app/engine.py`, `app/schemas.py`

---

## 2. Module Boundaries

### `app/schemas.py` — Data Contracts & Fail-Closed Validators
- Pydantic v2 models for all request/response/entity types
- `load_real_schemes()`: reads `data/schemes.json`, enforces strict bool validation (`is True` not `bool()`), adds support channels and verification checklists, fails closed to `LISTING_ONLY`
- `load_demo_fixtures()`: reads `data/fixtures/demo.json`, preserves `REAL_STUB` identity for `demo-listing-only`, marks `FICTIONAL_FIXTURE` records correctly
- `validate_real_scheme_for_assessment()`: 10+ mandatory safeguards before ASSESSABLE is honoured
- `ActionDefinition._infer_submission_flag()`: infers only from label (not ID) to avoid false positives on IDs like `act-post-submit-receipt`

### `app/engine.py` — Three-Valued Kleene Eligibility Engine
- Evaluates `global_conditions` (AND), `pathways` (OR of ANDs), `optional_conditions` (INFO_ONLY)
- Aggregation priority: global_failed > all_pathways_failed > global_unresolved > any_pathway_satisfied
- Non-exhaustive pathways (`pathways_exhaustive=False`) return `NEEDS_VERIFICATION` not `INELIGIBLE`
- Missing/unknown answers never treated as passing
- Real schemes with incomplete verification fail closed to `LISTING_ONLY` with `applicant_outcome=None`

### `app/planner.py` — DAG Action Planner
- `validate_action_graph()`: detects duplicate IDs, unknown prerequisites (`UnknownPrerequisiteError`), and cycles (`DependencyCycleError`)
- `_determine_safety_gate()`: GATED takes strict priority over `completed_action_ids`
- `build_action_plan()`: produces topologically ordered `DONE/READY/BLOCKED/GATED` statuses

### `app/retriever.py` — Stdlib TF-IDF Policy Retriever
- Pure Python: `math`, `re`, `collections.Counter` only
- Strict separation: real and fictional evidence never mixed in a single query execution
- Unverified real scheme evidence → `INSUFFICIENT_VERIFIED_EVIDENCE`
- Below-threshold similarity → `NO_RELEVANT_MATCH`
- Retrieval never determines eligibility

### `app/catalog.py` — Catalogue & Isolation Service
- `SchemeCatalogService`: loads both data files, maintains separate `_real_by_id` and `_demo_by_id` dictionaries
- `list_real_summaries()`: never returns fictional fixtures
- `is_demo_scenario_id()`: used by API to prevent demo IDs from reaching real endpoints
- `list_fictional_demo_scenarios()`: returns only `FICTIONAL_FIXTURE` records from the demo file

### `app/main.py` — FastAPI Application
- `create_app()` factory: accepts `schemes_path`, `demo_path`, `frontend_root` for testability
- `security_and_privacy_middleware`: Content-Length pre-check + actual body read cap + defensive headers
- `GET /api/demo/scenarios`: labels each record by `data_type` and `is_fictional`; does not apply a blanket fictional warning to all records
- Static mount: serves `css/`, `js/`, `data/` and injects P6 assets into `index.html` non-destructively

---

## 3. Data Flow: Real Scheme Assessment

```
POST /api/assess  →  catalog.get_real_scheme()
                  →  engine.evaluate_scheme()
                       → validate_real_scheme_for_assessment()
                       → evaluate_condition() for each global/pathway/optional condition
                       → _evaluate_pathway() for each pathway
                       → planner.build_action_plan()
                  →  AssessmentResponse (applicant_outcome=None if LISTING_ONLY)
```

---

## 4. Data Flow: Demo Assessment

```
POST /api/demo/assess  →  catalog.get_demo_scenario()
                       →  engine.evaluate_scheme()  (same engine as real)
                       →  AssessmentResponse (always fictional_warning set)
```

---

## 5. Data Flow: Policy Q&A

```
POST /api/ask  →  catalog.retriever.answer_query()
               →  enforce real/fictional separation
               →  collect verified evidence corpus
               →  TF-IDF + cosine similarity
               →  AskResponse (SUPPORTED_MATCH / NO_RELEVANT_MATCH / INSUFFICIENT_VERIFIED_EVIDENCE)
               (never calls engine.py)
```

---

## 6. Frontend Integration (P6)

`js/haqsetu_api_client.js` is injected into `index.html` at `/` route. It:
- Uses `document.createElement` and `textContent` exclusively (zero raw `innerHTML`)
- Loads real scheme catalogue on init
- Provides fictional demo assessment questionnaire wired to `/api/demo/assess`
- Provides policy Q&A panel wired to `/api/ask`
- Shows real scheme detail with verification checklist and safe `https:` links to official portals
- Falls back gracefully when the backend is offline (static P1 mode)
