"""Pytest suite for HaqSetu Stage P5 source-grounded policy retrieval and refusal safeguards."""

from __future__ import annotations

from pathlib import Path

from app.catalog import SchemeCatalogService
from app.retriever import PolicyClauseRetriever, evaluate_retrieval_benchmark
from app.schemas import EvidenceReference, RetrievalStatus, SchemeDataType, SchemeReadiness, SchemeRecord


def test_retriever_refuses_unverified_real_schemes() -> None:
    """Real schemes with no verified policy evidence must return INSUFFICIENT_VERIFIED_EVIDENCE."""
    catalog = SchemeCatalogService()
    res = catalog.retriever.answer_query(
        "What is the parental income limit and last date?",
        scheme_id="pmsp-central-sector",
        include_fictional_demo=False,
    )
    assert res.status == RetrievalStatus.INSUFFICIENT_VERIFIED_EVIDENCE
    assert res.passages == []
    assert res.is_fictional_context is False


def test_retriever_isolates_fictional_demo_from_real_queries() -> None:
    """Querying demo-assessable without include_fictional_demo=True is refused to prevent cross-contamination."""
    catalog = SchemeCatalogService()

    blocked = catalog.retriever.answer_query(
        "What percentage marks are needed in the qualifying examination?",
        scheme_id="demo-assessable",
        include_fictional_demo=False,
    )
    assert blocked.status == RetrievalStatus.INSUFFICIENT_VERIFIED_EVIDENCE
    assert blocked.passages == []

    allowed = catalog.retriever.answer_query(
        "What percentage marks are needed in the qualifying examination?",
        scheme_id="demo-assessable",
        include_fictional_demo=True,
    )
    assert allowed.status == RetrievalStatus.SUPPORTED_MATCH
    assert len(allowed.passages) >= 1
    assert allowed.passages[0].evidence_id == "ev-001"
    assert allowed.is_fictional_context is True
    assert allowed.fictional_warning is not None


def test_retriever_no_match_refusal_for_out_of_scope_queries() -> None:
    """Out-of-scope questions return NO_RELEVANT_MATCH and zero passages."""
    catalog = SchemeCatalogService()
    res = catalog.retriever.answer_query(
        "How do I apply for a commercial driving licence and passport renewal?",
        scheme_id="demo-assessable",
        include_fictional_demo=True,
    )
    assert res.status == RetrievalStatus.NO_RELEVANT_MATCH
    assert res.passages == []


def test_retriever_returns_verified_real_passage_with_exact_source_metadata() -> None:
    """When a real scheme has human-verified evidence, retrieval cites title, URL, section, and excerpt."""
    verified_ev = EvidenceReference(
        id="ev-real-101",
        source_title="Ministry of Education CSSS Guidelines",
        source_url="https://scholarships.gov.in/public/schemeGuidelines/FAQ_DOHE_CSSS.pdf",
        academic_cycle="2025-26",
        section_or_page="Clause 4.2, Page 3",
        excerpt="Gross parental/family income from all sources must not exceed Rs. 4,50,000 per annum.",
        access_date="2026-10-14",
        verified=True,
        verification_date="2026-10-14",
        verified_by="Human Auditor",
        fictional=False,
    )
    real_scheme = SchemeRecord(
        id="real-verified-sample",
        name="Verified Sample Scholarship",
        short_name="Verified Sample",
        issuing_body="Ministry of Education",
        readiness=SchemeReadiness.ASSESSABLE,
        data_type=SchemeDataType.REAL_VERIFIED,
        is_fictional=False,
        academic_year_verified="2025-26",
        evidence_registry={"ev-real-101": verified_ev},
    )
    retriever = PolicyClauseRetriever([real_scheme])

    res = retriever.answer_query(
        "What is the maximum parental family income per annum?",
        scheme_id="real-verified-sample",
        include_fictional_demo=False,
    )
    assert res.status == RetrievalStatus.SUPPORTED_MATCH
    assert len(res.passages) == 1
    top = res.passages[0]
    assert top.evidence_id == "ev-real-101"
    assert top.source_title == "Ministry of Education CSSS Guidelines"
    assert top.source_url == "https://scholarships.gov.in/public/schemeGuidelines/FAQ_DOHE_CSSS.pdf"
    assert top.section_or_page == "Clause 4.2, Page 3"
    assert "4,50,000" in top.excerpt
    assert "does not evaluate or confirm your personal eligibility" in res.eligibility_separation_notice


def test_evaluation_benchmark_corpus_runs_and_meets_targets() -> None:
    """Verify that data/eval_queries.json runs cleanly and achieves reasonable precision and refusal accuracy."""
    repo_root = Path(__file__).resolve().parent.parent
    eval_path = repo_root / "data" / "eval_queries.json"
    if eval_path.exists():
        catalog = SchemeCatalogService()
        metrics = evaluate_retrieval_benchmark(catalog.retriever, eval_path)
        assert metrics["total_queries"] == 10
        # At least some supported queries must hit
        assert metrics["top1_accuracy"] >= 0.5
        assert metrics["top3_recall"] >= 0.5
        # Refusal queries (eval-07, eval-08) must be correctly refused
        assert metrics["refusal_accuracy"] >= 0.8
