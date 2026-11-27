"""FastAPI service implementing EIP shared contract v0.1."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.assessment import assess_claim
from core.models import (
    CONTRACT_VERSION,
    AssessmentResponse,
    ClaimRequest,
    EvidenceListResponse,
    HealthResponse,
)
from core.store import load_evidence_file

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def create_app(evidence_path: str | Path | None = None) -> FastAPI:
    """Create the EIP FastAPI application."""
    application = FastAPI(
        title="Evidence Integrity Platform (EIP) API",
        version="0.1.0",
        description=(
            "Deterministic geospatial and temporal evidence assessment API "
            "(Contract v0.1). Not a truth oracle or operational safety service."
        ),
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    @application.get("/health", response_model=HealthResponse, tags=["system"])
    def get_health() -> HealthResponse:
        return HealthResponse(status="ok", contract_version=CONTRACT_VERSION)

    @application.get("/v1/evidence", response_model=EvidenceListResponse, tags=["evidence"])
    def get_evidence() -> EvidenceListResponse:
        items = load_evidence_file(evidence_path)
        return EvidenceListResponse(items=items)

    @application.post("/v1/assess", response_model=AssessmentResponse, tags=["assessment"])
    def post_assess(claim: ClaimRequest) -> AssessmentResponse:
        items = load_evidence_file(evidence_path)
        return assess_claim(claim, items)

    return application


app = create_app()
