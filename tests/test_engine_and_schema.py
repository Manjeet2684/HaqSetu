"""Comprehensive pytest suite for HaqSetu P2 schemas, data compatibility, and eligibility engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.engine import evaluate_scheme
from app.schemas import (
    ActionDefinition,
    ApplicantOutcome,
    ConditionResultStatus,
    EligibilityCondition,
    EligibilityPathway,
    EvidenceReference,
    RuleOperator,
    SchemeDataType,
    SchemeReadiness,
    SchemeRecord,
    load_demo_fixtures,
    load_real_schemes,
    normalize_condition_result,
    validate_real_scheme_for_assessment,
    validate_scheme_catalog,
)


def _make_verified_evidence(ev_id: str = "ev-verified-1", cycle: str = "2025-26") -> EvidenceReference:
    """Create a complete, verified official EvidenceReference for unit tests."""
    return EvidenceReference(
        id=ev_id,
        source_title="Ministry of Education CSSS Guidelines",
        source_url="https://scholarships.gov.in/public/schemeGuidelines/FAQ_DOHE_CSSS.pdf",
        academic_cycle=cycle,
        section_or_page="Section 4, Page 2",
        excerpt="Parental income from all sources must not exceed Rs. 4,50,000 per annum.",
        access_date="2026-10-14",
        verified=True,
        verification_date="2026-10-14",
        verified_by="Human Reviewer",
        fictional=False,
    )


def _make_verified_real_scheme(
    *,
    pathways_exhaustive: bool = True,
    global_conditions: list[EligibilityCondition] | None = None,
    pathways: list[EligibilityPathway] | None = None,
    optional_conditions: list[EligibilityCondition] | None = None,
) -> SchemeRecord:
    """Build a fully verified assessable real SchemeRecord for unit testing."""
    ev1 = _make_verified_evidence("ev-1")
    ev2 = _make_verified_evidence("ev-2")
    ev3 = _make_verified_evidence("ev-3")

    default_global = [
        EligibilityCondition(
            id="glob-no-other-scholarship",
            question_id="q-other-scholarship",
            label="Not receiving any other central scholarship",
            operator=RuleOperator.BOOL_FALSE,
            expected_value=False,
            mandatory=True,
            evidence_id="ev-1",
            evidence=ev1,
        )
    ]
    default_pathways = [
        EligibilityPathway(
            id="path-merit",
            label="Standard Merit Pathway",
            conditions=[
                EligibilityCondition(
                    id="cond-marks",
                    question_id="q-marks",
                    label="Class 12 score at least 80%",
                    operator=RuleOperator.GTE,
                    expected_value=80,
                    mandatory=True,
                    evidence_id="ev-2",
                    evidence=ev2,
                ),
                EligibilityCondition(
                    id="cond-income",
                    question_id="q-income",
                    label="Annual family income up to 450000",
                    operator=RuleOperator.LTE,
                    expected_value=450000,
                    mandatory=True,
                    evidence_id="ev-3",
                    evidence=ev3,
                ),
            ],
        )
    ]

    return SchemeRecord(
        id="verified-test-scheme",
        name="Verified Test Scholarship",
        short_name="Verified Test",
        issuing_body="Ministry of Education",
        portal_url="https://scholarships.gov.in",
        readiness=SchemeReadiness.ASSESSABLE,
        data_type=SchemeDataType.REAL_VERIFIED,
        is_fictional=False,
        academic_year_verified="2025-26",
        official_source_url="https://scholarships.gov.in/public/schemeGuidelines/FAQ_DOHE_CSSS.pdf",
        official_source_inspected=True,
        human_verified=True,
        verified_by="Human Policy Auditor",
        verification_date="2026-10-14",
        pathways_exhaustive=pathways_exhaustive,
        application_window_open=True,
        global_conditions=default_global if global_conditions is None else global_conditions,
        pathways=default_pathways if pathways is None else pathways,
        optional_conditions=optional_conditions or [],
        actions=[
            ActionDefinition(
                id="act-submit",
                label="Submit application on NSP",
                is_submission=True,
                requires_eligible=True,
                evidence_id="ev-1",
            )
        ],
        evidence_registry={"ev-1": ev1, "ev-2": ev2, "ev-3": ev3},
    )


def test_normalize_legacy_fixture_condition_results() -> None:
    """Fixture tokens PASS, FAIL, and NEEDS_VERIFICATION normalize safely to canonical statuses."""
    assert normalize_condition_result("PASS") == ConditionResultStatus.SATISFIED
    assert normalize_condition_result("FAIL") == ConditionResultStatus.FAILED
    assert normalize_condition_result("NEEDS_VERIFICATION") == ConditionResultStatus.UNRESOLVED
    assert normalize_condition_result("INFO_ONLY") == ConditionResultStatus.INFO_ONLY
    assert normalize_condition_result(None) is None
    with pytest.raises(ValueError, match="Unsupported condition result token"):
        normalize_condition_result("INVALID_TOKEN")


def test_numeric_threshold_boundaries_both_sides() -> None:
    """Numeric operators LTE and GTE evaluate exact boundary, passing side, and failing side accurately."""
    scheme = _make_verified_real_scheme()

    res_exact = evaluate_scheme(
        scheme,
        {"q-other-scholarship": False, "q-marks": 80, "q-income": 450000},
    )
    assert res_exact.applicant_outcome == ApplicantOutcome.ELIGIBLE

    res_low_marks = evaluate_scheme(
        scheme,
        {"q-other-scholarship": False, "q-marks": 79.9, "q-income": 450000},
    )
    assert res_low_marks.applicant_outcome == ApplicantOutcome.INELIGIBLE

    res_high_income = evaluate_scheme(
        scheme,
        {"q-other-scholarship": False, "q-marks": 80, "q-income": 450001},
    )
    assert res_high_income.applicant_outcome == ApplicantOutcome.INELIGIBLE


def test_missing_and_dont_know_answers_never_treated_as_passing() -> None:
    """Missing answers and explicit 'don't know' variants produce UNRESOLVED and NEEDS_VERIFICATION."""
    scheme = _make_verified_real_scheme()

    res_missing = evaluate_scheme(
        scheme,
        {"q-other-scholarship": False, "q-marks": 85},
    )
    assert res_missing.applicant_outcome == ApplicantOutcome.NEEDS_VERIFICATION
    income_cond = next(c for c in res_missing.condition_results if c.condition_id == "cond-income")
    assert income_cond.status == ConditionResultStatus.UNRESOLVED

    for token in ("unknown", "Don't know", "dont_know", ""):
        res_unknown = evaluate_scheme(
            scheme,
            {"q-other-scholarship": False, "q-marks": 85, "q-income": token},
        )
        assert res_unknown.applicant_outcome == ApplicantOutcome.NEEDS_VERIFICATION


def test_or_pathways_one_passing_one_failing_succeeds() -> None:
    """When one pathway fails and an alternative pathway passes (and global rules pass), outcome is ELIGIBLE."""
    ev1 = _make_verified_evidence("ev-1")
    path_a = EligibilityPathway(
        id="path-a",
        label="Merit Stream",
        conditions=[
            EligibilityCondition(
                id="cond-merit",
                question_id="q-marks",
                label="Marks >= 85%",
                operator=RuleOperator.GTE,
                expected_value=85,
                evidence_id="ev-1",
                evidence=ev1,
            )
        ],
    )
    path_b = EligibilityPathway(
        id="path-b",
        label="Sports Quota Stream",
        conditions=[
            EligibilityCondition(
                id="cond-sports",
                question_id="q-sports",
                label="National level sports certificate",
                operator=RuleOperator.BOOL_TRUE,
                expected_value=True,
                evidence_id="ev-1",
                evidence=ev1,
            )
        ],
    )
    scheme = _make_verified_real_scheme(pathways=[path_a, path_b])

    res = evaluate_scheme(
        scheme,
        {"q-other-scholarship": False, "q-marks": 72, "q-sports": True},
    )
    assert res.applicant_outcome == ApplicantOutcome.ELIGIBLE
    assert res.pathway_results[0].status == ConditionResultStatus.FAILED
    assert res.pathway_results[1].status == ConditionResultStatus.SATISFIED


def test_global_mandatory_failure_overrides_passing_pathway() -> None:
    """A failed global mandatory condition cannot be overridden by a passing pathway."""
    scheme = _make_verified_real_scheme(pathways_exhaustive=True)
    res = evaluate_scheme(
        scheme,
        {
            "q-other-scholarship": True,
            "q-marks": 95,
            "q-income": 200000,
        },
    )
    assert res.pathway_results[0].status == ConditionResultStatus.SATISFIED
    assert res.global_condition_results[0].status == ConditionResultStatus.FAILED
    assert res.applicant_outcome == ApplicantOutcome.INELIGIBLE


def test_global_unresolved_does_not_short_circuit_pathway_evaluation() -> None:
    """Even when a global condition is unresolved, all pathways are still evaluated.

    Case A: global=UNRESOLVED, pathway=SATISFIED, exhaustive=True
        -> global_failed is False, all_pathways_failed is False, global_unresolved fires
        -> outcome = NEEDS_VERIFICATION (global uncertainty overrides pathway pass)

    Case B: global=UNRESOLVED, pathway=FAILED, exhaustive=True
        -> global_failed is False, all_pathways_failed=True + exhaustive=True fires
        -> outcome = INELIGIBLE (exhaustive pathways all fail)
    """
    scheme = _make_verified_real_scheme(pathways_exhaustive=True)

    # Case A: pathway passes but global is unresolved
    res_pass_path = evaluate_scheme(
        scheme,
        {"q-other-scholarship": "unknown", "q-marks": 90, "q-income": 300000},
    )
    assert len(res_pass_path.pathway_results) == 1
    assert res_pass_path.pathway_results[0].status == ConditionResultStatus.SATISFIED
    assert res_pass_path.applicant_outcome == ApplicantOutcome.NEEDS_VERIFICATION

    # Case B: pathway fails, exhaustive — outcome must be INELIGIBLE
    res_fail_path = evaluate_scheme(
        scheme,
        {"q-other-scholarship": "unknown", "q-marks": 60, "q-income": 300000},
    )
    assert res_fail_path.pathway_results[0].status == ConditionResultStatus.FAILED
    assert res_fail_path.applicant_outcome == ApplicantOutcome.INELIGIBLE


def test_non_exhaustive_pathways_never_produce_unjustified_ineligible() -> None:
    """When pathways_exhaustive=False, failing all modelled pathways returns NEEDS_VERIFICATION."""
    scheme = _make_verified_real_scheme(pathways_exhaustive=False)
    res = evaluate_scheme(
        scheme,
        {"q-other-scholarship": False, "q-marks": 55, "q-income": 800000},
    )
    assert res.pathway_results[0].status == ConditionResultStatus.FAILED
    assert res.applicant_outcome == ApplicantOutcome.NEEDS_VERIFICATION


def test_optional_conditions_never_flip_eligibility_outcome() -> None:
    """Optional/informational conditions are marked INFO_ONLY and never alter the verdict."""
    ev = _make_verified_evidence("ev-1")
    opt_cond = EligibilityCondition(
        id="opt-bank-seeded",
        question_id="q-bank-seeded",
        label="Aadhaar seeded with bank account for DBT",
        operator=RuleOperator.BOOL_TRUE,
        expected_value=True,
        mandatory=False,
        is_optional=True,
        evidence_id="ev-1",
        evidence=ev,
    )
    scheme = _make_verified_real_scheme(optional_conditions=[opt_cond])

    res = evaluate_scheme(
        scheme,
        {
            "q-other-scholarship": False,
            "q-marks": 88,
            "q-income": 250000,
            "q-bank-seeded": False,
        },
    )
    assert res.applicant_outcome == ApplicantOutcome.ELIGIBLE
    assert len(res.optional_condition_results) == 1
    assert res.optional_condition_results[0].status == ConditionResultStatus.INFO_ONLY


def test_listing_only_produces_null_outcome() -> None:
    """LISTING_ONLY schemes must always return applicant_outcome=None."""
    scheme = _make_verified_real_scheme()
    scheme.readiness = SchemeReadiness.LISTING_ONLY

    res = evaluate_scheme(
        scheme,
        {"q-other-scholarship": False, "q-marks": 95, "q-income": 100000},
    )
    assert res.effective_readiness == SchemeReadiness.LISTING_ONLY
    assert res.applicant_outcome is None


def test_incomplete_or_unverified_real_scheme_fails_closed() -> None:
    """Setting human_verified=True without reviewer/evidence/official URL fails closed to LISTING_ONLY."""
    scheme = _make_verified_real_scheme()
    scheme.verified_by = None
    scheme.official_source_url = None

    errors = validate_real_scheme_for_assessment(scheme)
    assert any("verified_by" in e for e in errors)
    assert any("official_source_url" in e for e in errors)

    res = evaluate_scheme(
        scheme,
        {"q-other-scholarship": False, "q-marks": 95, "q-income": 100000},
    )
    assert res.effective_readiness == SchemeReadiness.LISTING_ONLY
    assert res.applicant_outcome is None
    assert len(res.safeguard_warnings) >= 2


def test_real_schemes_and_demo_fixtures_compatibility_and_separation() -> None:
    """Verify exact compatibility with existing data/schemes.json and data/fixtures/demo.json."""
    repo_root = Path(__file__).resolve().parent.parent
    schemes_path = repo_root / "data" / "schemes.json"
    demo_path = repo_root / "data" / "fixtures" / "demo.json"

    if schemes_path.exists():
        real_schemes = load_real_schemes(schemes_path)
        assert len(real_schemes) == 2
        assert all(s.readiness == SchemeReadiness.LISTING_ONLY for s in real_schemes)
        assert all(not s.is_fictional for s in real_schemes)
        assert validate_scheme_catalog(real_schemes, allow_fictional=False) == []
        for s in real_schemes:
            res = evaluate_scheme(s, {"q-marks": "above_80"})
            assert res.applicant_outcome is None

    if demo_path.exists():
        demo_scenarios = load_demo_fixtures(demo_path)
        assert len(demo_scenarios) == 2
        assessable_demo = next(s for s in demo_scenarios if s.id == "demo-assessable")
        listing_demo = next(s for s in demo_scenarios if s.id == "demo-listing-only")

        assert assessable_demo.is_fictional is True
        assert assessable_demo.data_type == SchemeDataType.FICTIONAL_FIXTURE
        # REAL_STUB demo scenario must NOT be marked fictional
        assert listing_demo.is_fictional is False
        assert listing_demo.data_type == SchemeDataType.REAL_STUB
        assert listing_demo.readiness == SchemeReadiness.LISTING_ONLY

        catalog_errors = validate_scheme_catalog([assessable_demo], allow_fictional=False)
        assert any("Fictional scheme" in err for err in catalog_errors)

        res_eligible = evaluate_scheme(
            assessable_demo,
            {
                "q-marks": "above_80",
                "q-income": "below_450000",
                "q-enrollment": "yes",
                "q-other-scholarship": "no",
            },
        )
        assert res_eligible.applicant_outcome == ApplicantOutcome.ELIGIBLE
        assert res_eligible.is_fictional is True
        assert res_eligible.fictional_warning is not None
        assert "FICTIONAL" in res_eligible.fictional_warning
