"""FastAPI service implementing EIP API (Contract v0.1 compatible + v0.2 discovery)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from core.engine import AssessmentEngine
from core.models import (
    CONTRACT_V02_VERSION,
    CONTRACT_VERSION,
    AssessmentResponse,
    CapabilitiesResponse,
    ClaimRequest,
    EvidenceListResponse,
    HealthResponse,
    PolicyListResponse,
)
from core.policy import (
    ClaimValidationError,
    PolicyRegistry,
    UnknownPolicyError,
    UnsupportedClaimTypeError,
)
from core.store import EvidenceStore, FileEvidenceStore
from policies import build_default_registry

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def create_app(
    evidence_path: str | Path | None = None,
    registry: PolicyRegistry | None = None,
    store: EvidenceStore | None = None,
) -> FastAPI:
    """Create the EIP FastAPI application with pluggable policy registry and store."""
    active_registry = registry if registry is not None else build_default_registry()
    active_store = store if store is not None else FileEvidenceStore(evidence_path)
    engine = AssessmentEngine(active_registry)

    application = FastAPI(
        title="Evidence Integrity Platform (EIP) API",
        version="0.2.0",
        description=(
            "Domain-independent, deterministic evidence assessment API "
            "(Contract v0.1 compatible; extended with v0.2 policy discovery, "
            "temporal integrity modes, and source independence analysis). "
            "Not a truth oracle or operational safety service."
        ),
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
        expose_headers=["X-EIP-Assessed-At"],
    )

    @application.get("/health", response_model=HealthResponse, tags=["system"])
    def get_health() -> HealthResponse:
        return HealthResponse(status="ok", contract_version=CONTRACT_VERSION)

    @application.get(
        "/v1/capabilities",
        response_model=CapabilitiesResponse,
        tags=["discovery"],
    )
    def get_capabilities() -> CapabilitiesResponse:
        return CapabilitiesResponse(
            contract_version=CONTRACT_V02_VERSION,
            supported_claim_types=active_registry.supported_claim_types(),
            supported_evidence_kinds=active_registry.supported_evidence_kinds(),
            registered_policy_ids=active_registry.registered_policy_ids(),
        )

    @application.get(
        "/v1/policies",
        response_model=PolicyListResponse,
        tags=["discovery"],
    )
    def get_policies() -> PolicyListResponse:
        return PolicyListResponse(
            contract_version=CONTRACT_V02_VERSION,
            policies=active_registry.list_specs(),
        )

    @application.get(
        "/v1/evidence",
        response_model=EvidenceListResponse,
        tags=["evidence"],
    )
    def get_evidence() -> EvidenceListResponse:
        items = active_store.load_all()
        return EvidenceListResponse(items=items)

    @application.post(
        "/v1/assess",
        response_model=AssessmentResponse,
        tags=["assessment"],
    )
    def post_assess(claim: ClaimRequest, response: Response) -> AssessmentResponse:
        items = active_store.load_all()
        try:
            result = engine.assess(claim, items)
        except UnsupportedClaimTypeError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "unsupported_claim_type",
                    "message": str(exc),
                    "claim_type": exc.claim_type,
                    "supported_claim_types": exc.supported_claim_types,
                },
            ) from exc
        except UnknownPolicyError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "unknown_policy",
                    "message": str(exc),
                    "policy_id": exc.policy_id,
                    "registered_policy_ids": exc.registered_policy_ids,
                },
            ) from exc
        except ClaimValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "claim_validation_error",
                    "message": exc.message,
                    "field": exc.field_path,
                },
            ) from exc

        assessed_header = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        response.headers["X-EIP-Assessed-At"] = assessed_header
        return result

    return application


app = create_app()
