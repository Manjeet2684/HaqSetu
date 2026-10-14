# HaqSetu — Presentation Outline (Slide-by-Slide Source)

> **Note:** This Markdown file is the editable slide source. No PowerPoint generator
> is installed in this environment. Use this outline to build slides manually in
> PowerPoint, Google Slides, or Keynote. Screenshot placeholders must be filled
> by capturing the running application at `http://127.0.0.1:8000`.

---

## Slide 1 — Title Slide
- **Product Name:** HaqSetu — AI Welfare and Scholarship Navigator
- **Tagline:** "The opportunity exists. The person who needs it exists. The bridge connecting them is often missing."
- **SDGs:** Primary: SDG 4 (Quality Education) | Secondary: SDG 1, SDG 10
- **IBM SkillsBuild Internship Deliverable**

---

## Slide 2 — Problem Statement
- Students miss scholarships due to fragmented PDFs and unclear eligibility criteria
- Chatbots hallucinate income limits, marks cutoffs, and deadlines
- No clear prerequisite order for certificates, OTR registration, nodal officer verification
- Real, unverified schemes must not be turned into misleading automated verdicts

---

## Slide 3 — HaqSetu Workflow
```
Eligibility Condition → Supporting Evidence → Decision → Next Action
```
- Discovery: Browse real scheme catalogue with verification status
- Assessment: Three-valued Kleene logic (ELIGIBLE / INELIGIBLE / NEEDS_VERIFICATION)
- Action Planning: Dependency-aware DAG with DONE/READY/BLOCKED/GATED
- Q&A: Source-grounded TF-IDF retrieval with explicit refusal

---

## Slide 4 — Architecture (Modular Monolith)
- `app/schemas.py` → Pydantic v2 contracts + fail-closed loaders
- `app/engine.py` → Kleene 3-valued eligibility evaluation
- `app/planner.py` → graphlib.TopologicalSorter action planner
- `app/retriever.py` → Stdlib TF-IDF + cosine similarity
- `app/catalog.py` → Real/demo separation catalogue service
- `app/main.py` → FastAPI routes + security middleware + static mount
- `js/haqsetu_api_client.js` → Progressive P6 API bridge (safe DOM)

---

## Slide 5 — Safety by Design
- **LISTING_ONLY** real schemes → `applicant_outcome = null` always
- **Safety gates** cannot be bypassed by marking actions complete
- **Failed global mandatory condition** cannot be overridden by passing pathway
- **Unknown/missing answers** never treated as passing
- **Fictional demo** always labelled; never leaks to real endpoints
- **No Aadhaar, bank data, or PII** collected or logged

---

## Slide 6 — Scheme Catalogue (Screenshot)
> [PLACEHOLDER: Screenshot of real scheme catalogue panel from http://127.0.0.1:8000]
- Shows PM-USP and UP Pre-Matric as LISTING_ONLY
- Human verification checklist visible
- Official portal, helpdesk, and CPGRAMS links

---

## Slide 7 — Demo Assessment (Screenshot)
> [PLACEHOLDER: Screenshot of fictional demo assessment from http://127.0.0.1:8000]
- FICTIONAL DEMO WARNING banner persistent
- Condition-by-condition outcomes (SATISFIED/FAILED/UNRESOLVED)
- GATED submission when eligibility unresolved
- ELIGIBLE outcome when all conditions met

---

## Slide 8 — Policy Q&A Retrieval (Screenshot)
> [PLACEHOLDER: Screenshot of policy Q&A panel from http://127.0.0.1:8000]
- Real scheme query → INSUFFICIENT_VERIFIED_EVIDENCE refusal
- Demo scheme query → source-linked fictional clause
- Source title, section, cycle, score, and official URL visible

---

## Slide 9 — Test Suite & Benchmark
- **32 pytest cases** collected and passing (Python 3.14.5, pytest 9.1.1)
  - 11 engine/schema, 7 planner (incl. 3 parametrized), 5 retrieval, 9 API/security
- **10-query synthetic smoke benchmark** (data/eval_queries.json):
  - Top-1 Accuracy: 1.0 | Top-3 Recall: 1.0 | MRR: 1.0 | Refusal Accuracy: 1.0
  - ⚠️ Small synthetic corpus — not independent validation

---

## Slide 10 — Honest Current Status & Roadmap
**Implemented:**
- Full P1–P8 pipeline: engine, planner, retrieval, API, UI bridge
- 2 real scheme stubs (LISTING_ONLY, safe by design)
- 1 verified assessable fictional demo scenario

**Pending human action:**
- Inspect official government portals for current academic-year rules
- Record verbatim clauses, section/page, reviewer name, date
- Only then promote a scheme from LISTING_ONLY → ASSESSABLE

**Future scope (not in MVP):**
- Vernacular translation, pin-code district lookup, multi-scheme comparison

---
