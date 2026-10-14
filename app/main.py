"""FastAPI application integrating P2/P3 engine & planner, P5 retrieval, and P1/P6 static UI."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.catalog import DEFAULT_REPO_ROOT, SchemeCatalogService
from app.engine import evaluate_scheme
from app.schemas import (
    FICTIONAL_DEMO_WARNING,
    AskRequest,
    AskResponse,
    AssessmentRequest,
    AssessmentResponse,
    AssistantRequest,
    AssistantResponse,
    DemoAssessRequest,
    HealthResponse,
    RecommendationRequest,
    RecommendationResponse,
    SchemeDetailResponse,
    SchemeReadiness,
    SchemeSummary,
    SchemeValidationError,
)

MAX_REQUEST_BODY_BYTES = 32_768  # 32 KB hard limit


def create_app(
    *,
    schemes_path: str | Path | None = None,
    demo_path: str | Path | None = None,
    frontend_root: str | Path | None = None,
) -> FastAPI:
    """
    Create and configure the HaqSetu FastAPI application.

    Privacy & Security Design:
    - Stateless evaluation: applicant answers are never stored on disk or logged.
    - Enforces 32 KB request body limit and sets defensive HTTP headers (nosniff, DENY).
    - Strictly separates /api/assess (real schemes only) from /api/demo/assess (fictional demo).
    """
    app = FastAPI(
        title="HaqSetu — AI Welfare and Scholarship Navigator",
        description=(
            "Evidence-grounded scholarship discovery, deterministic three-valued eligibility "
            "evaluation, dependency-aware action planning, and verified-source policy retrieval."
        ),
        version="1.0.0",
    )

    ui_root = Path(frontend_root or DEFAULT_REPO_ROOT)
    catalog_holder: dict[str, SchemeCatalogService | None] = {"service": None}

    def get_catalog() -> SchemeCatalogService:
        if catalog_holder["service"] is None:
            try:
                catalog_holder["service"] = SchemeCatalogService(
                    schemes_path=schemes_path,
                    demo_path=demo_path,
                )
            except SchemeValidationError as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"Catalogue initialization error: {exc}",
                ) from exc
        return catalog_holder["service"]

    @app.middleware("http")
    async def security_and_privacy_middleware(request: Request, call_next: Any) -> Response:
        """
        Body-size limit + defensive security headers.

        Strategy for requests without Content-Length:
        We use asyncio.wait_for to bound the body read to a reasonable timeout, then
        check actual length. This prevents unbounded streaming accumulation.
        """
        content_length_header = request.headers.get("content-length")
        if content_length_header is not None:
            try:
                cl = int(content_length_header)
            except (ValueError, OverflowError):
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Malformed Content-Length header."},
                )
            if cl > MAX_REQUEST_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request payload exceeds the 32 KB maximum size limit."},
                )

        # Read the body and check actual length (handles chunked/no-length requests too).
        # We bound with a short timeout to avoid stalling on slow large uploads.
        try:
            body_bytes: bytes = await asyncio.wait_for(request.body(), timeout=10.0)
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body read timed out (payload too large or slow)."},
            )
        if len(body_bytes) > MAX_REQUEST_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request payload exceeds the 32 KB maximum size limit."},
            )

        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Return readable validation errors without echoing raw sensitive answer payloads
        clean_errors = [
            {
                "loc": [str(part) for part in err.get("loc", ())],
                "msg": err.get("msg", "Invalid input"),
                "type": err.get("type", "value_error"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request validation failed. Check field types and required parameters.",
                "errors": clean_errors,
            },
        )

    @app.get("/api/health", response_model=HealthResponse, tags=["System"])
    def get_health(catalog: SchemeCatalogService = Depends(get_catalog)) -> HealthResponse:
        real_summaries = catalog.list_real_summaries()
        assessable_count = sum(
            1 for s in real_summaries if s.readiness == SchemeReadiness.ASSESSABLE
        )
        return HealthResponse(
            status="ok",
            real_scheme_count=len(real_summaries),
            assessable_real_scheme_count=assessable_count,
            demo_scenario_count=len(catalog.list_demo_scenarios()),
        )

    @app.get("/api/schemes", response_model=list[SchemeSummary], tags=["Schemes"])
    def list_schemes(
        q: str | None = Query(default=None, max_length=120, description="Search keyword"),
        readiness: SchemeReadiness | None = Query(default=None),
        ministry: str | None = Query(default=None, max_length=120),
        catalog: SchemeCatalogService = Depends(get_catalog),
    ) -> list[SchemeSummary]:
        return catalog.list_real_summaries(q=q, readiness=readiness, ministry=ministry)

    @app.get(
        "/api/schemes/{scheme_id}",
        response_model=SchemeDetailResponse,
        tags=["Schemes"],
    )
    def get_scheme_detail(
        scheme_id: str,
        catalog: SchemeCatalogService = Depends(get_catalog),
    ) -> SchemeDetailResponse:
        # Explicitly reject demo fixture IDs with a clear message
        if catalog.is_demo_scenario_id(scheme_id):
            raise HTTPException(
                status_code=404,
                detail=(
                    f"'{scheme_id}' is a fictional demo scenario and does not exist in the real "
                    "scheme catalogue. Use /api/demo/scenarios for demonstration fixtures."
                ),
            )
        detail = catalog.get_real_scheme_detail(scheme_id)
        if detail is None:
            raise HTTPException(
                status_code=404,
                detail=f"Real scheme '{scheme_id}' not found.",
            )
        return detail

    @app.post("/api/assess", response_model=AssessmentResponse, tags=["Assessment"])
    def assess_real_scheme(
        payload: AssessmentRequest,
        catalog: SchemeCatalogService = Depends(get_catalog),
    ) -> AssessmentResponse:
        if catalog.is_demo_scenario_id(payload.scheme_id):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Fictional demo scenario '{payload.scheme_id}' cannot be assessed via the real "
                    "/api/assess endpoint. Use POST /api/demo/assess for fictional demonstrations."
                ),
            )
        scheme = catalog.get_real_scheme(payload.scheme_id)
        if scheme is None:
            raise HTTPException(
                status_code=404,
                detail=f"Real scheme '{payload.scheme_id}' not found.",
            )
        return evaluate_scheme(
            scheme,
            answers=payload.answers,
            completed_action_ids=payload.completed_action_ids,
        )

    @app.get("/api/demo/scenarios", tags=["Fictional Demo"])
    def list_demo_scenarios(
        catalog: SchemeCatalogService = Depends(get_catalog),
    ) -> dict[str, Any]:
        """
        Return all demo scenarios from data/fixtures/demo.json with per-record type labelling.
        Records are explicitly identified by their data_type so callers can distinguish
        truly fictional fixtures from REAL_STUB candidates stored in the fixture file.
        """
        scenarios = catalog.list_demo_scenarios()
        scenario_list = []
        for s in scenarios:
            entry = {
                "id": s.id,
                "name": s.name,
                "short_name": s.short_name,
                "readiness": s.readiness,
                "data_type": s.data_type,
                "is_fictional": s.is_fictional,
            }
            if s.is_fictional:
                entry["fictional_warning"] = FICTIONAL_DEMO_WARNING
            scenario_list.append(entry)
        return {
            "note": (
                "This endpoint returns all records from data/fixtures/demo.json. "
                "Records are identified per their data_type: FICTIONAL_FIXTURE records are "
                "demo scenarios; REAL_STUB records are real scheme candidates stored here for "
                "reference. Check is_fictional and data_type per record."
            ),
            "scenarios": scenario_list,
        }

    @app.post(
        "/api/demo/assess",
        response_model=AssessmentResponse,
        tags=["Fictional Demo"],
    )
    def assess_demo_scenario(
        payload: DemoAssessRequest,
        catalog: SchemeCatalogService = Depends(get_catalog),
    ) -> AssessmentResponse:
        scenario = catalog.get_demo_scenario(payload.scenario_id)
        if scenario is None:
            raise HTTPException(
                status_code=404,
                detail=f"Demo scenario '{payload.scenario_id}' not found.",
            )
        return evaluate_scheme(
            scenario,
            answers=payload.answers,
            completed_action_ids=payload.completed_action_ids,
        )

    @app.get("/api/evidence/{scheme_id}", tags=["Evidence & Retrieval"])
    def get_scheme_evidence(
        scheme_id: str,
        include_demo: bool = Query(default=False),
        catalog: SchemeCatalogService = Depends(get_catalog),
    ) -> dict[str, Any]:
        scheme = catalog.get_real_scheme(scheme_id)
        if scheme is None and include_demo:
            scheme = catalog.get_demo_scenario(scheme_id)
        if scheme is None:
            raise HTTPException(
                status_code=404,
                detail=f"Scheme '{scheme_id}' not found (or requires include_demo=true for demo fixtures).",
            )
        return {
            "scheme_id": scheme.id,
            "scheme_name": scheme.name,
            "readiness": scheme.readiness,
            "is_fictional": scheme.is_fictional,
            "data_type": scheme.data_type,
            "fictional_warning": FICTIONAL_DEMO_WARNING if scheme.is_fictional else None,
            "human_verified": scheme.human_verified,
            "academic_year_verified": scheme.academic_year_verified,
            "official_source_url": scheme.official_source_url,
            "evidence_count": len(scheme.evidence_registry),
            "evidence": [ev.model_dump() for ev in scheme.evidence_registry.values()],
        }

    @app.post("/api/ask", response_model=AskResponse, tags=["Evidence & Retrieval"])
    def ask_policy_question(
        payload: AskRequest,
        catalog: SchemeCatalogService = Depends(get_catalog),
    ) -> AskResponse:
        return catalog.retriever.answer_query(
            payload.query,
            scheme_id=payload.scheme_id,
            include_fictional_demo=payload.include_fictional_demo,
            top_k=payload.top_k,
        )

    @app.post(
        "/api/recommend",
        response_model=RecommendationResponse,
        tags=["AI/ML — P9"],
    )
    def recommend_schemes(
        payload: RecommendationRequest,
        catalog: SchemeCatalogService = Depends(get_catalog),
    ) -> RecommendationResponse:
        """
        Content-based TF-IDF scheme recommendation.

        NOT an eligibility assessment. Scores reflect keyword similarity to
        catalogue metadata only. See disclaimer in response.
        """
        return catalog.recommend_schemes(
            payload.query,
            top_k=payload.top_k,
            include_fictional=payload.include_fictional,
        )

    @app.post(
        "/api/assistant",
        response_model=AssistantResponse,
        tags=["AI/ML — P9"],
    )
    def assistant_query(
        payload: AssistantRequest,
        catalog: SchemeCatalogService = Depends(get_catalog),
    ) -> AssistantResponse:
        """
        Unified assistant: classify intent, route advice, and optionally retrieve Q&A passages.

        Never determines eligibility. See intent.confidence_notice in response.
        """
        return catalog.handle_assistant_query(
            payload.query,
            scheme_id=payload.scheme_id,
            include_fictional_demo=payload.include_fictional_demo,
            top_k=payload.top_k,
        )

    @app.get(
        "/api/ml/metrics",
        tags=["AI/ML — P9"],
    )
    def get_ml_metrics(
        catalog: SchemeCatalogService = Depends(get_catalog),
    ) -> dict:
        """
        Run all ML/retrieval benchmarks and return measured metrics.

        All metrics are synthetic smoke benchmarks. See notice in response.
        """
        return catalog.get_ml_metrics()

    # Mount static directories (css/, js/, data/) and serve index.html with P6 progressive bridge
    for folder_name in ("css", "js", "data"):
        folder_path = ui_root / folder_name
        if folder_path.exists() and folder_path.is_dir():
            app.mount(
                f"/{folder_name}",
                StaticFiles(directory=str(folder_path)),
                name=f"static_{folder_name}",
            )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def serve_index() -> HTMLResponse:
        index_path = ui_root / "index.html"
        if not index_path.exists():
            return HTMLResponse(
                content="<h1>HaqSetu API is running. Place index.html in project root.</h1>",
                status_code=200,
            )
        raw_html = index_path.read_text(encoding="utf-8")
        # Non-destructively inject P6 CSS & API client bridge if not already referenced
        if "haqsetu_p6_enhancements.css" not in raw_html and "</head>" in raw_html:
            raw_html = raw_html.replace(
                "</head>",
                '  <link rel="stylesheet" href="/css/haqsetu_p6_enhancements.css">\n</head>',
                1,
            )
        if "haqsetu_api_client.js" not in raw_html and "</body>" in raw_html:
            raw_html = raw_html.replace(
                "</body>",
                '  <script src="/js/haqsetu_api_client.js" defer></script>\n</body>',
                1,
            )
        return HTMLResponse(content=raw_html, status_code=200)

    return app


app = create_app()
