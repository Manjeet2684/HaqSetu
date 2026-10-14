"""Deterministic three-valued logic (Kleene logic) eligibility engine for HaqSetu."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.planner import build_action_plan
from app.schemas import (
    FICTIONAL_DEMO_WARNING,
    PRELIMINARY_GUIDANCE_DISCLAIMER,
    ApplicantOutcome,
    AssessmentResponse,
    ConditionAssessmentResult,
    ConditionResultStatus,
    EligibilityCondition,
    EligibilityPathway,
    EvidenceReference,
    PathwayAssessmentResult,
    RuleOperator,
    SchemeDataType,
    SchemeReadiness,
    SchemeRecord,
    validate_real_scheme_for_assessment,
)

_UNKNOWN_TOKENS: frozenset[str] = frozenset(
    {
        "",
        "unknown",
        "dont_know",
        "don't know",
        "do not know",
        "unsure",
        "not_sure",
        "n/a",
        "na",
        "null",
        "none",
        "unresolved",
    }
)


def _is_unknown_answer(value: Any) -> bool:
    """Return True if an answer is missing or explicitly marked as 'don't know' / unknown."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in _UNKNOWN_TOKENS:
        return True
    return False


def _resolve_evidence(
    scheme: SchemeRecord, condition: EligibilityCondition
) -> EvidenceReference | None:
    """Retrieve the EvidenceReference linked to a condition from inline data or the registry."""
    if condition.evidence is not None:
        return condition.evidence
    if condition.evidence_id is not None:
        return scheme.evidence_registry.get(condition.evidence_id)
    return None


def _lookup_answer(
    condition: EligibilityCondition, answers: Mapping[str, Any]
) -> tuple[bool, Any]:
    """
    Look up the user's submitted answer by question_id or condition.id.

    Never reads `condition.fixture_display_result` or `condition.fixture_user_answer`.
    """
    if condition.question_id and condition.question_id in answers:
        return True, answers[condition.question_id]
    if condition.id in answers:
        return True, answers[condition.id]
    return False, None


def _coerce_boolean(value: Any) -> bool | None:
    """Coerce common boolean or yes/no representations without guessing ambiguous strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1"}:
            return True
        if lowered in {"false", "no", "n", "0"}:
            return False
    return None


def _coerce_numeric(value: Any) -> float | None:
    """Safely convert int/float or numeric strings (excluding booleans) to float."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        import math
        f = float(value)
        if not math.isfinite(f):
            return None
        return f
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("\u20b9", "").replace("%", "")
        try:
            import math
            f = float(cleaned)
            if not math.isfinite(f):
                return None
            return f
        except ValueError:
            return None
    return None


def _apply_operator(
    operator: RuleOperator, actual_value: Any, expected_value: Any
) -> bool | None:
    """
    Evaluate `actual_value` against `expected_value` using `operator`.

    Returns True (satisfied), False (failed), or None (cannot be resolved safely).
    """
    if operator == RuleOperator.BOOL_TRUE:
        coerced = _coerce_boolean(actual_value)
        return None if coerced is None else (coerced is True)

    if operator == RuleOperator.BOOL_FALSE:
        coerced = _coerce_boolean(actual_value)
        return None if coerced is None else (coerced is False)

    if operator == RuleOperator.EQ:
        actual_bool = _coerce_boolean(actual_value)
        expected_bool = _coerce_boolean(expected_value)
        if actual_bool is not None and expected_bool is not None:
            return actual_bool == expected_bool
        actual_num = _coerce_numeric(actual_value)
        expected_num = _coerce_numeric(expected_value)
        if actual_num is not None and expected_num is not None:
            return actual_num == expected_num
        return actual_value == expected_value

    if operator == RuleOperator.NEQ:
        eq_res = _apply_operator(RuleOperator.EQ, actual_value, expected_value)
        return None if eq_res is None else (not eq_res)

    if operator in {RuleOperator.LTE, RuleOperator.LT, RuleOperator.GTE, RuleOperator.GT}:
        actual_num = _coerce_numeric(actual_value)
        expected_num = _coerce_numeric(expected_value)
        if actual_num is None or expected_num is None:
            return None
        if operator == RuleOperator.LTE:
            return actual_num <= expected_num
        if operator == RuleOperator.LT:
            return actual_num < expected_num
        if operator == RuleOperator.GTE:
            return actual_num >= expected_num
        return actual_num > expected_num

    if operator == RuleOperator.IN:
        if not isinstance(expected_value, (list, tuple, set, frozenset)):
            return None
        return actual_value in expected_value

    if operator == RuleOperator.NOT_IN:
        if not isinstance(expected_value, (list, tuple, set, frozenset)):
            return None
        return actual_value not in expected_value

    return None


def evaluate_condition(
    scheme: SchemeRecord,
    condition: EligibilityCondition,
    answers: Mapping[str, Any],
    *,
    pathway_id: str | None = None,
) -> ConditionAssessmentResult:
    """
    Evaluate a single condition against user answers using explicit three-valued logic.

    Optional/informational conditions always return `INFO_ONLY` so they never alter eligibility.
    Missing evidence on a mandatory condition forces `UNRESOLVED`.
    """
    evidence = _resolve_evidence(scheme, condition)
    found, raw_answer = _lookup_answer(condition, answers)

    if condition.is_optional or not condition.mandatory:
        if _is_unknown_answer(raw_answer) or not found:
            explanation = (
                f"Optional/informational condition '{condition.label}': no answer supplied "
                "(does not affect eligibility)."
            )
        else:
            mapped_val = (
                condition.value_aliases.get(str(raw_answer), raw_answer)
                if condition.value_aliases
                else raw_answer
            )
            matched = _apply_operator(condition.operator, mapped_val, condition.expected_value)
            note = "met" if matched is True else ("not met" if matched is False else "noted")
            explanation = (
                f"Optional/informational condition '{condition.label}' ({note}; "
                "does not affect eligibility outcome)."
            )
        return ConditionAssessmentResult(
            condition_id=condition.id,
            question_id=condition.question_id,
            pathway_id=pathway_id,
            label=condition.label,
            mandatory=False,
            is_optional=True,
            status=ConditionResultStatus.INFO_ONLY,
            submitted_answer=raw_answer if found else None,
            explanation=explanation,
            evidence_id=evidence.id if evidence else condition.evidence_id,
            evidence=evidence,
            is_fictional=scheme.is_fictional or bool(evidence and evidence.fictional),
        )

    if evidence is None:
        return ConditionAssessmentResult(
            condition_id=condition.id,
            question_id=condition.question_id,
            pathway_id=pathway_id,
            label=condition.label,
            mandatory=True,
            is_optional=False,
            status=ConditionResultStatus.UNRESOLVED,
            submitted_answer=raw_answer if found else None,
            explanation=(
                f"Condition '{condition.label}' cannot be verified because its supporting "
                "policy evidence reference is missing."
            ),
            evidence_id=condition.evidence_id,
            evidence=None,
            is_fictional=scheme.is_fictional,
        )

    if not scheme.is_fictional and (not evidence.verified or evidence.fictional):
        return ConditionAssessmentResult(
            condition_id=condition.id,
            question_id=condition.question_id,
            pathway_id=pathway_id,
            label=condition.label,
            mandatory=True,
            is_optional=False,
            status=ConditionResultStatus.UNRESOLVED,
            submitted_answer=raw_answer if found else None,
            explanation=(
                f"Condition '{condition.label}' is unresolved because its policy evidence "
                f"('{evidence.id}') has not been human-verified."
            ),
            evidence_id=evidence.id,
            evidence=evidence,
            is_fictional=scheme.is_fictional,
        )

    if not found or _is_unknown_answer(raw_answer):
        reason = (
            "Applicant selected 'Don't know'."
            if found and raw_answer is not None
            else "No answer provided."
        )
        return ConditionAssessmentResult(
            condition_id=condition.id,
            question_id=condition.question_id,
            pathway_id=pathway_id,
            label=condition.label,
            mandatory=True,
            is_optional=False,
            status=ConditionResultStatus.UNRESOLVED,
            submitted_answer=raw_answer if found else None,
            explanation=f"{reason} Verification required against {evidence.source_title}.",
            evidence_id=evidence.id,
            evidence=evidence,
            is_fictional=scheme.is_fictional or evidence.fictional,
        )

    mapped_answer = (
        condition.value_aliases.get(str(raw_answer), raw_answer)
        if condition.value_aliases and isinstance(raw_answer, str)
        else raw_answer
    )
    comparison = _apply_operator(condition.operator, mapped_answer, condition.expected_value)

    if comparison is None:
        return ConditionAssessmentResult(
            condition_id=condition.id,
            question_id=condition.question_id,
            pathway_id=pathway_id,
            label=condition.label,
            mandatory=True,
            is_optional=False,
            status=ConditionResultStatus.UNRESOLVED,
            submitted_answer=raw_answer,
            explanation=(
                f"Submitted answer {raw_answer!r} could not be compared deterministically "
                f"for '{condition.label}'. Manual verification required."
            ),
            evidence_id=evidence.id,
            evidence=evidence,
            is_fictional=scheme.is_fictional or evidence.fictional,
        )

    if comparison is True:
        return ConditionAssessmentResult(
            condition_id=condition.id,
            question_id=condition.question_id,
            pathway_id=pathway_id,
            label=condition.label,
            mandatory=True,
            is_optional=False,
            status=ConditionResultStatus.SATISFIED,
            submitted_answer=raw_answer,
            explanation=f"Meets condition '{condition.label}' (supported by {evidence.id}).",
            evidence_id=evidence.id,
            evidence=evidence,
            is_fictional=scheme.is_fictional or evidence.fictional,
        )

    return ConditionAssessmentResult(
        condition_id=condition.id,
        question_id=condition.question_id,
        pathway_id=pathway_id,
        label=condition.label,
        mandatory=True,
        is_optional=False,
        status=ConditionResultStatus.FAILED,
        submitted_answer=raw_answer,
        explanation=f"Does not meet mandatory condition '{condition.label}' (see {evidence.id}).",
        evidence_id=evidence.id,
        evidence=evidence,
        is_fictional=scheme.is_fictional or evidence.fictional,
    )


def _evaluate_pathway(
    scheme: SchemeRecord,
    pathway: EligibilityPathway,
    answers: Mapping[str, Any],
) -> PathwayAssessmentResult:
    """
    Evaluate all conditions in a single pathway using three-valued AND logic.

    - All mandatory conditions SATISFIED -> pathway SATISFIED
    - At least one mandatory condition FAILED -> pathway FAILED
    - No mandatory condition FAILED and at least one UNRESOLVED -> pathway UNRESOLVED
    """
    cond_results: list[ConditionAssessmentResult] = [
        evaluate_condition(scheme, cond, answers, pathway_id=pathway.id)
        for cond in pathway.conditions
    ]
    mandatory_results = [r for r in cond_results if r.mandatory and not r.is_optional]

    if not mandatory_results:
        return PathwayAssessmentResult(
            pathway_id=pathway.id,
            label=pathway.label,
            status=ConditionResultStatus.UNRESOLVED,
            condition_results=cond_results,
            explanation=f"Pathway '{pathway.label}' has no mandatory conditions configured.",
        )

    has_failure = any(r.status == ConditionResultStatus.FAILED for r in mandatory_results)
    has_unresolved = any(
        r.status == ConditionResultStatus.UNRESOLVED for r in mandatory_results
    )

    if has_failure:
        status = ConditionResultStatus.FAILED
        explanation = (
            f"Pathway '{pathway.label}' failed because at least one mandatory condition failed."
        )
    elif has_unresolved:
        status = ConditionResultStatus.UNRESOLVED
        explanation = (
            f"Pathway '{pathway.label}' needs verification because one or more mandatory "
            "conditions are unresolved."
        )
    else:
        status = ConditionResultStatus.SATISFIED
        explanation = (
            f"Pathway '{pathway.label}' satisfied all {len(mandatory_results)} mandatory conditions."
        )

    return PathwayAssessmentResult(
        pathway_id=pathway.id,
        label=pathway.label,
        status=status,
        condition_results=cond_results,
        explanation=explanation,
    )


def evaluate_scheme(
    scheme: SchemeRecord,
    answers: Mapping[str, Any] | None = None,
    *,
    completed_action_ids: list[str] | set[str] | None = None,
) -> AssessmentResponse:
    """
    Deterministically evaluate applicant eligibility and build the ordered action plan.

    Enforces all 12 critical aggregation rules:
    - Real schemes lacking full human verification or valid evidence fail closed to LISTING_ONLY.
    - Evaluates all global conditions, pathways, and optional conditions without early return.
    - A failed global mandatory condition is NEVER overridden by a passing pathway.
    - Non-exhaustive pathways (pathways_exhaustive=False) return NEEDS_VERIFICATION instead of
      INELIGIBLE when modelled pathways fail.
    - Optional conditions never alter the eligibility outcome.
    - Fictional fixtures always carry an explicit fictional-demo warning.

    Aggregation priority order (highest to lowest):
    1. global_failed + exhaustive  -> INELIGIBLE
    2. global_failed + non-exhaust -> NEEDS_VERIFICATION
    3. all_pathways_failed + exhaust -> INELIGIBLE
    4. all_pathways_failed + non-exhaust -> NEEDS_VERIFICATION
    5. global_unresolved           -> NEEDS_VERIFICATION
    6. any_pathway_satisfied       -> ELIGIBLE
    7. any_pathway_unresolved      -> NEEDS_VERIFICATION
    8. fallback                    -> NEEDS_VERIFICATION
    """
    answer_map: Mapping[str, Any] = answers or {}
    safeguard_warnings: list[str] = []
    fictional_warning = FICTIONAL_DEMO_WARNING if scheme.is_fictional else None
    disclaimer = (
        f"{FICTIONAL_DEMO_WARNING} {PRELIMINARY_GUIDANCE_DISCLAIMER}"
        if scheme.is_fictional
        else PRELIMINARY_GUIDANCE_DISCLAIMER
    )

    effective_readiness = scheme.readiness
    if not scheme.is_fictional and scheme.readiness == SchemeReadiness.ASSESSABLE:
        validation_errors = validate_real_scheme_for_assessment(scheme)
        if validation_errors:
            effective_readiness = SchemeReadiness.LISTING_ONLY
            safeguard_warnings.extend(validation_errors)

    if effective_readiness == SchemeReadiness.LISTING_ONLY:
        action_plan = build_action_plan(
            scheme, outcome=None, completed_action_ids=completed_action_ids
        )
        summary = (
            "Scheme is LISTING_ONLY: official eligibility rules have not been verified for "
            "automated assessment. Please check the official scholarship portal directly."
        )
        return AssessmentResponse(
            scheme_id=scheme.id,
            scheme_name=scheme.name,
            readiness=scheme.readiness,
            effective_readiness=SchemeReadiness.LISTING_ONLY,
            data_type=scheme.data_type,
            is_fictional=scheme.is_fictional,
            fictional_warning=fictional_warning,
            disclaimer=disclaimer,
            applicant_outcome=None,
            summary=summary,
            global_condition_results=[],
            pathway_results=[],
            optional_condition_results=[],
            condition_results=[],
            action_plan=action_plan,
            safeguard_warnings=safeguard_warnings,
        )

    global_results: list[ConditionAssessmentResult] = [
        evaluate_condition(scheme, cond, answer_map, pathway_id=None)
        for cond in scheme.global_conditions
    ]
    pathway_results: list[PathwayAssessmentResult] = [
        _evaluate_pathway(scheme, pathway, answer_map) for pathway in scheme.pathways
    ]
    optional_results: list[ConditionAssessmentResult] = [
        evaluate_condition(
            scheme,
            cond.model_copy(update={"mandatory": False, "is_optional": True}),
            answer_map,
            pathway_id=None,
        )
        for cond in scheme.optional_conditions
    ]

    all_condition_results: list[ConditionAssessmentResult] = [
        *global_results,
        *(cr for pr in pathway_results for cr in pr.condition_results),
        *optional_results,
    ]

    mandatory_global = [r for r in global_results if r.mandatory and not r.is_optional]
    global_failed = any(r.status == ConditionResultStatus.FAILED for r in mandatory_global)
    global_unresolved = any(
        r.status == ConditionResultStatus.UNRESOLVED for r in mandatory_global
    )

    if pathway_results:
        any_pathway_satisfied = any(
            pr.status == ConditionResultStatus.SATISFIED for pr in pathway_results
        )
        any_pathway_unresolved = any(
            pr.status == ConditionResultStatus.UNRESOLVED for pr in pathway_results
        )
        all_pathways_failed = all(
            pr.status == ConditionResultStatus.FAILED for pr in pathway_results
        )
    else:
        any_pathway_satisfied = bool(mandatory_global)
        any_pathway_unresolved = False
        all_pathways_failed = False

    # Determine outcome using the documented priority order.
    # global_failed takes strict precedence — a failing global mandatory exclusion
    # cannot be overridden by any passing pathway.
    if not mandatory_global and not pathway_results:
        outcome = ApplicantOutcome.NEEDS_VERIFICATION
        summary = "No mandatory conditions or pathways were evaluated; verification required."
    elif global_failed:
        if scheme.pathways_exhaustive:
            outcome = ApplicantOutcome.INELIGIBLE
            summary = (
                "Based on your answers, a mandatory scheme-wide eligibility condition was not met. "
                "Preliminary assessment: INELIGIBLE."
            )
        else:
            outcome = ApplicantOutcome.NEEDS_VERIFICATION
            summary = (
                "A mandatory condition was not met, but modelled rules are not marked exhaustive. "
                "Preliminary assessment: NEEDS_VERIFICATION."
            )
    elif all_pathways_failed and pathway_results:
        if scheme.pathways_exhaustive:
            outcome = ApplicantOutcome.INELIGIBLE
            summary = (
                "Based on your answers, none of the exhaustive eligibility pathways were satisfied. "
                "Preliminary assessment: INELIGIBLE."
            )
        else:
            outcome = ApplicantOutcome.NEEDS_VERIFICATION
            summary = (
                "Based on your answers, modelled pathway conditions were not satisfied, "
                "but pathways are not marked exhaustive. Preliminary assessment: NEEDS_VERIFICATION."
            )
    elif global_unresolved:
        outcome = ApplicantOutcome.NEEDS_VERIFICATION
        summary = (
            "Based on your answers, one or more universal eligibility conditions require verification. "
            "Preliminary assessment: NEEDS_VERIFICATION."
        )
    elif any_pathway_satisfied:
        outcome = ApplicantOutcome.ELIGIBLE
        summary = (
            "Based on your answers, all verified mandatory conditions for an eligible pathway "
            "are satisfied — preliminary assessment: ELIGIBLE."
        )
    elif any_pathway_unresolved:
        outcome = ApplicantOutcome.NEEDS_VERIFICATION
        summary = (
            "Based on your answers, one or more required pathway conditions remain unresolved. "
            "Preliminary assessment: NEEDS_VERIFICATION."
        )
    else:
        outcome = ApplicantOutcome.NEEDS_VERIFICATION
        summary = "Preliminary assessment requires additional verification."

    action_plan = build_action_plan(
        scheme,
        outcome=outcome,
        completed_action_ids=completed_action_ids,
    )

    return AssessmentResponse(
        scheme_id=scheme.id,
        scheme_name=scheme.name,
        readiness=scheme.readiness,
        effective_readiness=effective_readiness,
        data_type=scheme.data_type,
        is_fictional=scheme.is_fictional,
        fictional_warning=fictional_warning,
        disclaimer=disclaimer,
        applicant_outcome=outcome,
        summary=summary,
        global_condition_results=global_results,
        pathway_results=pathway_results,
        optional_condition_results=optional_results,
        condition_results=all_condition_results,
        action_plan=action_plan,
        safeguard_warnings=safeguard_warnings,
    )


def assess_scheme(
    scheme: SchemeRecord,
    answers: Mapping[str, Any] | None = None,
    completed_action_ids: list[str] | set[str] | None = None,
) -> AssessmentResponse:
    """Convenience alias for `evaluate_scheme`."""
    return evaluate_scheme(
        scheme=scheme,
        answers=answers,
        completed_action_ids=completed_action_ids,
    )
