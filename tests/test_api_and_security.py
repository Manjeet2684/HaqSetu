"""Integration, security, and privacy tests for HaqSetu Stage P4-P7 FastAPI application."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import SchemeValidationError, load_real_schemes


@pytest.fixture()
def client() -> TestClient:
    """Create a FastAPI TestClient wired to the repository data files."""
    app = create_app()
    return TestClient(app)


def test_health_endpoint_and_security_headers(client: TestClient) -> None:
    """GET /api/health returns 200 OK, accurate counts, and defensive HTTP headers."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["real_scheme_count"] == 2
    assert body["assessable_real_scheme_count"] == 0
    assert body["demo_scenario_count"] == 2
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"


def test_list_real_schemes_excludes_fictional_and_supports_search(client: TestClient) -> None:
    """GET /api/schemes returns only real schemes and supports search/filter parameters."""
    resp = client.get("/api/schemes")
    assert resp.status_code == 200
    items = resp.json()
    ids = [item["id"] for item in items]
    assert "pmsp-central-sector" in ids
    assert "up-pre-matric-scholarship" in ids
    assert "demo-assessable" not in ids
    assert all(item["is_fictional"] is False for item in items)

    # Search filter
    resp_filtered = client.get("/api/schemes", params={"q": "Uttar Pradesh"})
    assert resp_filtered.status_code == 200
    filtered_items = resp_filtered.json()
    assert len(filtered_items) == 1
    assert filtered_items[0]["id"] == "up-pre-matric-scholarship"


def test_scheme_detail_and_not_found_and_fictional_rejection(client: TestClient) -> None:
    """GET /api/schemes/{id} returns verification checklist + official channels, and 404s on unknown/demo IDs."""
    resp = client.get("/api/schemes/pmsp-central-sector")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["safe_for_automated_assessment"] is False
    assert len(detail["Pending_verification_requirements"]) >= 3
    assert len(detail["scheme"]["support_channels"]) >= 2

    resp_missing = client.get("/api/schemes/non-existent-scheme")
    assert resp_missing.status_code == 404

    # demo-assessable must NOT appear in real scheme endpoint
    resp_demo = client.get("/api/schemes/demo-assessable")
    assert resp_demo.status_code == 404
    # demo-listing-only: it's in demo fixture only, so should also 404 from real endpoint
    resp_listing_demo = client.get("/api/schemes/demo-listing-only")
    assert resp_listing_demo.status_code == 404


def test_real_assess_endpoint_keeps_listing_only_null_and_rejects_fictional(
    client: TestClient,
) -> None:
    """POST /api/assess returns null outcome for LISTING_ONLY real schemes and 400 for fictional demo IDs."""
    resp_real = client.post(
        "/api/assess",
        json={
            "scheme_id": "pmsp-central-sector",
            "answers": {"q-marks": "above_80"},
            "completed_action_ids": [],
        },
    )
    assert resp_real.status_code == 200
    body = resp_real.json()
    assert body["effective_readiness"] == "LISTING_ONLY"
    assert body["applicant_outcome"] is None

    resp_demo = client.post(
        "/api/assess",
        json={"scheme_id": "demo-assessable", "answers": {}},
    )
    assert resp_demo.status_code == 400
    assert "fictional demo" in resp_demo.json()["detail"].lower()


def test_demo_assess_endpoint_evaluates_dynamically_with_fictional_warning(
    client: TestClient,
) -> None:
    """POST /api/demo/assess dynamically computes outcomes, gates submission when unresolved, and warns user."""
    # Unresolved income -> NEEDS_VERIFICATION, submission action GATED even if passed in completed_action_ids
    resp_unresolved = client.post(
        "/api/demo/assess",
        json={
            "scenario_id": "demo-assessable",
            "answers": {
                "q-marks": "above_80",
                "q-income": "unknown",
                "q-enrollment": "yes",
                "q-other-scholarship": "no",
            },
            "completed_action_ids": ["act-submit-application"],
        },
    )
    assert resp_unresolved.status_code == 200
    data_unres = resp_unresolved.json()
    assert data_unres["is_fictional"] is True
    assert "FICTIONAL DEMO WARNING" in (data_unres["fictional_warning"] or "")
    assert data_unres["applicant_outcome"] == "NEEDS_VERIFICATION"
    submit_act = next(
        a for a in data_unres["action_plan"] if a["id"] == "act-submit-application"
    )
    assert submit_act["status"] == "GATED"

    # All conditions met -> ELIGIBLE
    resp_elig = client.post(
        "/api/demo/assess",
        json={
            "scenario_id": "demo-assessable",
            "answers": {
                "q-marks": "above_80",
                "q-income": "below_450000",
                "q-enrollment": "yes",
                "q-other-scholarship": "no",
            },
            "completed_action_ids": [
                "act-gather-income",
                "act-gather-marksheet",
                "act-verify-eligibility",
            ],
        },
    )
    assert resp_elig.status_code == 200
    data_elig = resp_elig.json()
    assert data_elig["applicant_outcome"] == "ELIGIBLE"
    submit_ready = next(
        a for a in data_elig["action_plan"] if a["id"] == "act-submit-application"
    )
    assert submit_ready["status"] == "READY"


def test_ask_endpoint_refusal_and_demo_retrieval(client: TestClient) -> None:
    """POST /api/ask refuses unverified real schemes and retrieves grounded demo clauses when requested."""
    resp_real = client.post(
        "/api/ask",
        json={
            "query": "What is the family income ceiling?",
            "scheme_id": "pmsp-central-sector",
            "include_fictional_demo": False,
        },
    )
    assert resp_real.status_code == 200
    assert resp_real.json()["status"] == "INSUFFICIENT_VERIFIED_EVIDENCE"

    resp_demo = client.post(
        "/api/ask",
        json={
            "query": "What is the family income limit from all sources?",
            "scheme_id": "demo-assessable",
            "include_fictional_demo": True,
        },
    )
    assert resp_demo.status_code == 200
    demo_body = resp_demo.json()
    assert demo_body["status"] == "SUPPORTED_MATCH"
    assert demo_body["passages"][0]["evidence_id"] == "ev-002"


def test_malformed_and_oversized_payload_handling(client: TestClient) -> None:
    """Invalid input returns 422 without leaking stack traces; oversized payloads return 413."""
    resp_invalid = client.post("/api/assess", json={"answers": "not-a-dict"})
    assert resp_invalid.status_code == 422
    assert "errors" in resp_invalid.json()

    oversized_body = "x" * 40_000
    resp_large = client.post(
        "/api/ask",
        content=oversized_body,
        headers={"Content-Type": "application/json"},
    )
    assert resp_large.status_code == 413


def test_demo_scenarios_endpoint_labels_records_correctly(client: TestClient) -> None:
    """GET /api/demo/scenarios labels fictional fixtures separately from REAL_STUB records."""
    resp = client.get("/api/demo/scenarios")
    assert resp.status_code == 200
    body = resp.json()
    assert "scenarios" in body
    scenarios = body["scenarios"]

    # Find each by ID
    assessable = next((s for s in scenarios if s["id"] == "demo-assessable"), None)
    listing = next((s for s in scenarios if s["id"] == "demo-listing-only"), None)

    assert assessable is not None
    assert assessable["is_fictional"] is True
    assert assessable["data_type"] == "FICTIONAL_FIXTURE"
    assert "fictional_warning" in assessable

    assert listing is not None
    assert listing["is_fictional"] is False
    assert listing["data_type"] == "REAL_STUB"
    # REAL_STUB record must NOT have a fictional_warning key
    assert "fictional_warning" not in listing


def test_missing_and_malformed_data_files_fail_clearly(tmp_path: Path) -> None:
    """Missing or corrupted JSON files raise explicit SchemeValidationError messages."""
    missing_file = tmp_path / "does_not_exist.json"
    with pytest.raises(SchemeValidationError, match="not found"):
        load_real_schemes(missing_file)

    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("{bad json", encoding="utf-8")
    with pytest.raises(SchemeValidationError, match="Malformed JSON"):
        load_real_schemes(corrupt_file)
