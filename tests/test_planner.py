"""Comprehensive pytest suite for HaqSetu P3 dependency-aware action planner."""

from __future__ import annotations

import pytest

from app.planner import (
    DependencyCycleError,
    UnknownPrerequisiteError,
    build_action_plan,
)
from app.schemas import (
    ActionDefinition,
    ActionStatus,
    ApplicantOutcome,
    EvidenceReference,
    SchemeDataType,
    SchemeReadiness,
    SchemeRecord,
)


def _make_planner_scheme(
    actions: list[ActionDefinition],
    *,
    readiness: SchemeReadiness = SchemeReadiness.ASSESSABLE,
    window_open: bool | None = True,
) -> SchemeRecord:
    """Create a lightweight SchemeRecord configured with the supplied actions."""
    ev = EvidenceReference(
        id="ev-act-1",
        source_title="Official Portal Instructions",
        source_url="https://scholarships.gov.in",
        academic_cycle="2025-26",
        section_or_page="Section 7",
        excerpt="Applicants must complete OTR and upload income and mark sheets before submission.",
        access_date="2026-10-14",
        verified=True,
        verification_date="2026-10-14",
        verified_by="Auditor",
        fictional=False,
    )
    return SchemeRecord(
        id="planner-test-scheme",
        name="Planner Test Scheme",
        short_name="Planner Test",
        issuing_body="Ministry of Education",
        readiness=readiness,
        data_type=SchemeDataType.REAL_VERIFIED,
        is_fictional=False,
        application_window_open=window_open,
        actions=actions,
        evidence_registry={"ev-act-1": ev},
    )


def test_topological_prerequisite_ordering_and_states() -> None:
    """Planner orders actions topologically and assigns DONE, READY, BLOCKED, and GATED accurately."""
    actions = [
        ActionDefinition(
            id="act-submit",
            label="Submit application on official portal",
            prerequisites=["act-verify"],
            is_submission=True,
            requires_eligible=True,
            evidence_id="ev-act-1",
        ),
        ActionDefinition(
            id="act-verify",
            label="Verify documents with institute nodal officer",
            prerequisites=["act-income", "act-marksheet"],
        ),
        ActionDefinition(
            id="act-income",
            label="Obtain income certificate",
            prerequisites=[],
        ),
        ActionDefinition(
            id="act-marksheet",
            label="Collect attested mark sheet",
            prerequisites=[],
        ),
    ]
    scheme = _make_planner_scheme(actions)

    plan = build_action_plan(
        scheme,
        outcome=ApplicantOutcome.NEEDS_VERIFICATION,
        completed_action_ids=["act-marksheet"],
    )

    ordered_ids = [item.id for item in plan]
    assert ordered_ids.index("act-income") < ordered_ids.index("act-verify")
    assert ordered_ids.index("act-marksheet") < ordered_ids.index("act-verify")
    assert ordered_ids.index("act-verify") < ordered_ids.index("act-submit")

    by_id = {item.id: item for item in plan}
    assert by_id["act-marksheet"].status == ActionStatus.DONE
    assert by_id["act-income"].status == ActionStatus.READY
    assert by_id["act-verify"].status == ActionStatus.BLOCKED
    assert "act-income" in (by_id["act-verify"].status_reason or "")
    assert by_id["act-submit"].status == ActionStatus.GATED
    assert by_id["act-submit"].gate_reason is not None


def test_unknown_prerequisite_id_raises_explicit_error() -> None:
    """Unknown prerequisite IDs are caught explicitly before TopologicalSorter runs."""
    actions = [
        ActionDefinition(
            id="act-1",
            label="Upload certificate",
            prerequisites=["non-existent-action-id"],
        )
    ]
    scheme = _make_planner_scheme(actions)

    with pytest.raises(UnknownPrerequisiteError, match="non-existent-action-id"):
        build_action_plan(scheme, outcome=ApplicantOutcome.ELIGIBLE)


def test_dependency_cycle_raises_explicit_error() -> None:
    """Circular prerequisites raise DependencyCycleError."""
    actions = [
        ActionDefinition(
            id="act-a",
            label="Step A",
            prerequisites=["act-b"],
        ),
        ActionDefinition(
            id="act-b",
            label="Step B",
            prerequisites=["act-a"],
        ),
    ]
    scheme = _make_planner_scheme(actions)

    with pytest.raises(DependencyCycleError, match="Dependency cycle detected"):
        build_action_plan(scheme, outcome=ApplicantOutcome.ELIGIBLE)


@pytest.mark.parametrize(
    ("readiness", "outcome"),
    [
        (SchemeReadiness.ASSESSABLE, ApplicantOutcome.INELIGIBLE),
        (SchemeReadiness.ASSESSABLE, ApplicantOutcome.NEEDS_VERIFICATION),
        (SchemeReadiness.LISTING_ONLY, None),
    ],
)
def test_submission_gated_when_ineligible_unresolved_or_listing_only(
    readiness: SchemeReadiness,
    outcome: ApplicantOutcome | None,
) -> None:
    """Submission action is always GATED if outcome is INELIGIBLE, NEEDS_VERIFICATION, or LISTING_ONLY."""
    actions = [
        ActionDefinition(id="act-prep", label="Prepare documents", prerequisites=[]),
        ActionDefinition(
            id="act-submit-application",
            label="Submit application on portal",
            prerequisites=["act-prep"],
            is_submission=True,
            requires_eligible=True,
        ),
    ]
    scheme = _make_planner_scheme(actions, readiness=readiness)

    plan = build_action_plan(
        scheme,
        outcome=outcome,
        completed_action_ids=["act-prep"],
    )
    submit_item = next(item for item in plan if item.id == "act-submit-application")
    assert submit_item.status == ActionStatus.GATED
    assert submit_item.gate_reason is not None


def test_completed_actions_never_bypass_safety_gates() -> None:
    """Marking a gated action (or its prerequisites) as complete cannot bypass an active safety gate."""
    actions = [
        ActionDefinition(
            id="act-submit-application",
            label="Submit application on portal",
            prerequisites=[],
            is_submission=True,
            requires_eligible=True,
            requires_open_window=True,
        ),
        ActionDefinition(
            id="act-post-submit-receipt",
            label="Print submission receipt for nodal officer",
            prerequisites=["act-submit-application"],
        ),
    ]
    # Ineligible + window open: submission must be GATED; downstream must be BLOCKED
    scheme_ineligible = _make_planner_scheme(actions, window_open=True)
    plan_ineligible = build_action_plan(
        scheme_ineligible,
        outcome=ApplicantOutcome.INELIGIBLE,
        completed_action_ids=["act-submit-application"],
    )
    by_id_ineligible = {item.id: item for item in plan_ineligible}
    assert by_id_ineligible["act-submit-application"].status == ActionStatus.GATED
    assert by_id_ineligible["act-post-submit-receipt"].status == ActionStatus.BLOCKED

    # Eligible + window closed: submission gated by closed window
    scheme_closed = _make_planner_scheme(actions, window_open=False)
    plan_closed = build_action_plan(
        scheme_closed,
        outcome=ApplicantOutcome.ELIGIBLE,
        completed_action_ids=["act-submit-application"],
    )
    by_id_closed = {item.id: item for item in plan_closed}
    assert by_id_closed["act-submit-application"].status == ActionStatus.GATED
    assert "window" in (by_id_closed["act-submit-application"].gate_reason or "").lower()
