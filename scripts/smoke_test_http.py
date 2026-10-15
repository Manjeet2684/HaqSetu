"""Dependency-free HTTP smoke test for a running HaqSetu instance.

Start the application first, for example:
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --no-access-log
Then run:
    python scripts/smoke_test_http.py --base-url http://127.0.0.1:8765

This script checks API contracts and safety properties; it does not replace pytest
or browser-based visual testing.
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any


def request_json(
    base_url: str,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    expected_status: int = 200,
) -> tuple[Any, dict[str, str], int]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(base_url.rstrip("/") + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
            response_body = response.read()
            response_headers = {key.lower(): value for key, value in response.headers.items()}
    except HTTPError as exc:
        status = exc.code
        response_body = exc.read()
        response_headers = {key.lower(): value for key, value in exc.headers.items()}
    except URLError as exc:
        raise RuntimeError(
            f"Cannot reach {base_url}. Start the server and verify the port. Cause: {exc.reason}"
        ) from exc

    if status != expected_status:
        raise AssertionError(
            f"{method} {path}: expected HTTP {expected_status}, received {status}; "
            f"body={response_body[:300]!r}"
        )

    content_type = response_headers.get("content-type", "")
    if "json" in content_type.lower():
        try:
            parsed_body: Any = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AssertionError(f"{method} {path}: server returned invalid JSON") from exc
    else:
        parsed_body = response_body.decode("utf-8", errors="replace")
    return parsed_body, response_headers, status


def run(base_url: str) -> int:
    checks: list[str] = []

    def passed(name: str) -> None:
        checks.append(name)
        print(f"PASS {len(checks):02d} — {name}")

    health, headers, _ = request_json(base_url, "GET", "/api/health")
    assert health["status"] == "ok"
    assert health["real_scheme_count"] == 2
    assert health["assessable_real_scheme_count"] == 0
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    passed("health and defensive headers")

    homepage, _, _ = request_json(base_url, "GET", "/")
    assert homepage.count("haqsetu_api_client.js") == 1
    assert homepage.count("haqsetu_p6_enhancements.css") == 1
    assert "py -m http.server 8000" not in homepage
    passed("homepage and single asset injection")

    schemes, _, _ = request_json(base_url, "GET", "/api/schemes")
    ids = {item["id"] for item in schemes}
    assert {"pmsp-central-sector", "up-pre-matric-scholarship"}.issubset(ids)
    assert "demo-assessable" not in ids
    passed("real catalogue excludes demo fixtures")

    detail, _, _ = request_json(base_url, "GET", "/api/schemes/pmsp-central-sector")
    assert detail["safe_for_automated_assessment"] is False
    assert detail["scheme"]["readiness"] == "LISTING_ONLY"
    passed("real scheme verification state")

    real_assessment, _, _ = request_json(
        base_url,
        "POST",
        "/api/assess",
        payload={"scheme_id": "pmsp-central-sector", "answers": {}},
    )
    assert real_assessment["effective_readiness"] == "LISTING_ONLY"
    assert real_assessment["applicant_outcome"] is None
    passed("real assessment fails closed")

    demos, _, _ = request_json(base_url, "GET", "/api/demo/scenarios")
    fictional = next(item for item in demos["scenarios"] if item["id"] == "demo-assessable")
    assert fictional["is_fictional"] is True
    assert "FICTIONAL DEMO WARNING" in fictional["fictional_warning"]
    passed("demo scenario is explicitly fictional")

    demo_result, _, _ = request_json(
        base_url,
        "POST",
        "/api/demo/assess",
        payload={
            "scenario_id": "demo-assessable",
            "answers": {
                "q-marks": "above_80",
                "q-income": "below_450000",
                "q-enrollment": "yes",
                "q-other-scholarship": "no",
            },
        },
    )
    assert demo_result["is_fictional"] is True
    assert "FICTIONAL DEMO WARNING" in (demo_result["fictional_warning"] or "")
    passed("fictional assessment includes warning")

    request_json(base_url, "GET", "/api/evidence/pmsp-central-sector")
    request_json(base_url, "GET", "/api/evidence/demo-assessable?include_demo=true")
    passed("real and fictional evidence endpoints respond")

    real_answer, _, _ = request_json(
        base_url,
        "POST",
        "/api/ask",
        payload={
            "query": "What is the family income ceiling?",
            "scheme_id": "pmsp-central-sector",
            "include_fictional_demo": False,
        },
    )
    assert real_answer["status"] == "INSUFFICIENT_VERIFIED_EVIDENCE"
    demo_answer, _, _ = request_json(
        base_url,
        "POST",
        "/api/ask",
        payload={
            "query": "What is the family income limit from all sources?",
            "scheme_id": "demo-assessable",
            "include_fictional_demo": True,
        },
    )
    assert demo_answer["status"] == "SUPPORTED_MATCH"
    passed("policy Q&A refusal and fictional evidence retrieval")

    assistant, _, _ = request_json(
        base_url,
        "POST",
        "/api/assistant",
        payload={"query": "Which scholarships are available for college students?"},
    )
    assert assistant["intent"]["predicted_intent"] == "find_scheme"
    assert assistant["recommendations"]
    ambiguous, _, _ = request_json(
        base_url, "POST", "/api/assistant", payload={"query": "scholarship"}
    )
    assert ambiguous["intent"]["predicted_intent"] == "out_of_scope"
    assert ambiguous["recommendations"] == []
    assert ambiguous["ask_response"] is None
    passed("assistant routes clear query and abstains on ambiguous query")

    recommendations, _, _ = request_json(
        base_url,
        "POST",
        "/api/recommend",
        payload={"query": "college scholarship central government", "top_k": 3},
    )
    assert recommendations["recommendations"]
    assert "NOT an eligibility assessment" in recommendations["disclaimer"]
    passed("recommendations preserve non-eligibility disclaimer")

    metrics, _, _ = request_json(base_url, "GET", "/api/ml/metrics")
    assert {"intent_classifier", "retrieval_benchmark", "recommender_benchmark"}.issubset(metrics)
    assert "not generalisation accuracy" in metrics["notice"].lower()
    passed("ML metrics include synthetic benchmark notice")

    request_json(base_url, "GET", "/data/fixtures/demo.json")
    for path in (
        "/data/schemes.json",
        "/data/eval_queries.json",
        "/data/ml/intent_dataset.json",
        "/data/ml/recommendation_eval.json",
    ):
        request_json(base_url, "GET", path, expected_status=404)
    passed("only the intended demo fixture is publicly served")

    _, validation_headers, _ = request_json(
        base_url,
        "POST",
        "/api/assess",
        payload={"answers": "invalid"},
        expected_status=422,
    )
    assert validation_headers.get("x-content-type-options") == "nosniff"
    _, oversized_headers, _ = request_json(
        base_url,
        "POST",
        "/api/ask",
        payload={"query": "x" * 40_000},
        expected_status=413,
    )
    assert oversized_headers.get("x-content-type-options") == "nosniff"
    passed("validation and request-size limit")

    print(f"\nHTTP SMOKE TEST SUMMARY: {len(checks)} checks passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8765",
        help="Base URL for an already-running HaqSetu server",
    )
    args = parser.parse_args()
    try:
        return run(args.base_url)
    except (AssertionError, RuntimeError, StopIteration) as exc:
        print(f"FAIL — {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
