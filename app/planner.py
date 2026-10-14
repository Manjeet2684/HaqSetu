"""Deterministic dependency-aware action planner using standard-library graphlib.TopologicalSorter."""

from __future__ import annotations

from collections.abc import Iterable
from graphlib import CycleError, TopologicalSorter

from app.schemas import (
    ActionDefinition,
    ActionPlanItem,
    ActionStatus,
    ApplicantOutcome,
    SchemeReadiness,
    SchemeRecord,
)


class ActionPlanValidationError(ValueError):
    """Base exception for invalid action planner definitions."""


class UnknownPrerequisiteError(ActionPlanValidationError):
    """Raised when an action references a prerequisite action ID that does not exist."""


class DependencyCycleError(ActionPlanValidationError):
    """Raised when action prerequisites form a dependency cycle."""


def validate_action_graph(actions: Iterable[ActionDefinition]) -> list[ActionDefinition]:
    """
    Validate action uniqueness, unknown prerequisite IDs, and dependency cycles.

    Returns actions in a deterministic topological order that preserves declaration order
    as a tie-breaker among simultaneously ready nodes.
    """
    action_list = list(actions)
    if not action_list:
        return []

    by_id: dict[str, ActionDefinition] = {}
    declaration_index: dict[str, int] = {}

    for idx, action in enumerate(action_list):
        if action.id in by_id:
            raise ActionPlanValidationError(f"Duplicate action ID detected: '{action.id}'.")
        by_id[action.id] = action
        declaration_index[action.id] = idx

    for action in action_list:
        for prereq_id in action.prerequisites:
            if prereq_id not in by_id:
                raise UnknownPrerequisiteError(
                    f"Action '{action.id}' references unknown prerequisite ID '{prereq_id}'."
                )

    sorter: TopologicalSorter[str] = TopologicalSorter()
    for action in action_list:
        sorter.add(action.id, *action.prerequisites)

    try:
        sorter.prepare()
    except CycleError as exc:
        raise DependencyCycleError(
            f"Dependency cycle detected in action plan: {exc.args}"
        ) from exc

    ordered: list[ActionDefinition] = []
    while sorter.is_active():
        ready_ids = sorted(sorter.get_ready(), key=lambda aid: declaration_index[aid])
        for aid in ready_ids:
            ordered.append(by_id[aid])
            sorter.done(aid)

    return ordered


def _determine_safety_gate(
    scheme: SchemeRecord,
    action: ActionDefinition,
    outcome: ApplicantOutcome | None,
) -> str | None:
    """
    Return a non-empty gate_reason if a safety gate prohibits `action` from proceeding, else None.

    Safety gates always take precedence over user completion (`completed_action_ids`) and prerequisites.
    """
    is_gated_submission = action.is_submission or action.requires_eligible

    if scheme.readiness == SchemeReadiness.LISTING_ONLY or outcome is None:
        if is_gated_submission:
            return (
                "Gated: this scheme is LISTING_ONLY and has no verified eligibility outcome. "
                "Verify official guidelines on the portal before submitting an application."
            )

    if is_gated_submission:
        if outcome == ApplicantOutcome.INELIGIBLE:
            return (
                "Gated: preliminary assessment is INELIGIBLE based on verified mandatory conditions. "
                "Application submission is not recommended."
            )
        if outcome == ApplicantOutcome.NEEDS_VERIFICATION:
            return (
                "Gated: preliminary eligibility is NEEDS_VERIFICATION (one or more required "
                "conditions remain unresolved). Confirm eligibility before submitting."
            )

    if action.requires_open_window and scheme.application_window_open is False:
        return (
            "Gated: the official application window for this academic cycle is currently closed."
        )

    if action.requires_open_window and scheme.application_window_open is None:
        return (
            "Gated: the official application window dates have not yet been verified."
        )

    return None


def build_action_plan(
    scheme: SchemeRecord,
    outcome: ApplicantOutcome | None,
    completed_action_ids: Iterable[str] | None = None,
) -> list[ActionPlanItem]:
    """
    Build a deterministically ordered action plan with DONE, READY, BLOCKED, and GATED statuses.

    Rules enforced:
    1. Unknown prerequisite IDs raise `UnknownPrerequisiteError`.
    2. Dependency cycles raise `DependencyCycleError`.
    3. Safety gates (`GATED`) take strict priority: a completed action ID never bypasses an active
       eligibility, verification, listing-only, or application-window safety gate.
    4. Non-gated actions in `completed_action_ids` receive status `DONE`.
    5. Non-gated, non-completed actions with any prerequisite not in `DONE` state receive `BLOCKED`.
    6. Non-gated, non-completed actions whose prerequisites are all `DONE` receive `READY`.
    """
    ordered_actions = validate_action_graph(scheme.actions)
    if not ordered_actions:
        return []

    completed_set: set[str] = set(completed_action_ids or ())
    computed_statuses: dict[str, ActionStatus] = {}
    plan_items: list[ActionPlanItem] = []

    for action in ordered_actions:
        evidence = (
            scheme.evidence_registry.get(action.evidence_id)
            if action.evidence_id
            else None
        )
        gate_reason = _determine_safety_gate(scheme, action, outcome)

        if gate_reason is not None:
            status = ActionStatus.GATED
            status_reason = None
        elif action.id in completed_set:
            status = ActionStatus.DONE
            status_reason = "Marked complete by user."
        else:
            incomplete_prereqs = [
                prereq_id
                for prereq_id in action.prerequisites
                if computed_statuses.get(prereq_id) != ActionStatus.DONE
            ]
            if incomplete_prereqs:
                status = ActionStatus.BLOCKED
                status_reason = (
                    f"Blocked: prerequisite action(s) not yet complete: "
                    f"{', '.join(incomplete_prereqs)}."
                )
            else:
                status = ActionStatus.READY
                status_reason = (
                    "All prerequisites are satisfied. Ready to proceed."
                    if action.prerequisites
                    else "No prerequisites required. Ready to proceed."
                )

        computed_statuses[action.id] = status
        plan_items.append(
            ActionPlanItem(
                id=action.id,
                label=action.label,
                description=action.description,
                status=status,
                status_reason=status_reason,
                gate_reason=gate_reason,
                prerequisites=list(action.prerequisites),
                document_type=action.document_type,
                evidence_id=action.evidence_id,
                evidence=evidence,
                is_submission=action.is_submission,
            )
        )

    return plan_items
