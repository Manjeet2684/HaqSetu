"""Pydantic v2 models, normalization helpers, fail-closed validators, and P4/P5 API contracts."""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FICTIONAL_DEMO_WARNING = (
    "FICTIONAL DEMO WARNING: This scenario uses entirely invented rules, conditions, "
    "evidence, and synthetic persona data to demonstrate the interface only. "
    "Nothing here represents official government scholarship policy."
)

PRELIMINARY_GUIDANCE_DISCLAIMER = (
    "Based on your answers, this is a preliminary assessment only. "
    "The issuing government authority makes all official eligibility decisions."
)

RETRIEVAL_METHOD_DISCLAIMER = (
    "Source-grounded lexical/TF-IDF passage retrieval over recorded policy clauses. "
    "This is not a trained machine-learning classifier or generative LLM, and retrieved "
    "passages never determine applicant eligibility."
)


class SchemeValidationError(ValueError):
    """Raised when a scheme configuration or evidence chain fails integrity validation."""


class SchemeReadiness(StrEnum):
    """Indicates whether a scheme has verified rules ready for assessment or is a listing stub."""

    ASSESSABLE = "ASSESSABLE"
    LISTING_ONLY = "LISTING_ONLY"


class ApplicantOutcome(StrEnum):
    """Three-state applicant eligibility outcome for an assessable scheme."""

    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"


class ConditionResultStatus(StrEnum):
    """Normalized condition-level evaluation status."""

    SATISFIED = "SATISFIED"
    FAILED = "FAILED"
    UNRESOLVED = "UNRESOLVED"
    INFO_ONLY = "INFO_ONLY"


class ActionStatus(StrEnum):
    """Dependency-aware and safety-gated action planner status."""

    DONE = "DONE"
    READY = "READY"
    BLOCKED = "BLOCKED"
    GATED = "GATED"


class RuleOperator(StrEnum):
    """Deterministic comparison operators supported by the eligibility engine."""

    EQ = "eq"
    NEQ = "neq"
    LTE = "lte"
    LT = "lt"
    GTE = "gte"
    GT = "gt"
    IN = "in"
    NOT_IN = "not_in"
    BOOL_TRUE = "bool_true"
    BOOL_FALSE = "bool_false"


class SchemeDataType(StrEnum):
    """Origin classification separating real catalogues from fictional demo fixtures."""

    REAL_STUB = "REAL_STUB"
    REAL_VERIFIED = "REAL_VERIFIED"
    FICTIONAL_FIXTURE = "FICTIONAL_FIXTURE"


class RetrievalStatus(StrEnum):
    """Outcome status for source-grounded policy Q&A retrieval."""

    SUPPORTED_MATCH = "SUPPORTED_MATCH"
    NO_RELEVANT_MATCH = "NO_RELEVANT_MATCH"
    INSUFFICIENT_VERIFIED_EVIDENCE = "INSUFFICIENT_VERIFIED_EVIDENCE"


_LEGACY_CONDITION_RESULT_MAP: dict[str, ConditionResultStatus] = {
    "PASS": ConditionResultStatus.SATISFIED,
    "SATISFIED": ConditionResultStatus.SATISFIED,
    "FAIL": ConditionResultStatus.FAILED,
    "FAILED": ConditionResultStatus.FAILED,
    "NEEDS_VERIFICATION": ConditionResultStatus.UNRESOLVED,
    "UNRESOLVED": ConditionResultStatus.UNRESOLVED,
    "INFO_ONLY": ConditionResultStatus.INFO_ONLY,
}


def normalize_condition_result(
    raw_value: str | ConditionResultStatus | None,
) -> ConditionResultStatus | None:
    """Safely normalize P1 fixture result tokens (PASS/FAIL/NEEDS_VERIFICATION) to canonical statuses."""
    if raw_value is None:
        return None
    if isinstance(raw_value, ConditionResultStatus):
        return raw_value
    cleaned = str(raw_value).strip().upper()
    if cleaned not in _LEGACY_CONDITION_RESULT_MAP:
        raise ValueError(f"Unsupported condition result token: {raw_value!r}")
    return _LEGACY_CONDITION_RESULT_MAP[cleaned]


class EvidenceReference(BaseModel):
    """Traceable policy evidence backing an eligibility rule, document, or gated action."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    source_title: str = Field(..., min_length=1)
    source_url: str | None = None
    academic_cycle: str | None = None
    section_or_page: str | None = None
    excerpt: str = Field(..., min_length=1)
    access_date: str | None = None
    verified: bool = False
    verification_date: str | None = None
    verified_by: str | None = None
    fictional: bool = False


class EligibilityCondition(BaseModel):
    """Single deterministic eligibility condition linked to a question and policy evidence."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    question_id: str | None = None
    label: str = Field(..., min_length=1)
    operator: RuleOperator = RuleOperator.EQ
    expected_value: Any = True
    mandatory: bool = True
    is_optional: bool = False
    evidence_id: str | None = None
    evidence: EvidenceReference | None = None
    value_aliases: dict[str, Any] = Field(default_factory=dict)
    fixture_display_result: ConditionResultStatus | None = None
    fixture_user_answer: str | None = None

    @field_validator("fixture_display_result", mode="before")
    @classmethod
    def _normalize_fixture_result(cls, value: Any) -> ConditionResultStatus | None:
        return normalize_condition_result(value)

    @model_validator(mode="after")
    def _sync_mandatory_and_optional(self) -> EligibilityCondition:
        if self.is_optional:
            self.mandatory = False
        elif not self.mandatory:
            self.is_optional = True
        if self.evidence is not None and self.evidence_id is None:
            self.evidence_id = self.evidence.id
        return self


class EligibilityPathway(BaseModel):
    """A pathway of conditions evaluated with AND logic; multiple pathways combine via OR logic."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    conditions: list[EligibilityCondition] = Field(default_factory=list)
    fixture_display_result: ConditionResultStatus | None = None

    @field_validator("fixture_display_result", mode="before")
    @classmethod
    def _normalize_pathway_fixture_result(cls, value: Any) -> ConditionResultStatus | None:
        return normalize_condition_result(value)


class ActionDefinition(BaseModel):
    """Action node in a scheme's dependency-aware workflow graph."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    description: str | None = None
    prerequisites: list[str] = Field(default_factory=list)
    evidence_id: str | None = None
    document_type: str | None = None
    is_submission: bool = False
    requires_eligible: bool = False
    requires_open_window: bool = False
    channel: str | None = None
    fixture_default_status: ActionStatus | None = None
    fixture_status_reason: str | None = None
    fixture_gate_reason: str | None = None

    @model_validator(mode="after")
    def _infer_submission_flag(self) -> ActionDefinition:
        lower_label = self.label.lower()
        # Infer submission only from the label starting with "submit" or containing
        # "submit application", NOT from the action ID. Checking the ID risks false
        # positives on compound IDs like "act-post-submit-receipt".
        if lower_label.startswith("submit") or "submit application" in lower_label:
            self.is_submission = True
            self.requires_eligible = True
        return self


class QuestionnaireOption(BaseModel):
    """Single selectable option in a questionnaire item."""

    model_config = ConfigDict(extra="forbid")

    value: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)


class QuestionnaireItem(BaseModel):
    """Frontend-compatible question item mapped to a condition ID."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)
    type: str = "radio"
    options: list[QuestionnaireOption] = Field(default_factory=list)
    demo_answer: str | None = None
    links_to_condition: str | None = None


class SupportChannelInfo(BaseModel):
    """Official application, helpdesk, or grievance channel metadata with traceable source."""

    model_config = ConfigDict(extra="forbid")

    channel_type: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    official_url: str | None = None
    contact_detail: str | None = None
    hours_or_sla: str | None = None
    source_note: str = Field(..., min_length=1)
    # Only True when this channel has a specific backing source_note; default False
    # to avoid auto-marking every default as verified.
    verified_portal_fact: bool = False


class SchemeRecord(BaseModel):
    """Canonical representation of either a real scholarship scheme or an explicit demo fixture."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    short_name: str = Field(..., min_length=1)
    issuing_body: str = Field(..., min_length=1)
    portal_url: str | None = None
    readiness: SchemeReadiness = SchemeReadiness.LISTING_ONLY
    data_type: SchemeDataType = SchemeDataType.REAL_STUB
    is_fictional: bool = False
    fixture_notice: str | None = None
    verification_note: str | None = None
    academic_year: str | None = None
    academic_year_verified: str | None = None
    official_source_url: str | None = None
    official_source_inspected: bool = False
    human_verified: bool = False
    verified_by: str | None = None
    verification_date: str | None = None
    rules_stale_or_conflicting: bool = False
    pathways_exhaustive: bool = False
    application_window_open: bool | None = None
    global_conditions: list[EligibilityCondition] = Field(default_factory=list)
    pathways: list[EligibilityPathway] = Field(default_factory=list)
    optional_conditions: list[EligibilityCondition] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    actions: list[ActionDefinition] = Field(default_factory=list)
    evidence_registry: dict[str, EvidenceReference] = Field(default_factory=dict)
    questionnaire: list[QuestionnaireItem] = Field(default_factory=list)
    fixture_precomputed_outcome: ApplicantOutcome | None = None
    fixture_assessment_summary: str | None = None
    support_channels: list[SupportChannelInfo] = Field(default_factory=list)
    verification_checklist: list[str] = Field(default_factory=list)
    jurisdiction: dict[str, Any] | None = None
    authority_info: dict[str, Any] | None = None
    grievance_route: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _sync_fictional_and_evidence_registry(self) -> SchemeRecord:
        if self.data_type == SchemeDataType.FICTIONAL_FIXTURE:
            self.is_fictional = True
        if self.is_fictional and not self.fixture_notice:
            self.fixture_notice = FICTIONAL_DEMO_WARNING
        all_conditions = [
            *self.global_conditions,
            *self.optional_conditions,
            *(cond for pathway in self.pathways for cond in pathway.conditions),
        ]
        for cond in all_conditions:
            if cond.evidence is not None and cond.evidence.id not in self.evidence_registry:
                self.evidence_registry[cond.evidence.id] = cond.evidence
        return self


class ConditionAssessmentResult(BaseModel):
    """Traceable evaluation output for a single condition."""

    model_config = ConfigDict(extra="forbid")

    condition_id: str
    question_id: str | None = None
    pathway_id: str | None = None
    label: str
    mandatory: bool
    is_optional: bool
    status: ConditionResultStatus
    submitted_answer: Any = None
    explanation: str
    evidence_id: str | None = None
    evidence: EvidenceReference | None = None
    is_fictional: bool = False


class PathwayAssessmentResult(BaseModel):
    """Evaluation output for an eligibility pathway."""

    model_config = ConfigDict(extra="forbid")

    pathway_id: str
    label: str
    status: ConditionResultStatus
    condition_results: list[ConditionAssessmentResult] = Field(default_factory=list)
    explanation: str


class ActionPlanItem(BaseModel):
    """Deterministic action plan step with computed status and gate/block explanations."""

    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    description: str | None = None
    status: ActionStatus
    status_reason: str | None = None
    gate_reason: str | None = None
    prerequisites: list[str] = Field(default_factory=list)
    document_type: str | None = None
    evidence_id: str | None = None
    evidence: EvidenceReference | None = None
    is_submission: bool = False


class AssessmentRequest(BaseModel):
    """Input payload for evaluating a real scheme and building its action plan."""

    model_config = ConfigDict(extra="forbid")

    scheme_id: str = Field(..., min_length=1, max_length=120)
    answers: dict[str, Any] = Field(default_factory=dict)
    completed_action_ids: list[str] = Field(default_factory=list)
    allow_fictional_fixture: bool = False


class DemoAssessRequest(BaseModel):
    """Explicitly isolated request payload for evaluating a fictional demo scenario."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(default="demo-assessable", min_length=1, max_length=120)
    answers: dict[str, Any] = Field(default_factory=dict)
    completed_action_ids: list[str] = Field(default_factory=list)


class AssessmentResponse(BaseModel):
    """Complete assessment output combining readiness, outcome, condition trace, and action plan."""

    model_config = ConfigDict(extra="forbid")

    scheme_id: str
    scheme_name: str
    readiness: SchemeReadiness
    effective_readiness: SchemeReadiness
    data_type: SchemeDataType
    is_fictional: bool
    fictional_warning: str | None = None
    disclaimer: str
    applicant_outcome: ApplicantOutcome | None = None
    summary: str
    global_condition_results: list[ConditionAssessmentResult] = Field(default_factory=list)
    pathway_results: list[PathwayAssessmentResult] = Field(default_factory=list)
    optional_condition_results: list[ConditionAssessmentResult] = Field(default_factory=list)
    condition_results: list[ConditionAssessmentResult] = Field(default_factory=list)
    action_plan: list[ActionPlanItem] = Field(default_factory=list)
    safeguard_warnings: list[str] = Field(default_factory=list)


class SchemeSummary(BaseModel):
    """Lightweight discovery card payload for GET /api/schemes."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    short_name: str
    issuing_body: str
    portal_url: str | None = None
    readiness: SchemeReadiness
    data_type: SchemeDataType
    is_fictional: bool = False
    verification_note: str | None = None
    academic_year_verified: str | None = None
    official_source_inspected: bool = False
    human_verified: bool = False


class SchemeDetailResponse(BaseModel):
    """Detailed scheme view returned by GET /api/schemes/{scheme_id}."""

    model_config = ConfigDict(extra="forbid")

    scheme: SchemeRecord
    safe_for_automated_assessment: bool
    Pending_verification_requirements: list[str] = Field(default_factory=list)
    disclaimer: str = PRELIMINARY_GUIDANCE_DISCLAIMER


class RetrievedPassage(BaseModel):
    """Single source-linked passage returned by classical TF-IDF policy retrieval."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    scheme_id: str
    scheme_name: str
    source_title: str
    source_url: str | None = None
    academic_cycle: str | None = None
    section_or_page: str | None = None
    excerpt: str
    similarity_score: float
    verified: bool
    is_fictional: bool


class AskRequest(BaseModel):
    """Request payload for POST /api/ask source-grounded policy Q&A."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=2, max_length=500)
    scheme_id: str | None = Field(default=None, max_length=120)
    include_fictional_demo: bool = False
    top_k: int = Field(default=3, ge=1, le=5)


class AskResponse(BaseModel):
    """Source-grounded response for POST /api/ask with explicit refusal and non-eligibility notice."""

    model_config = ConfigDict(extra="forbid")

    query: str
    scheme_id: str | None = None
    status: RetrievalStatus
    answer_message: str
    passages: list[RetrievedPassage] = Field(default_factory=list)
    is_fictional_context: bool = False
    fictional_warning: str | None = None
    method_disclaimer: str = RETRIEVAL_METHOD_DISCLAIMER
    eligibility_separation_notice: str = (
        "Retrieving a policy passage does not evaluate or confirm your personal eligibility. "
        "Use the deterministic eligibility check when a scheme is ASSESSABLE, or consult the official portal."
    )


class HealthResponse(BaseModel):
    """Health check response for GET /api/health."""

    model_config = ConfigDict(extra="forbid")

    status: str = "ok"
    product: str = "HaqSetu — AI Welfare and Scholarship Navigator"
    real_scheme_count: int
    assessable_real_scheme_count: int
    demo_scenario_count: int


# ---------------------------------------------------------------------------
# P9 — AI/ML Enhancement Types
# ---------------------------------------------------------------------------

RECOMMENDATION_NON_ELIGIBILITY_DISCLAIMER = (
    "Scheme recommendations are based on keyword similarity to catalogue metadata (descriptive text, "
    "issuing body, and scheme names). They are NOT an eligibility assessment. No user answer is "
    "evaluated against official policy rules during recommendation. Always verify your eligibility "
    "on the official scheme portal or through the deterministic assessment where the scheme is ASSESSABLE."
)

INTENT_CONFIDENCE_NOTICE = (
    "Intent confidence scores are the softmax-normalised log-probability distribution of a Multinomial "
    "Naive Bayes classifier trained on a small synthetic dataset. They indicate relative class ranking "
    "within that distribution, not calibrated posterior probabilities."
)


class IntentClass(StrEnum):
    """Eight intent classes recognised by the HaqSetu Naive Bayes intent classifier."""

    CHECK_ELIGIBILITY = "check_eligibility"
    FIND_SCHEME = "find_scheme"
    ASK_DOCUMENTS = "ask_documents"
    ASK_DEADLINE = "ask_deadline"
    ASK_AWARD = "ask_award"
    ASK_GRIEVANCE = "ask_grievance"
    ASK_PORTAL = "ask_portal"
    OUT_OF_SCOPE = "out_of_scope"


class IntentPrediction(BaseModel):
    """Predicted intent with ranked confidence distribution from the Naive Bayes classifier."""

    model_config = ConfigDict(extra="forbid")

    predicted_intent: IntentClass
    confidence_scores: dict[str, float] = Field(default_factory=dict)
    confidence_notice: str = INTENT_CONFIDENCE_NOTICE
    is_out_of_scope: bool = False


class SchemeRecommendationItem(BaseModel):
    """Single scheme recommendation with similarity score and non-eligibility notice."""

    model_config = ConfigDict(extra="forbid")

    scheme_id: str
    scheme_name: str
    short_name: str
    issuing_body: str
    portal_url: str | None = None
    readiness: SchemeReadiness
    data_type: SchemeDataType
    is_fictional: bool
    similarity_score: float
    match_reason: str


class RecommendationRequest(BaseModel):
    """Request payload for POST /api/recommend content-based scheme recommendation."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=2, max_length=500)
    top_k: int = Field(default=3, ge=1, le=5)
    include_fictional: bool = False


class RecommendationResponse(BaseModel):
    """Content-based scheme recommendation response with explicit non-eligibility disclaimer."""

    model_config = ConfigDict(extra="forbid")

    query: str
    recommendations: list[SchemeRecommendationItem] = Field(default_factory=list)
    disclaimer: str = RECOMMENDATION_NON_ELIGIBILITY_DISCLAIMER
    method_note: str = (
        "Recommendations use TF-IDF cosine similarity over curated scheme descriptors "
        "(catalogue metadata only). This is not a machine-learning eligibility classifier."
    )


class AssistantRequest(BaseModel):
    """Request payload for POST /api/assistant — unified intent + routing entry point."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=2, max_length=500)
    scheme_id: str | None = Field(default=None, max_length=120)
    include_fictional_demo: bool = False
    top_k: int = Field(default=3, ge=1, le=5)


class AssistantResponse(BaseModel):
    """Unified assistant response: intent prediction + recommended routing + optional Q&A result."""

    model_config = ConfigDict(extra="forbid")

    query: str
    intent: IntentPrediction
    routing_advice: str
    ask_response: AskResponse | None = None
    recommendations: list[SchemeRecommendationItem] = Field(default_factory=list)
    recommendation_disclaimer: str = RECOMMENDATION_NON_ELIGIBILITY_DISCLAIMER


def _is_valid_http_url(url: str | None) -> bool:
    """Return True if url is a non-empty http:// or https:// string."""
    if not url or not isinstance(url, str):
        return False
    stripped = url.strip().lower()
    return stripped.startswith("https://") or stripped.startswith("http://")


def validate_real_scheme_for_assessment(scheme: SchemeRecord) -> list[str]:
    """
    Validate whether a real scheme satisfies all mandatory human-verification and evidence safeguards.

    Returns a list of human-readable error strings. An empty list means the scheme is safe to assess.
    """
    errors: list[str] = []

    if scheme.is_fictional or scheme.data_type == SchemeDataType.FICTIONAL_FIXTURE:
        errors.append(
            f"Scheme '{scheme.id}' is marked as fictional fixture data and cannot be validated as real policy."
        )

    if scheme.rules_stale_or_conflicting:
        errors.append(
            f"Scheme '{scheme.id}' has stale or conflicting policy rules and must remain LISTING_ONLY."
        )

    if not scheme.human_verified:
        errors.append(f"Scheme '{scheme.id}' lacks human_verified=True.")

    if not (scheme.verified_by and scheme.verified_by.strip()):
        errors.append(
            f"Scheme '{scheme.id}' lacks a documented human reviewer (verified_by). "
            "Setting human_verified=True alone is insufficient."
        )

    if not (scheme.verification_date and scheme.verification_date.strip()):
        errors.append(f"Scheme '{scheme.id}' lacks a documented verification_date.")

    if not scheme.official_source_inspected:
        errors.append(f"Scheme '{scheme.id}' does not have official_source_inspected=True.")

    if not _is_valid_http_url(scheme.official_source_url):
        errors.append(f"Scheme '{scheme.id}' lacks a valid official_source_url.")

    if not (scheme.academic_year_verified and scheme.academic_year_verified.strip()):
        errors.append(f"Scheme '{scheme.id}' lacks a verified current academic_year_verified.")

    mandatory_conditions = [
        *(c for c in scheme.global_conditions if c.mandatory and not c.is_optional),
        *(
            c
            for p in scheme.pathways
            for c in p.conditions
            if c.mandatory and not c.is_optional
        ),
    ]
    if not mandatory_conditions:
        errors.append(
            f"Scheme '{scheme.id}' has no mandatory eligibility conditions configured."
        )

    all_conditions = [
        *scheme.global_conditions,
        *(c for p in scheme.pathways for c in p.conditions),
        *scheme.optional_conditions,
    ]
    for cond in all_conditions:
        ev = cond.evidence or (
            scheme.evidence_registry.get(cond.evidence_id) if cond.evidence_id else None
        )
        if ev is None:
            errors.append(
                f"Condition '{cond.id}' in scheme '{scheme.id}' is missing a valid evidence reference."
            )
            continue
        _validate_real_evidence_ref(scheme, f"Condition '{cond.id}'", ev, errors)

    for action in scheme.actions:
        if action.evidence_id is not None:
            ev = scheme.evidence_registry.get(action.evidence_id)
            if ev is None:
                errors.append(
                    f"Action '{action.id}' in scheme '{scheme.id}' references unknown evidence_id '{action.evidence_id}'."
                )
            else:
                _validate_real_evidence_ref(scheme, f"Action '{action.id}'", ev, errors)
        elif action.is_submission or action.requires_eligible or action.requires_open_window:
            errors.append(
                f"Gated/submission action '{action.id}' in assessable real scheme '{scheme.id}' "
                "must cite traceable official evidence (evidence_id)."
            )

    known_action_ids = {a.id for a in scheme.actions}
    for action in scheme.actions:
        for prereq_id in action.prerequisites:
            if prereq_id not in known_action_ids:
                errors.append(
                    f"Action '{action.id}' in scheme '{scheme.id}' references unknown prerequisite '{prereq_id}'."
                )

    return errors


def _validate_real_evidence_ref(
    scheme: SchemeRecord,
    owner_label: str,
    ev: EvidenceReference,
    errors: list[str],
) -> None:
    """Check that an EvidenceReference meets all official-source and cycle requirements."""
    if ev.fictional:
        errors.append(
            f"{owner_label} in real scheme '{scheme.id}' cites fictional evidence '{ev.id}'."
        )
    if not ev.verified:
        errors.append(
            f"{owner_label} in real scheme '{scheme.id}' cites unverified evidence '{ev.id}'."
        )
    if not _is_valid_http_url(ev.source_url):
        errors.append(
            f"Evidence '{ev.id}' for {owner_label} in scheme '{scheme.id}' lacks a valid official source_url."
        )
    if not (ev.section_or_page and ev.section_or_page.strip()):
        errors.append(
            f"Evidence '{ev.id}' for {owner_label} in scheme '{scheme.id}' lacks a section_or_page reference."
        )
    if not (ev.access_date and ev.access_date.strip()):
        errors.append(
            f"Evidence '{ev.id}' for {owner_label} in scheme '{scheme.id}' lacks an access_date."
        )
    if not (ev.verification_date and ev.verification_date.strip()):
        errors.append(
            f"Evidence '{ev.id}' for {owner_label} in scheme '{scheme.id}' lacks a verification_date."
        )
    if not (ev.academic_cycle and ev.academic_cycle.strip()):
        errors.append(
            f"Evidence '{ev.id}' for {owner_label} in scheme '{scheme.id}' lacks an academic_cycle."
        )
    elif (
        scheme.academic_year_verified
        and ev.academic_cycle.strip() != scheme.academic_year_verified.strip()
    ):
        errors.append(
            f"Evidence '{ev.id}' academic_cycle ('{ev.academic_cycle}') does not match "
            f"scheme academic_year_verified ('{scheme.academic_year_verified}')."
        )


def validate_scheme_catalog(
    schemes: list[SchemeRecord],
    *,
    allow_fictional: bool = False,
) -> list[str]:
    """
    Validate a list of SchemeRecords for duplicate IDs, fictional leakage, and assessable safeguards.
    """
    errors: list[str] = []
    seen_ids: set[str] = set()

    for scheme in schemes:
        if scheme.id in seen_ids:
            errors.append(f"Duplicate scheme ID detected: '{scheme.id}'.")
        seen_ids.add(scheme.id)

        if not allow_fictional and (
            scheme.is_fictional or scheme.data_type == SchemeDataType.FICTIONAL_FIXTURE
        ):
            errors.append(
                f"Fictional scheme '{scheme.id}' is not permitted in the real scheme catalogue."
            )

        if not scheme.is_fictional and scheme.readiness == SchemeReadiness.ASSESSABLE:
            errors.extend(validate_real_scheme_for_assessment(scheme))

    return errors


# ---------------------------------------------------------------------------
# Default support channels with traceable source notes (Audit #5).
# verified_portal_fact=True ONLY when a specific official source URL backs the claim.
# ---------------------------------------------------------------------------
_DEFAULT_REAL_SUPPORT_CHANNELS: dict[str, list[SupportChannelInfo]] = {
    "pmsp-central-sector": [
        SupportChannelInfo(
            channel_type="OFFICIAL_PORTAL",
            label="National Scholarship Portal (NSP) — Official Portal",
            official_url="https://scholarships.gov.in",
            contact_detail="Student OTR & Application Portal",
            hours_or_sla=None,
            source_note=(
                "Recorded in data/schemes.json (portal field). "
                "Confirmed live on scholarships.gov.in (accessed June 2026)."
            ),
            verified_portal_fact=True,
        ),
        SupportChannelInfo(
            channel_type="HELPDESK",
            label="NSP Official Helpdesk",
            official_url="https://scholarships.gov.in/fresh1819/nsphelpdesk",
            contact_detail="helpdesk@nsp.gov.in | 0120-6619540",
            hours_or_sla="8:00 AM to 8:00 PM (all days except government holidays)",
            source_note=(
                "Published on NSP Helpdesk page (https://scholarships.gov.in/fresh1819/nsphelpdesk), "
                "page marked updated June 2026. Source: cross-check performed June 2026."
            ),
            verified_portal_fact=True,
        ),
        SupportChannelInfo(
            channel_type="GRIEVANCE_REDRESSAL",
            label="NSP Nodal Officers Directory",
            official_url="https://scholarships.gov.in/iver/nodelOfficerDetails",
            contact_detail="Scheme/District Nodal Officer directory",
            hours_or_sla=None,
            source_note=(
                "Official NSP Nodal Officer directory, page marked updated June 2026. "
                "Source: cross-check performed June 2026."
            ),
            verified_portal_fact=True,
        ),
        SupportChannelInfo(
            channel_type="GRIEVANCE_REDRESSAL",
            label="CPGRAMS Public Grievance Portal (General Government Route)",
            official_url="https://pgportal.gov.in/Home/",
            contact_detail="Centralised Public Grievance Redress and Monitoring System",
            hours_or_sla=None,
            source_note=(
                "Official Government of India CPGRAMS portal (https://pgportal.gov.in/Home/). "
                "This is a general public-grievance route — its applicability to PM-USP Central Sector "
                "specifically must be confirmed on the scheme portal."
            ),
            verified_portal_fact=True,
        ),
    ],
    "up-pre-matric-scholarship": [
        SupportChannelInfo(
            channel_type="OFFICIAL_PORTAL",
            label="Uttar Pradesh Scholarship & Fee Reimbursement Online System",
            official_url="https://scholarship.up.gov.in",
            contact_detail="Social Welfare Department, Government of Uttar Pradesh",
            hours_or_sla=None,
            source_note=(
                "Recorded in data/schemes.json (portal field). "
                "Specific category helpline must be verified on the portal for the chosen variant."
            ),
            verified_portal_fact=True,
        ),
        SupportChannelInfo(
            channel_type="GRIEVANCE_REDRESSAL",
            label="CPGRAMS Public Grievance Portal (General Government Route)",
            official_url="https://pgportal.gov.in/Home/",
            contact_detail="Centralised Public Grievance Redress and Monitoring System",
            hours_or_sla=None,
            source_note=(
                "Official Government of India CPGRAMS portal (https://pgportal.gov.in/Home/). "
                "This is a general public-grievance escalation route. Whether it applies to this "
                "specific UP Pre-Matric category variant must be confirmed in the category-specific "
                "Government Order (Shasanadesh)."
            ),
            verified_portal_fact=True,
        ),
    ],
}

_DEFAULT_VERIFICATION_CHECKLISTS: dict[str, list[str]] = {
    "pmsp-central-sector": [
        "Inspect current academic year notification on https://scholarships.gov.in and the "
        "Ministry of Education CSSS guidelines PDF.",
        "Verify exact parental/family annual income ceiling and issuing authority for the Income Certificate.",
        "Verify Class 12 board marks/percentile requirement for fresh applicants and GPA/attendance rules for renewal.",
        "Verify course-level exclusions (diploma, correspondence/distance mode) and concurrent central scholarship exclusions.",
        "Record exact section/page numbers, verbatim excerpts, access date, human reviewer name, and verification date "
        "before changing readiness from LISTING_ONLY to ASSESSABLE.",
    ],
    "up-pre-matric-scholarship": [
        "Select the exact beneficiary variant (SC / ST / General / OBC / Minority) on https://scholarship.up.gov.in.",
        "Inspect the official Government Order (Shasanadesh) and master timetable for the selected category and current academic year.",
        "Verify class eligibility (e.g., Class 9 and Class 10 full-time enrollment — confirm in current-year GO) and "
        "family income threshold for the chosen category.",
        "Verify required documents (caste certificate if applicable, income certificate, OTR number) in the correct "
        "category-specific, current-year Government Order. Do NOT ask users for Aadhaar or bank account data in HaqSetu.",
        "Record human verification metadata and verbatim official clauses before changing readiness from LISTING_ONLY to ASSESSABLE.",
    ],
}


def load_real_schemes(path: str | Path) -> list[SchemeRecord]:
    """
    Load real candidate schemes from `data/schemes.json` without modifying the file on disk.

    Enforces strict separation from fictional fixture data and fails closed to LISTING_ONLY
    if any scheme lacks complete human verification.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise SchemeValidationError(f"Real scheme catalogue file not found: '{file_path}'.")
    try:
        raw_data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchemeValidationError(
            f"Malformed JSON in real scheme catalogue '{file_path}': {exc}"
        ) from exc

    if not isinstance(raw_data, dict):
        raise SchemeValidationError(f"Root of '{file_path}' must be a JSON object.")

    meta = raw_data.get("_meta", {})
    if meta.get("data_type") == SchemeDataType.FICTIONAL_FIXTURE.value:
        raise SchemeValidationError(
            f"Refusing to load fictional fixture file '{file_path}' as a real scheme catalogue."
        )

    raw_schemes = raw_data.get("schemes")
    if not isinstance(raw_schemes, list):
        raise SchemeValidationError(f"Expected 'schemes' list in '{file_path}'.")

    loaded: list[SchemeRecord] = []
    for item in raw_schemes:
        if not isinstance(item, dict) or "id" not in item or "name" not in item:
            raise SchemeValidationError(f"Invalid scheme entry in '{file_path}'.")
        if item.get("data_type") == SchemeDataType.FICTIONAL_FIXTURE.value or item.get("is_fictional"):
            raise SchemeValidationError(
                f"Fictional scheme record '{item.get('id')}' found inside real scheme catalogue."
            )
        sid = str(item["id"])
        record = SchemeRecord(
            id=sid,
            name=str(item["name"]),
            short_name=str(item.get("short_name") or item["name"]),
            issuing_body=str(
                item.get("ministry") or item.get("issuing_body") or "Unknown Authority"
            ),
            portal_url=item.get("portal") or item.get("portal_url"),
            readiness=SchemeReadiness(item.get("readiness", "LISTING_ONLY")),
            data_type=SchemeDataType.REAL_STUB,
            is_fictional=False,
            verification_note=item.get("verification_note"),
            academic_year_verified=item.get("academic_year_verified"),
            official_source_url=item.get("official_source_url"),
            # Strict bool check: item.get(...) is True avoids "false" string being truthy
            official_source_inspected=item.get("official_source_inspected") is True,
            human_verified=item.get("human_verified") is True,
            verified_by=item.get("verified_by"),
            verification_date=item.get("verification_date"),
            required_documents=list(item.get("required_documents", [])),
            support_channels=list(_DEFAULT_REAL_SUPPORT_CHANNELS.get(sid, [])),
            verification_checklist=list(_DEFAULT_VERIFICATION_CHECKLISTS.get(sid, [])),
        )
        if record.readiness == SchemeReadiness.ASSESSABLE:
            validation_errors = validate_real_scheme_for_assessment(record)
            if validation_errors:
                record.readiness = SchemeReadiness.LISTING_ONLY
        loaded.append(record)

    return loaded


# ---------------------------------------------------------------------------
# Demo condition rule specifications used by load_demo_fixtures to enrich
# the fictional demo scenario with evaluable operators and value aliases.
# These are synthetic rules for demonstration only — not official policy.
# ---------------------------------------------------------------------------
_DEMO_CONDITION_RULE_SPECS: dict[str, dict[str, Any]] = {
    "cond-marks": {
        "question_id": "q-marks",
        "operator": RuleOperator.GTE,
        "expected_value": 80,
        "value_aliases": {
            "above_80": 85,
            "60_to_80": 70,
            "below_60": 50,
        },
    },
    "cond-income": {
        "question_id": "q-income",
        "operator": RuleOperator.LTE,
        "expected_value": 450000,
        "value_aliases": {
            "below_450000": 400000,
            "above_450000": 500000,
        },
    },
    "cond-enrollment": {
        "question_id": "q-enrollment",
        "operator": RuleOperator.BOOL_TRUE,
        "expected_value": True,
        "value_aliases": {
            "yes": True,
            "no": False,
        },
    },
    "cond-prev-scholarship": {
        "question_id": "q-other-scholarship",
        "operator": RuleOperator.BOOL_FALSE,
        "expected_value": False,
        "value_aliases": {
            "yes": True,
            "no": False,
        },
    },
}


def load_demo_fixtures(path: str | Path) -> list[SchemeRecord]:
    """
    Load and normalize fictional demonstration scenarios from `data/fixtures/demo.json`.

    Preserves P1's static display statuses only as `fixture_display_result` /
    `fixture_default_status` so they are never mistaken for live evaluations computed
    from user answers, and preserves `REAL_STUB` identity for `demo-listing-only`.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise SchemeValidationError(f"Demo fixture file not found: '{file_path}'.")
    try:
        raw_data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchemeValidationError(
            f"Malformed JSON in demo fixture '{file_path}': {exc}"
        ) from exc

    if not isinstance(raw_data, dict):
        raise SchemeValidationError(f"Root of '{file_path}' must be a JSON object.")

    raw_scenarios = raw_data.get("scenarios")
    if not isinstance(raw_scenarios, list):
        raise SchemeValidationError(f"Expected 'scenarios' list in '{file_path}'.")

    meta_warning = raw_data.get("_meta", {}).get("warning") or FICTIONAL_DEMO_WARNING
    scenarios: list[SchemeRecord] = []

    for item in raw_scenarios:
        raw_data_type = item.get("data_type", "FICTIONAL_FIXTURE")
        scheme_data_type = (
            SchemeDataType(raw_data_type)
            if raw_data_type in SchemeDataType._value2member_map_
            else SchemeDataType.FICTIONAL_FIXTURE
        )
        # is_fictional is True ONLY when data_type is FICTIONAL_FIXTURE.
        # Do NOT default is_fictional=True — that would mark REAL_STUB records as fictional.
        is_fictional = scheme_data_type == SchemeDataType.FICTIONAL_FIXTURE

        questionnaire = [
            QuestionnaireItem(
                id=q["id"],
                question=q["question"],
                type=q.get("type", "radio"),
                options=[
                    QuestionnaireOption(value=opt["value"], label=opt["label"])
                    for opt in q.get("options", [])
                ],
                demo_answer=q.get("demo_answer"),
                links_to_condition=q.get("links_to_condition"),
            )
            for q in item.get("questionnaire", [])
        ]
        condition_to_question: dict[str, str] = {
            q.links_to_condition: q.id
            for q in questionnaire
            if q.links_to_condition is not None
        }

        evidence_registry: dict[str, EvidenceReference] = {}
        pathways: list[EligibilityPathway] = []

        for raw_pathway in item.get("pathways", []):
            conditions: list[EligibilityCondition] = []
            for raw_cond in raw_pathway.get("conditions", []):
                cond_id = raw_cond["id"]
                raw_ev = raw_cond.get("evidence")
                ev_ref: EvidenceReference | None = None
                if isinstance(raw_ev, dict):
                    ev_ref = EvidenceReference(
                        id=raw_ev["id"],
                        source_title=(
                            raw_ev.get("source_label")
                            or raw_ev.get("source_title")
                            or "Fictional Demo Source"
                        ),
                        source_url=raw_ev.get("source_url"),
                        academic_cycle=item.get("academic_year"),
                        section_or_page=raw_ev.get("source_label"),
                        # Use non-empty fallback for missing excerpts (min_length=1)
                        excerpt=raw_ev.get("excerpt") or "[No excerpt provided]",
                        verified=raw_ev.get("verified") is True,
                        fictional=raw_ev.get("fictional") is not False,  # default True for demo
                    )
                    evidence_registry[ev_ref.id] = ev_ref

                rule_spec = _DEMO_CONDITION_RULE_SPECS.get(cond_id, {})
                q_id = (
                    raw_cond.get("question_id")
                    or condition_to_question.get(cond_id)
                    or rule_spec.get("question_id")
                )
                operator = RuleOperator(
                    raw_cond.get("operator", rule_spec.get("operator", RuleOperator.EQ))
                )
                expected_value = raw_cond.get(
                    "expected_value", rule_spec.get("expected_value", True)
                )
                value_aliases = dict(
                    raw_cond.get("value_aliases", rule_spec.get("value_aliases", {}))
                )

                conditions.append(
                    EligibilityCondition(
                        id=cond_id,
                        question_id=q_id,
                        label=raw_cond["label"],
                        operator=operator,
                        expected_value=expected_value,
                        mandatory=bool(raw_cond.get("mandatory", True)),
                        is_optional=not bool(raw_cond.get("mandatory", True)),
                        evidence_id=ev_ref.id if ev_ref else None,
                        evidence=ev_ref,
                        value_aliases=value_aliases,
                        fixture_display_result=normalize_condition_result(
                            raw_cond.get("result")
                        ),
                        fixture_user_answer=raw_cond.get("user_answer"),
                    )
                )

            pathways.append(
                EligibilityPathway(
                    id=raw_pathway["id"],
                    label=raw_pathway["label"],
                    conditions=conditions,
                    fixture_display_result=normalize_condition_result(
                        raw_pathway.get("result")
                    ),
                )
            )

        actions: list[ActionDefinition] = []
        for raw_act in item.get("action_plan", []):
            raw_status = raw_act.get("status")
            actions.append(
                ActionDefinition(
                    id=raw_act["id"],
                    label=raw_act["label"],
                    prerequisites=list(raw_act.get("prerequisites", [])),
                    document_type=raw_act.get("document_type"),
                    fixture_default_status=ActionStatus(raw_status) if raw_status else None,
                    fixture_status_reason=raw_act.get("status_reason"),
                    fixture_gate_reason=raw_act.get("gate_reason"),
                )
            )

        raw_outcome = item.get("assessment_outcome")
        notice = item.get("fixture_notice") or (meta_warning if is_fictional else None)
        if is_fictional and notice and "fictional" not in notice.lower() and "invented" not in notice.lower():
            notice = f"{FICTIONAL_DEMO_WARNING} {notice}"

        req_docs = [a.document_type for a in actions if a.document_type]

        scenarios.append(
            SchemeRecord(
                id=item["id"],
                name=item["name"],
                short_name=item.get("short_name") or item["name"],
                issuing_body=item.get("issuing_body") or "Fictional Authority",
                readiness=SchemeReadiness(item.get("readiness", "LISTING_ONLY")),
                data_type=scheme_data_type,
                is_fictional=is_fictional,
                fixture_notice=notice,
                academic_year=item.get("academic_year"),
                pathways_exhaustive=bool(item.get("pathways_exhaustive", False)),
                pathways=pathways,
                required_documents=req_docs,
                actions=actions,
                evidence_registry=evidence_registry,
                questionnaire=questionnaire,
                fixture_precomputed_outcome=ApplicantOutcome(raw_outcome)
                if raw_outcome
                else None,
                fixture_assessment_summary=item.get("assessment_summary"),
            )
        )

    return scenarios
