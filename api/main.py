"""FastAPI service implementing EIP API (Contract v0.1 compatible + v0.2/v0.5 extensions)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from core.engine import AssessmentEngine
from core.graph import AssessmentGraphResponse, build_evidence_graph
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
from core.store import REPO_ROOT, EvidenceStore, FileEvidenceStore
from policies import build_default_registry

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

DEFAULT_CONTEXT_PATH = REPO_ROOT / "sample_data" / "context" / "lough_funshinagh_context.json"


def _dispatch_assessment(
    engine: AssessmentEngine,
    claim: ClaimRequest,
    items,
) -> AssessmentResponse:
    try:
        return engine.assess(claim, items)
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
        version="0.5.0",
        description=(
            "Domain-independent, deterministic evidence assessment API "
            "(Contract v0.1 compatible; extended with policy discovery, "
            "temporal integrity modes, source independence analysis, "
            "evidence graphs, and local Galileo OSNMA verification). "
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
        result = _dispatch_assessment(engine, claim, items)
        assessed_header = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        response.headers["X-EIP-Assessed-At"] = assessed_header
        return result

    @application.post(
        "/v1/assess/graph",
        response_model=AssessmentGraphResponse,
        tags=["assessment"],
    )
    def post_assess_graph(
        claim: ClaimRequest,
        response: Response,
    ) -> AssessmentGraphResponse:
        items = active_store.load_all()
        result = _dispatch_assessment(engine, claim, items)
        ev_by_id = {ev.id: ev for ev in items}
        assessed_ev = [ev_by_id[eid] for eid in result.evidence_ids if eid in ev_by_id]
        graph = build_evidence_graph(claim, assessed_ev, result)
        assessed_header = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        response.headers["X-EIP-Assessed-At"] = assessed_header
        return AssessmentGraphResponse(
            assessment=result,
            evidence=assessed_ev,
            graph=graph,
        )

    @application.post("/v1/galileo/tamper-demo", tags=["galileo"])
    def post_galileo_tamper_demo(response: Response) -> dict[str, Any]:
        """Run controlled offline 1-bit tamper comparison against recorded Galileo SBF."""
        from connectors.galileo_osnma import (
            GalileoOsnmaConnector,
            build_tampered_galileo_evidence,
        )

        original_items = GalileoOsnmaConnector(
            retrieved_at="2026-11-27T16:58:00Z"
        ).load_evidence()
        tampered_ev, tamper_details = build_tampered_galileo_evidence()

        svid = int(tamper_details["svid"])
        demo_claim = ClaimRequest.model_validate(
            {
                "claim_id": f"galileo-tamper-comparison-e{svid:02d}",
                "claim_type": "gnss_nav_message_authenticated",
                "geometry": None,
                "claimed_at": "2023-08-27T20:10:00Z",
                "source_label": (
                    f"Controlled offline tamper test comparing original vs 1-bit modified Galileo E{svid:02d} I/NAV"
                ),
                "synthetic": True,
                "attributes": {"svid": svid},
            }
        )

        orig_assessment = engine.assess(demo_claim, original_items)
        tampered_assessment = engine.assess(demo_claim, [tampered_ev])
        orig_graph = build_evidence_graph(demo_claim, original_items, orig_assessment)
        tampered_graph = build_evidence_graph(demo_claim, [tampered_ev], tampered_assessment)

        response.headers["X-EIP-Assessed-At"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        return {
            "tamper_details": tamper_details,
            "disclaimer": (
                "Controlled offline demonstration: the modified copy is explicitly synthetic/tampered "
                "test evidence (1 bit flipped in memory in Word Type 1 ephemeris with recomputed SBF CRC). "
                "The preserved original recording is untouched."
            ),
            "original": AssessmentGraphResponse(
                assessment=orig_assessment,
                evidence=original_items,
                graph=orig_graph,
            ).model_dump(mode="json"),
            "tampered": AssessmentGraphResponse(
                assessment=tampered_assessment,
                evidence=[tampered_ev],
                graph=tampered_graph,
            ).model_dump(mode="json"),
        }

    @application.get("/v1/context/lough-funshinagh", tags=["context"])
    def get_lough_funshinagh_context() -> dict[str, Any]:
        """Serve display-only local geographical context derived from licensed EMSR718 archive."""
        if not DEFAULT_CONTEXT_PATH.exists():
            return {"display_only": True, "baseline_water_extent": None, "landmarks": None}
        return json.loads(DEFAULT_CONTEXT_PATH.read_text(encoding="utf-8"))

    return application


app = create_app()
