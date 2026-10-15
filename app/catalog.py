"""Safe repository and catalogue service separating real schemes from fictional demo scenarios."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from app.retriever import PolicyClauseRetriever
from app.schemas import (
    AssistantResponse,
    IntentClass,
    RECOMMENDATION_NON_ELIGIBILITY_DISCLAIMER,
    RecommendationResponse,
    SchemeDetailResponse,
    SchemeReadiness,
    SchemeRecommendationItem,
    SchemeRecord,
    SchemeSummary,
    load_demo_fixtures,
    load_real_schemes,
    validate_real_scheme_for_assessment,
)

if TYPE_CHECKING:
    from app.intent_classifier import NaiveBayesIntentClassifier
    from app.recommender import SchemeRecommender

DEFAULT_REPO_ROOT = Path(__file__).resolve().parent.parent

# Intent-to-routing-advice messages
_INTENT_ROUTING: dict[str, str] = {
    IntentClass.CHECK_ELIGIBILITY: (
        "Your question is about eligibility. Use POST /api/assess for a real ASSESSABLE scheme "
        "or POST /api/demo/assess to try the fictional demo. For LISTING_ONLY schemes, consult "
        "the official portal directly."
    ),
    IntentClass.FIND_SCHEME: (
        "Your question is about finding schemes. See the recommendations below or use "
        "GET /api/schemes with a search keyword."
    ),
    IntentClass.ASK_DOCUMENTS: (
        "Your question is about required documents. Check the scheme detail page for the "
        "required_documents list, or consult the official portal."
    ),
    IntentClass.ASK_DEADLINE: (
        "Your question is about deadlines. HaqSetu cannot confirm current academic-cycle dates "
        "for unverified schemes. Please check the official portal (scholarships.gov.in or "
        "scholarship.up.gov.in) for the latest timetable."
    ),
    IntentClass.ASK_AWARD: (
        "Your question is about scholarship amounts. HaqSetu does not fabricate award values "
        "for unverified schemes. Please check the official portal or notification."
    ),
    IntentClass.ASK_GRIEVANCE: (
        "Your question is about grievances. Official helpdesk and grievance channels are listed "
        "in GET /api/schemes/{scheme_id} under support_channels."
    ),
    IntentClass.ASK_PORTAL: (
        "Your question is about the application portal. Check GET /api/schemes/{scheme_id} for "
        "the official portal_url and support_channels."
    ),
    IntentClass.OUT_OF_SCOPE: (
        "Your question appears to be outside the scope of HaqSetu's scholarship navigator. "
        "HaqSetu covers government scholarship discovery, eligibility assessment, and "
        "source-grounded policy Q&A only."
    ),
}


class SchemeCatalogService:
    """
    Manages loading, searching, and isolating real schemes (`data/schemes.json`)
    and fictional demo fixtures (`data/fixtures/demo.json`).

    Stage P9: Integrates NaiveBayesIntentClassifier and SchemeRecommender.
    """

    def __init__(
        self,
        schemes_path: str | Path | None = None,
        demo_path: str | Path | None = None,
    ) -> None:
        self.schemes_path = Path(
            schemes_path or (DEFAULT_REPO_ROOT / "data" / "schemes.json")
        )
        self.demo_path = Path(
            demo_path or (DEFAULT_REPO_ROOT / "data" / "fixtures" / "demo.json")
        )
        self._real_schemes: list[SchemeRecord] = []
        self._demo_scenarios: list[SchemeRecord] = []
        self._real_by_id: dict[str, SchemeRecord] = {}
        self._demo_by_id: dict[str, SchemeRecord] = {}
        self._retriever: PolicyClauseRetriever | None = None
        self._classifier: "NaiveBayesIntentClassifier | None" = None
        self._recommender: "SchemeRecommender | None" = None
        self.reload()

    def reload(self) -> None:
        """Reload real schemes and demo fixtures from disk and rebuild all indices."""
        self._real_schemes = load_real_schemes(self.schemes_path)
        self._demo_scenarios = load_demo_fixtures(self.demo_path)
        self._real_by_id = {s.id: s for s in self._real_schemes}
        self._demo_by_id = {s.id: s for s in self._demo_scenarios}
        self._retriever = PolicyClauseRetriever(
            [*self._real_schemes, *self._demo_scenarios]
        )
        self._init_ml_components()

    def _init_ml_components(self) -> None:
        """Initialise P9 components independently so one failure does not disable both."""
        self._classifier = None
        self._recommender = None

        try:
            from app.intent_classifier import NaiveBayesIntentClassifier

            self._classifier = NaiveBayesIntentClassifier()
        except Exception:
            # Keep assistant routing fail-closed if its model or dataset is unavailable.
            self._classifier = None

        try:
            from app.recommender import SchemeRecommender

            self._recommender = SchemeRecommender(
                [*self._real_schemes, *self._demo_scenarios]
            )
        except Exception:
            # The recommendation endpoint can report an unavailable index separately.
            self._recommender = None

    @property
    def retriever(self) -> PolicyClauseRetriever:
        """Return the initialized PolicyClauseRetriever."""
        if self._retriever is None:
            self.reload()
        assert self._retriever is not None
        return self._retriever

    @property
    def classifier(self) -> "NaiveBayesIntentClassifier | None":
        """Return the intent classifier (may be None if dataset file is absent)."""
        return self._classifier

    @property
    def recommender(self) -> "SchemeRecommender | None":
        """Return the scheme recommender."""
        return self._recommender

    def list_real_summaries(
        self,
        *,
        q: str | None = None,
        readiness: SchemeReadiness | None = None,
        ministry: str | None = None,
    ) -> list[SchemeSummary]:
        """
        Return filtered real scheme summaries for discovery.

        Never includes fictional demonstration scenarios (e.g. `demo-assessable`).
        """
        query_norm = q.strip().lower() if q else ""
        ministry_norm = ministry.strip().lower() if ministry else ""

        results: list[SchemeSummary] = []
        for s in self._real_schemes:
            if s.is_fictional:
                continue
            if readiness is not None and s.readiness != readiness:
                continue
            if ministry_norm and ministry_norm not in s.issuing_body.lower():
                continue
            if query_norm:
                haystack = f"{s.id} {s.name} {s.short_name} {s.issuing_body}".lower()
                if query_norm not in haystack:
                    continue
            results.append(
                SchemeSummary(
                    id=s.id,
                    name=s.name,
                    short_name=s.short_name,
                    issuing_body=s.issuing_body,
                    portal_url=s.portal_url,
                    readiness=s.readiness,
                    data_type=s.data_type,
                    is_fictional=False,
                    verification_note=s.verification_note,
                    academic_year_verified=s.academic_year_verified,
                    official_source_inspected=s.official_source_inspected,
                    human_verified=s.human_verified,
                )
            )
        return results

    def get_real_scheme(self, scheme_id: str) -> SchemeRecord | None:
        """Return a real scheme by ID, or None if not found (never returns fictional fixtures)."""
        scheme = self._real_by_id.get(scheme_id)
        if scheme is not None and not scheme.is_fictional:
            return scheme
        return None

    def get_real_scheme_detail(self, scheme_id: str) -> SchemeDetailResponse | None:
        """Return full detail and pending human verification items for a real scheme."""
        scheme = self.get_real_scheme(scheme_id)
        if scheme is None:
            return None
        validation_errors = validate_real_scheme_for_assessment(scheme)
        pending = (
            list(scheme.verification_checklist)
            if scheme.verification_checklist
            else validation_errors
        )
        return SchemeDetailResponse(
            scheme=scheme,
            safe_for_automated_assessment=(
                scheme.readiness == SchemeReadiness.ASSESSABLE and len(validation_errors) == 0
            ),
            Pending_verification_requirements=pending,
        )

    def list_demo_scenarios(self) -> list[SchemeRecord]:
        """Return all demonstration scenarios from `data/fixtures/demo.json`."""
        return list(self._demo_scenarios)

    def list_fictional_demo_scenarios(self) -> list[SchemeRecord]:
        """Return only FICTIONAL_FIXTURE scenarios (excludes REAL_STUB records in demo file)."""
        return [s for s in self._demo_scenarios if s.is_fictional]

    def get_demo_scenario(self, scenario_id: str) -> SchemeRecord | None:
        """Return a demo scenario by ID from `data/fixtures/demo.json`."""
        return self._demo_by_id.get(scenario_id)

    def is_demo_scenario_id(self, identifier: str) -> bool:
        """Return True if `identifier` belongs exclusively to the demo fixture set."""
        return identifier in self._demo_by_id and identifier not in self._real_by_id

    # ------------------------------------------------------------------
    # P9 AI/ML methods
    # ------------------------------------------------------------------

    def recommend_schemes(
        self,
        query: str,
        *,
        top_k: int = 3,
        include_fictional: bool = False,
    ) -> RecommendationResponse:
        """Return content-based TF-IDF scheme recommendations for `query`."""
        if self._recommender is None:
            return RecommendationResponse(
                query=query,
                recommendations=[],
                disclaimer=RECOMMENDATION_NON_ELIGIBILITY_DISCLAIMER,
                method_note="Recommender not available (index not initialised).",
            )
        recs = self._recommender.recommend(
            query, top_k=top_k, include_fictional=include_fictional
        )
        return RecommendationResponse(
            query=query,
            recommendations=recs,
        )

    def handle_assistant_query(
        self,
        query: str,
        *,
        scheme_id: str | None = None,
        include_fictional_demo: bool = False,
        top_k: int = 3,
    ) -> AssistantResponse:
        """
        Unified assistant entry point: classify intent, route, and optionally retrieve passages.

        For FIND_SCHEME intent: also returns scheme recommendations.
        For CHECK_ELIGIBILITY / policy intents: returns Q&A retrieval result.
        For OUT_OF_SCOPE: returns routing advice only.
        Never performs or implies eligibility evaluation.
        """
        from app.schemas import IntentClass, IntentPrediction

        # Classify intent
        if self._classifier is not None:
            intent_pred = self._classifier.predict(query)
        else:
            # Graceful fallback: treat as find_scheme
            intent_pred = IntentPrediction(
                predicted_intent=IntentClass.OUT_OF_SCOPE,
                confidence_scores={},
                confidence_notice=(
                    "The intent classifier is unavailable. HaqSetu did not infer a route; "
                    "please try again after the service is restored or use the scheme catalogue."
                ),
                is_out_of_scope=True,
            )

        intent_value = intent_pred.predicted_intent
        routing_advice = _INTENT_ROUTING.get(intent_value, _INTENT_ROUTING[IntentClass.OUT_OF_SCOPE])

        # For scope-relevant intents try retrieval; for FIND_SCHEME add recommendations
        ask_result = None
        recs: list[SchemeRecommendationItem] = []

        if intent_value == IntentClass.OUT_OF_SCOPE:
            # No retrieval for out-of-scope
            pass
        elif intent_value == IntentClass.FIND_SCHEME:
            if self._recommender is not None:
                recs = self._recommender.recommend(
                    query, top_k=top_k, include_fictional=include_fictional_demo
                )
        else:
            # Attempt policy Q&A retrieval for all other in-scope intents
            ask_result = self.retriever.answer_query(
                query,
                scheme_id=scheme_id,
                include_fictional_demo=include_fictional_demo,
                top_k=top_k,
            )

        return AssistantResponse(
            query=query,
            intent=intent_pred,
            routing_advice=routing_advice,
            ask_response=ask_result,
            recommendations=recs,
        )

    def get_ml_metrics(
        self,
        *,
        eval_path: Path | None = None,
        rec_eval_path: Path | None = None,
        dataset_path: Path | None = None,
    ) -> dict:
        """
        Run all ML benchmarks and return a metrics dict.

        All reported metrics are synthetic smoke benchmarks.
        """
        from app.retriever import evaluate_retrieval_benchmark, evaluate_retrieval_ablation

        _eval = eval_path or (DEFAULT_REPO_ROOT / "data" / "eval_queries.json")
        _rec_eval = rec_eval_path or (DEFAULT_REPO_ROOT / "data" / "ml" / "recommendation_eval.json")
        _dataset = dataset_path or (DEFAULT_REPO_ROOT / "data" / "ml" / "intent_dataset.json")

        metrics: dict = {}

        # Retrieval benchmark
        if _eval.exists():
            metrics["retrieval_benchmark"] = evaluate_retrieval_benchmark(self.retriever, _eval)
            metrics["retrieval_ablation"] = evaluate_retrieval_ablation(self.retriever, _eval)

        # Intent classifier evaluation (in-sample)
        if self._classifier is not None and _dataset.exists():
            import json
            raw = json.loads(_dataset.read_text(encoding="utf-8"))
            metrics["intent_classifier"] = self._classifier.evaluate(raw.get("utterances", []))

        # Recommender benchmark
        if self._recommender is not None and _rec_eval.exists():
            metrics["recommender_benchmark"] = self._recommender.evaluate_benchmark(_rec_eval)

        metrics["notice"] = (
            "All metrics are synthetic smoke benchmarks computed on datasets "
            "designed alongside the models. They indicate correct implementation "
            "logic, not generalisation accuracy on unseen data."
        )
        return metrics
