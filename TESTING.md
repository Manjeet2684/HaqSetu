# HaqSetu Testing Guide

## 1. Quick Run (Windows 10)

```powershell
cd C:\Users\manme\Desktop\HaqSetu
python -m pytest -v
```

Expected output: **32 passed** in under 5 seconds.

---

## 2. Test Suite Breakdown (32 tests across 4 modules)

### `tests/test_engine_and_schema.py` — 11 tests (P2/P7)
| Test | What it verifies |
|------|-----------------|
| `test_normalize_legacy_fixture_condition_results` | PASS/FAIL/NEEDS_VERIFICATION normalize correctly; invalid tokens raise ValueError |
| `test_numeric_threshold_boundaries_both_sides` | LTE/GTE exact boundary, passing side, failing side |
| `test_missing_and_dont_know_answers_never_treated_as_passing` | Missing/unknown answers always UNRESOLVED → NEEDS_VERIFICATION |
| `test_or_pathways_one_passing_one_failing_succeeds` | OR pathway logic: one pass makes ELIGIBLE |
| `test_global_mandatory_failure_overrides_passing_pathway` | Failed global condition → INELIGIBLE regardless of pathway |
| `test_global_unresolved_does_not_short_circuit_pathway_evaluation` | Global UNRESOLVED still evaluates all pathways |
| `test_non_exhaustive_pathways_never_produce_unjustified_ineligible` | pathways_exhaustive=False → NEEDS_VERIFICATION not INELIGIBLE |
| `test_optional_conditions_never_flip_eligibility_outcome` | Optional → INFO_ONLY; does not change verdict |
| `test_listing_only_produces_null_outcome` | LISTING_ONLY → applicant_outcome=None |
| `test_incomplete_or_unverified_real_scheme_fails_closed` | Missing verified_by/URL → LISTING_ONLY |
| `test_real_schemes_and_demo_fixtures_compatibility_and_separation` | Full compatibility with actual data files; REAL_STUB not fictional |

### `tests/test_planner.py` — 7 tests (P3/P7, includes 3 parametrized)
| Test | What it verifies |
|------|-----------------|
| `test_topological_prerequisite_ordering_and_states` | DONE/READY/BLOCKED/GATED assigned correctly in topo order |
| `test_unknown_prerequisite_id_raises_explicit_error` | UnknownPrerequisiteError raised |
| `test_dependency_cycle_raises_explicit_error` | DependencyCycleError raised |
| `test_submission_gated_when_ineligible_unresolved_or_listing_only[×3]` | Submission GATED for INELIGIBLE/NEEDS_VERIFICATION/LISTING_ONLY |
| `test_completed_actions_never_bypass_safety_gates` | Gated action stays GATED even if in completed_action_ids; act-post-submit-receipt stays BLOCKED |

### `tests/test_retriever.py` — 5 tests (P5/P7)
| Test | What it verifies |
|------|-----------------|
| `test_retriever_refuses_unverified_real_schemes` | INSUFFICIENT_VERIFIED_EVIDENCE for real schemes without verified evidence |
| `test_retriever_isolates_fictional_demo_from_real_queries` | Demo blocked without flag; allowed with flag; ev-001 returned |
| `test_retriever_no_match_refusal_for_out_of_scope_queries` | NO_RELEVANT_MATCH for irrelevant queries |
| `test_retriever_returns_verified_real_passage_with_exact_source_metadata` | Source URL, title, section, excerpt all present |
| `test_evaluation_benchmark_corpus_runs_and_meets_targets` | 10-query benchmark runs; refusal accuracy ≥ 0.8 |

### `tests/test_api_and_security.py` — 9 tests (P4/P7)
| Test | What it verifies |
|------|-----------------|
| `test_health_endpoint_and_security_headers` | Status OK, counts correct, nosniff/DENY headers |
| `test_list_real_schemes_excludes_fictional_and_supports_search` | Only real schemes returned; search filter works |
| `test_scheme_detail_and_not_found_and_fictional_rejection` | Checklist ≥ 3, support channels ≥ 2, 404 for demo/missing IDs |
| `test_real_assess_endpoint_keeps_listing_only_null_and_rejects_fictional` | null outcome for LISTING_ONLY; 400 for fictional ID |
| `test_demo_assess_endpoint_evaluates_dynamically_with_fictional_warning` | NEEDS_VERIFICATION+GATED when income unknown; ELIGIBLE+READY when all met |
| `test_ask_endpoint_refusal_and_demo_retrieval` | INSUFFICIENT for real; SUPPORTED_MATCH with ev-002 for demo |
| `test_malformed_and_oversized_payload_handling` | 422 with errors field; 413 for 40 KB body |
| `test_demo_scenarios_endpoint_labels_records_correctly` | demo-assessable=fictional+warning; demo-listing-only=REAL_STUB+no warning |
| `test_missing_and_malformed_data_files_fail_clearly` | SchemeValidationError with "not found" and "Malformed JSON" |

---

## 3. Retrieval Benchmark

```powershell
python -c "
from app.catalog import SchemeCatalogService
from app.retriever import evaluate_retrieval_benchmark
from pathlib import Path
catalog = SchemeCatalogService()
metrics = evaluate_retrieval_benchmark(catalog.retriever, Path('data/eval_queries.json'))
print(metrics)
"
```

**Measured results on 10-query synthetic benchmark:**

| Metric | Value |
|--------|-------|
| total_queries | 10 |
| supported_queries | 6 |
| refusal_queries | 4 |
| top1_accuracy | 1.0 |
| top3_recall | 1.0 |
| mean_reciprocal_rank | 1.0 |
| refusal_accuracy | 1.0 |

⚠️ **Honest caveat:** This is a small synthetic benchmark generated alongside the implementation. It does not constitute independent validation of retrieval accuracy on real government documents.

---

## 4. Known Testing Limitations

- **No headless browser automation**: Playwright/Selenium was not run. Frontend rendering at `393x852` and `1280x800` must be verified manually after starting the server.
- **No RAM measurement test**: No automated memory profiling was run; no RAM footprint claim is published.
- **Benchmark corpus is synthetic**: All 10 eval queries target the fictional demo evidence; real scheme retrieval is tested only for refusal behaviour.
- **Real scheme eligibility untested end-to-end**: Both real schemes remain `LISTING_ONLY` with no assessable rules, so API assessment returns `null` outcome by design.
