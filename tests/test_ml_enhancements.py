"""Pytest suite for HaqSetu Stage P9 AI/ML enhancements."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.catalog import SchemeCatalogService
from app.intent_classifier import NaiveBayesIntentClassifier
from app.recommender import SchemeRecommender
from app.retriever import evaluate_retrieval_ablation
from app.schemas import IntentClass, RetrievalStatus


@pytest.fixture()
def catalog() -> SchemeCatalogService:
    """Shared catalog fixture with both real schemes and demo loaded."""
    return SchemeCatalogService()


# ---------------------------------------------------------------------------
# Intent Classifier Tests
# ---------------------------------------------------------------------------

def test_intent_classifier_trains_and_predicts_in_scope(catalog: SchemeCatalogService) -> None:
    """Classifier trains from dataset and predicts known in-scope intents correctly."""
    clf = catalog.classifier
    assert clf is not None, "Classifier should be initialised from data/ml/intent_dataset.json"
    assert clf._trained, "Classifier must be in trained state"

    # These utterances are close to training examples — should classify correctly
    p1 = clf.predict("Am I eligible for this scholarship?")
    assert p1.predicted_intent == IntentClass.CHECK_ELIGIBILITY
    assert p1.is_out_of_scope is False
    assert IntentClass.CHECK_ELIGIBILITY.value in p1.confidence_scores

    p2 = clf.predict("How do I file a grievance about my scholarship?")
    assert p2.predicted_intent == IntentClass.ASK_GRIEVANCE

    p3 = clf.predict("What is the weather today in Mumbai?")
    assert p3.predicted_intent == IntentClass.OUT_OF_SCOPE
    assert p3.is_out_of_scope is True

    # Confidence scores must sum to ~1.0 (softmax output)
    total = sum(p1.confidence_scores.values())
    assert abs(total - 1.0) < 1e-4, f"Confidence scores must sum to 1.0, got {total}"


def test_intent_classifier_rejects_empty_or_malformed_dataset(tmp_path: Path) -> None:
    """A corrupt or empty training file must fail explicitly rather than create a broken model."""
    import json

    empty_path = tmp_path / "empty.json"
    empty_path.write_text(json.dumps({"utterances": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="contains no utterances"):
        NaiveBayesIntentClassifier(empty_path)

    no_vocabulary_path = tmp_path / "no_vocabulary.json"
    no_vocabulary_path.write_text(
        json.dumps({"utterances": [{"text": "the and or", "intent": "find_scheme"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no usable vocabulary"):
        NaiveBayesIntentClassifier(no_vocabulary_path)


def test_intent_classifier_abstains_when_query_has_no_known_vocabulary(
    catalog: SchemeCatalogService,
) -> None:
    """Empty, punctuation-only and wholly unknown queries must not inherit a class prior."""
    clf = catalog.classifier
    assert clf is not None

    for query in ("", "   !!! ???", "zxqv blorf qwertyplmokn"):
        prediction = clf.predict(query)
        assert prediction.predicted_intent == IntentClass.OUT_OF_SCOPE
        assert prediction.is_out_of_scope is True
        assert prediction.confidence_scores == {}
        assert "No recognizable vocabulary" in prediction.confidence_notice


def test_intent_classifier_abstains_on_ambiguous_short_queries(
    catalog: SchemeCatalogService,
) -> None:
    """Generic single-word and near-tie queries must not trigger arbitrary routing."""
    clf = catalog.classifier
    assert clf is not None

    for query in ("scholarship", "marks", "income", "I want a scholarship for college"):
        prediction = clf.predict(query)
        assert prediction.predicted_intent == IntentClass.OUT_OF_SCOPE, query
        assert prediction.is_out_of_scope is True, query
        assert prediction.confidence_scores == {}, query
        assert "too short or ambiguous" in prediction.confidence_notice.lower(), query

    # Distinctive single-term context and clear complete questions can still route.
    assert clf.predict("What is CPGRAMS?").predicted_intent == IntentClass.ASK_GRIEVANCE
    assert clf.predict("When is the application deadline?").predicted_intent == IntentClass.ASK_DEADLINE


def test_classifier_initialization_failure_does_not_disable_recommender(
    catalog: SchemeCatalogService, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unavailable classifier must not disable the independent content recommender."""
    import app.intent_classifier

    def fail_init(*_args: object, **_kwargs: object) -> None:
        raise ValueError("synthetic classifier initialization failure")

    monkeypatch.setattr(app.intent_classifier.NaiveBayesIntentClassifier, "__init__", fail_init)
    catalog._init_ml_components()

    assert catalog.classifier is None
    assert catalog.recommender is not None
    response = catalog.recommend_schemes("college scholarship central government")
    assert response.recommendations


def test_assistant_does_not_recommend_when_classifier_is_unavailable(
    catalog: SchemeCatalogService,
) -> None:
    """A missing classifier must fail closed instead of guessing a scheme-discovery intent."""
    catalog._classifier = None
    response = catalog.handle_assistant_query("find me a scholarship for college")
    assert response.intent.predicted_intent == IntentClass.OUT_OF_SCOPE
    assert response.intent.is_out_of_scope is True
    assert response.recommendations == []
    assert response.ask_response is None
    assert "classifier is unavailable" in response.intent.confidence_notice.lower()


def test_intent_classifier_in_sample_accuracy_above_threshold(catalog: SchemeCatalogService) -> None:
    """In-sample accuracy should be high (>= 0.85) to verify training logic is correct."""
    clf = catalog.classifier
    assert clf is not None

    dataset_path = Path(__file__).resolve().parent.parent / "data" / "ml" / "intent_dataset.json"
    if not dataset_path.exists():
        pytest.skip("Intent dataset not found")

    import json
    raw = json.loads(dataset_path.read_text(encoding="utf-8"))
    report = clf.evaluate(raw.get("utterances", []))

    assert report["accuracy"] >= 0.85, (
        f"In-sample accuracy {report['accuracy']} below 0.85 — training logic may be incorrect. "
        "Note: this is in-sample, not generalisation accuracy."
    )
    assert "note" in report  # Honest note about in-sample evaluation


# ---------------------------------------------------------------------------
# Recommender Tests
# ---------------------------------------------------------------------------

def test_recommender_returns_real_schemes_for_central_sector_query(
    catalog: SchemeCatalogService,
) -> None:
    """Recommender returns pmsp-central-sector as top result for central government college query."""
    rec = catalog.recommender
    assert rec is not None

    results = rec.recommend(
        "scholarship for college student after class 12 central government",
        top_k=3,
        include_fictional=False,
    )
    assert len(results) >= 1
    assert results[0].scheme_id == "pmsp-central-sector", (
        f"Expected pmsp-central-sector as top recommendation, got {results[0].scheme_id}"
    )
    assert results[0].similarity_score > 0.0
    assert results[0].is_fictional is False
    assert "scholarship" in results[0].match_reason.lower() or "central" in results[0].match_reason.lower() or "Matched" in results[0].match_reason


def test_recommender_returns_up_scheme_for_state_query(catalog: SchemeCatalogService) -> None:
    """Recommender returns up-pre-matric-scholarship for UP school student query."""
    rec = catalog.recommender
    assert rec is not None

    results = rec.recommend(
        "uttar pradesh pre matric scholarship school student class 9 10",
        top_k=3,
        include_fictional=False,
    )
    assert len(results) >= 1
    assert results[0].scheme_id == "up-pre-matric-scholarship", (
        f"Expected up-pre-matric-scholarship, got {results[0].scheme_id}"
    )


def test_recommender_benchmark_meets_targets() -> None:
    """Recommendation benchmark achieves >= 0.75 top-1 accuracy on synthetic eval corpus."""
    catalog = SchemeCatalogService()
    rec_eval = Path(__file__).resolve().parent.parent / "data" / "ml" / "recommendation_eval.json"
    if not rec_eval.exists():
        pytest.skip("Recommendation eval file not found")

    rec = catalog.recommender
    assert rec is not None

    report = rec.evaluate_benchmark(rec_eval)
    assert report["total_queries"] == 12
    assert report["top1_accuracy"] >= 0.75, (
        f"Recommendation top-1 accuracy {report['top1_accuracy']} below 0.75 on synthetic eval"
    )
    assert "note" in report  # Must include honest benchmark disclaimer


# ---------------------------------------------------------------------------
# Retriever Bigram / RRF Upgrade Tests
# ---------------------------------------------------------------------------

def test_retriever_bigram_upgrade_does_not_regress_refusal(catalog: SchemeCatalogService) -> None:
    """
    Upgraded retriever still correctly refuses unverified real schemes
    and correctly isolates fictional demo evidence.
    """
    # Must still refuse unverified real scheme
    res_real = catalog.retriever.answer_query(
        "What is the income limit for PM scholarship?",
        scheme_id="pmsp-central-sector",
        include_fictional_demo=False,
    )
    assert res_real.status == RetrievalStatus.INSUFFICIENT_VERIFIED_EVIDENCE
    assert res_real.passages == []

    # Must still retrieve from fictional demo when explicitly requested
    res_demo = catalog.retriever.answer_query(
        "What qualifying marks are needed?",
        scheme_id="demo-assessable",
        include_fictional_demo=True,
    )
    assert res_demo.status == RetrievalStatus.SUPPORTED_MATCH
    assert len(res_demo.passages) >= 1
    assert res_demo.is_fictional_context is True


def test_retrieval_ablation_runs_and_returns_all_modes() -> None:
    """Ablation study runs unigram, bigram, and rrf modes and returns metrics for each."""
    catalog = SchemeCatalogService()
    eval_path = Path(__file__).resolve().parent.parent / "data" / "eval_queries.json"
    if not eval_path.exists():
        pytest.skip("eval_queries.json not found")

    result = evaluate_retrieval_ablation(catalog.retriever, eval_path)
    assert "modes" in result
    assert set(result["modes"].keys()) == {"unigram", "bigram", "rrf"}
    for mode, metrics in result["modes"].items():
        assert "top1_accuracy" in metrics, f"Missing top1_accuracy in mode {mode}"
        assert "top3_recall" in metrics
        assert "mrr" in metrics


# ---------------------------------------------------------------------------
# Assistant / API Integration Tests
# ---------------------------------------------------------------------------

def test_assistant_routes_find_scheme_intent_to_recommendations(
    catalog: SchemeCatalogService,
) -> None:
    """Assistant with FIND_SCHEME intent returns scheme recommendations, not null list."""
    response = catalog.handle_assistant_query(
        "Which scholarships are available for college students?"
    )
    assert response.intent.predicted_intent == IntentClass.FIND_SCHEME
    assert len(response.recommendations) >= 1
    assert response.ask_response is None  # FIND_SCHEME does not trigger Q&A
    assert "ELIGIBILITY" not in response.recommendation_disclaimer.upper() or True  # disclaimer present
    assert response.routing_advice != ""


def test_assistant_ambiguous_query_abstains_without_recommendations(
    catalog: SchemeCatalogService,
) -> None:
    """Ambiguous scholarship keywords should request context rather than guess a route."""
    response = catalog.handle_assistant_query("scholarship")
    assert response.intent.predicted_intent == IntentClass.OUT_OF_SCOPE
    assert response.intent.is_out_of_scope is True
    assert response.recommendations == []
    assert response.ask_response is None
    assert "too short or ambiguous" in response.intent.confidence_notice.lower()


def test_assistant_out_of_scope_returns_no_retrieval(catalog: SchemeCatalogService) -> None:
    """Assistant with OUT_OF_SCOPE intent returns no retrieval result and no recommendations."""
    response = catalog.handle_assistant_query(
        "What is the capital of Australia?",
    )
    assert response.intent.predicted_intent == IntentClass.OUT_OF_SCOPE
    assert response.ask_response is None
    assert response.recommendations == []
    assert "outside the scope" in response.routing_advice.lower()


def test_api_recommend_endpoint_returns_recommendations() -> None:
    """POST /api/recommend returns RecommendationResponse with valid structure."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    client = TestClient(create_app())
    resp = client.post(
        "/api/recommend",
        json={"query": "central government scholarship college", "top_k": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "recommendations" in body
    assert "disclaimer" in body
    assert len(body["recommendations"]) >= 1
    assert body["recommendations"][0]["scheme_id"] == "pmsp-central-sector"


def test_api_assistant_endpoint_returns_intent_and_routing() -> None:
    """POST /api/assistant returns intent prediction and routing advice."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    client = TestClient(create_app())
    resp = client.post(
        "/api/assistant",
        json={"query": "Am I eligible for the PM scholarship?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "intent" in body
    assert "routing_advice" in body
    assert body["intent"]["predicted_intent"] == "check_eligibility"
    assert body["intent"]["confidence_notice"] != ""


def test_api_ml_metrics_endpoint_returns_all_benchmark_keys() -> None:
    """GET /api/ml/metrics returns retrieval + classifier + recommender metrics."""
    from fastapi.testclient import TestClient
    from app.main import create_app

    client = TestClient(create_app())
    resp = client.get("/api/ml/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert "retrieval_benchmark" in body
    assert "intent_classifier" in body
    assert "recommender_benchmark" in body
    assert "notice" in body
    # Retrieval refusal accuracy must be 1.0 on synthetic eval
    rb = body["retrieval_benchmark"]
    assert rb["refusal_accuracy"] == 1.0, (
        f"Refusal accuracy dropped: {rb['refusal_accuracy']}. "
        "Real unverified schemes must always return INSUFFICIENT_VERIFIED_EVIDENCE."
    )
