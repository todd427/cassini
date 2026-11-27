"""Minimal Python client SDK communicating exclusively with the public EIP REST API.

Zero imports from internal `core`, `policies`, `connectors`, or `api` packages.
Never substitutes mock or synthetic results when the API is unavailable.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from eip_sdk.errors import (
    EIPAPIError,
    EIPCompatibilityError,
    EIPConnectionError,
    EIPTimeoutError,
    EIPUnknownPolicyError,
    EIPUnsupportedClaimError,
    EIPValidationError,
)
from eip_sdk.models import (
    AssessmentGraphResult,
    AssessmentReport,
    AssessmentResult,
    Capabilities,
    ClaimInput,
    EvidenceRecord,
    HealthStatus,
    PolicySummary,
)

SDK_VERSION = "0.6.0"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class RawHTTPResponse:
    """Minimal HTTP response envelope returned by transport callables."""

    status_code: int
    body: bytes
    headers: dict[str, str]


TransportCallable = Callable[
    [str, str, bytes | None, dict[str, str], float],
    RawHTTPResponse,
]


def _default_urllib_transport(
    method: str,
    url: str,
    body: bytes | None,
    headers: dict[str, str],
    timeout: float,
) -> RawHTTPResponse:
    req = urllib.request.Request(url=url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return RawHTTPResponse(
                status_code=int(resp.status),
                body=resp.read(),
                headers=resp_headers,
            )
    except urllib.error.HTTPError as exc:
        err_headers = {k.lower(): v for k, v in (exc.headers.items() if exc.headers else [])}
        err_body = exc.read()
        return RawHTTPResponse(
            status_code=int(exc.code),
            body=err_body,
            headers=err_headers,
        )
    except socket.timeout as exc:
        raise EIPTimeoutError(
            f"Request to {url} timed out after {timeout:.1f}s.",
            base_url=url,
        ) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, socket.timeout):
            raise EIPTimeoutError(
                f"Request to {url} timed out after {timeout:.1f}s.",
                base_url=url,
            ) from exc
        raise EIPConnectionError(
            f"Unable to reach EIP API at {url}: {exc.reason}",
            base_url=url,
        ) from exc
    except TimeoutError as exc:
        raise EIPTimeoutError(
            f"Request to {url} timed out after {timeout:.1f}s.",
            base_url=url,
        ) from exc


class EIPClient:
    """Reusable enterprise Python client for the Evidence Integrity Platform REST API."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = f"eip-python-sdk/{SDK_VERSION}",
        transport: TransportCallable | None = None,
    ) -> None:
        if not base_url or not base_url.strip():
            raise ValueError("base_url must be a non-empty HTTP(S) URL.")
        if timeout <= 0:
            raise ValueError("timeout must be strictly positive.")
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.user_agent = user_agent
        self._transport = transport or _default_urllib_transport

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        url = f"{self.base_url}{path}"
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        body: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")

        resp = self._transport(method, url, body, headers, self.timeout)
        raw_text = resp.body.decode("utf-8", errors="replace")

        parsed: Any = None
        if raw_text.strip():
            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError:
                parsed = None

        if 200 <= resp.status_code < 300:
            if not isinstance(parsed, dict):
                raise EIPAPIError(
                    f"Expected JSON object from {method} {path}, received non-object payload.",
                    status_code=resp.status_code,
                    raw_body=raw_text,
                )
            return parsed, resp.headers

        self._raise_api_error(resp.status_code, parsed, raw_text, method, path)
        raise AssertionError("unreachable")  # pragma: no cover

    def _raise_api_error(
        self,
        status_code: int,
        parsed: Any,
        raw_text: str,
        method: str,
        path: str,
    ) -> None:
        detail = parsed.get("detail") if isinstance(parsed, dict) else None

        if status_code == 422 and isinstance(detail, dict):
            err_type = detail.get("error")
            msg = str(detail.get("message") or f"Validation error on {method} {path}")
            if err_type == "unsupported_claim_type":
                raise EIPUnsupportedClaimError(
                    msg,
                    status_code=status_code,
                    claim_type=detail.get("claim_type"),
                    supported_claim_types=detail.get("supported_claim_types") or [],
                    detail=detail,
                    raw_body=raw_text,
                )
            if err_type == "unknown_policy":
                raise EIPUnknownPolicyError(
                    msg,
                    status_code=status_code,
                    policy_id=detail.get("policy_id"),
                    registered_policy_ids=detail.get("registered_policy_ids") or [],
                    detail=detail,
                    raw_body=raw_text,
                )
            if err_type == "claim_validation_error":
                raise EIPValidationError(
                    msg,
                    status_code=status_code,
                    field=detail.get("field"),
                    detail=detail,
                    raw_body=raw_text,
                )

        if status_code == 422 and isinstance(detail, list):
            messages = [
                f"{'.'.join(str(p) for p in item.get('loc', []))}: {item.get('msg', 'invalid')}"
                for item in detail
                if isinstance(item, dict)
            ]
            raise EIPValidationError(
                "Request validation failed: " + "; ".join(messages)
                if messages
                else f"Validation error (HTTP 422) on {method} {path}",
                status_code=status_code,
                errors=[item for item in detail if isinstance(item, dict)],
                detail=detail,
                raw_body=raw_text,
            )

        raise EIPAPIError(
            f"EIP API error (HTTP {status_code}) on {method} {path}: {raw_text[:300]}",
            status_code=status_code,
            detail=detail,
            raw_body=raw_text,
        )

    @staticmethod
    def _coerce_claim_payload(claim: ClaimInput | dict[str, Any]) -> dict[str, Any]:
        if isinstance(claim, ClaimInput):
            return claim.to_payload()
        if isinstance(claim, dict):
            return dict(claim)
        raise TypeError("claim must be a ClaimInput instance or a JSON-serialisable dict.")

    # ------------------------------------------------------------------
    # Health, compatibility, and discovery
    # ------------------------------------------------------------------
    def health(self) -> HealthStatus:
        """Check API availability and base contract version (GET /health)."""
        data, _ = self._request("GET", "/health")
        return HealthStatus.from_dict(data)

    def capabilities(self) -> Capabilities:
        """Discover supported claim types, evidence kinds, and policy IDs (GET /v1/capabilities)."""
        data, _ = self._request("GET", "/v1/capabilities")
        return Capabilities.from_dict(data)

    def check_compatibility(
        self,
        *,
        supported_contracts: tuple[str, ...] = ("0.1", "0.2"),
    ) -> Capabilities:
        """Verify health and contract compatibility, returning server capabilities."""
        health = self.health()
        if health.status != "ok":
            raise EIPCompatibilityError(
                f"EIP API reported unhealthy status: {health.status!r}",
                server_contract=health.contract_version,
                supported_contracts=supported_contracts,
            )
        if health.contract_version not in supported_contracts:
            raise EIPCompatibilityError(
                f"Unsupported /health contract_version {health.contract_version!r}; "
                f"SDK supports {supported_contracts}.",
                server_contract=health.contract_version,
                supported_contracts=supported_contracts,
            )
        caps = self.capabilities()
        if caps.contract_version not in supported_contracts:
            raise EIPCompatibilityError(
                f"Unsupported /v1/capabilities contract_version {caps.contract_version!r}; "
                f"SDK supports {supported_contracts}.",
                server_contract=caps.contract_version,
                supported_contracts=supported_contracts,
            )
        return caps

    def supported_claim_types(self) -> list[str]:
        """Return claim types currently supported by registered server policies."""
        return self.capabilities().supported_claim_types

    def supported_evidence_kinds(self) -> list[str]:
        """Return evidence kinds recognised by registered server policies."""
        return self.capabilities().supported_evidence_kinds

    def list_policies(self) -> list[PolicySummary]:
        """Retrieve declarative specifications for all registered policies (GET /v1/policies)."""
        data, _ = self._request("GET", "/v1/policies")
        return [PolicySummary.from_dict(item) for item in data.get("policies") or []]

    def get_policy(self, policy_id: str) -> PolicySummary | None:
        """Look up a single registered policy by policy_id."""
        for policy in self.list_policies():
            if policy.policy_id == policy_id:
                return policy
        return None

    # ------------------------------------------------------------------
    # Evidence retrieval
    # ------------------------------------------------------------------
    def list_evidence(self, *, kind: str | None = None) -> list[EvidenceRecord]:
        """Retrieve evidence records and provenance metadata (GET /v1/evidence)."""
        data, _ = self._request("GET", "/v1/evidence")
        records = [EvidenceRecord.from_dict(item) for item in data.get("items") or []]
        if kind is not None:
            return [r for r in records if r.kind == kind]
        return records

    # ------------------------------------------------------------------
    # Claim assessment, temporal modes, and evidence graphs
    # ------------------------------------------------------------------
    def assess(self, claim: ClaimInput | dict[str, Any]) -> AssessmentResult:
        """Submit a structured claim for deterministic assessment (POST /v1/assess)."""
        payload = self._coerce_claim_payload(claim)
        data, headers = self._request("POST", "/v1/assess", payload)
        return AssessmentResult.from_dict(
            data,
            assessed_at_header=headers.get("x-eip-assessed-at"),
        )

    def assess_decision_time(
        self,
        claim: ClaimInput | dict[str, Any],
        decision_time: str,
    ) -> AssessmentResult:
        """Evaluate a claim in strict decision_time mode at the given UTC ISO 8601 timestamp."""
        payload = self._coerce_claim_payload(claim)
        payload["assessment_mode"] = "decision_time"
        payload["decision_time"] = decision_time
        return self.assess(payload)

    def assess_with_graph(
        self,
        claim: ClaimInput | dict[str, Any],
    ) -> AssessmentGraphResult:
        """Assess a claim and retrieve its API-derived provenance/evidence graph (POST /v1/assess/graph)."""
        payload = self._coerce_claim_payload(claim)
        data, headers = self._request("POST", "/v1/assess/graph", payload)
        return AssessmentGraphResult.from_dict(
            data,
            assessed_at_header=headers.get("x-eip-assessed-at"),
        )

    # ------------------------------------------------------------------
    # Machine-readable audit reporting
    # ------------------------------------------------------------------
    def build_report(
        self,
        claim: ClaimInput | dict[str, Any],
        *,
        include_graph: bool = True,
    ) -> AssessmentReport:
        """Run an assessment and assemble a machine-readable auditable JSON report."""
        payload = self._coerce_claim_payload(claim)
        if include_graph:
            graph_result = self.assess_with_graph(payload)
            return AssessmentReport.from_graph_result(
                api_base_url=self.base_url,
                claim_payload=payload,
                graph_result=graph_result,
            )
        result = self.assess(payload)
        evidence_records = self.list_evidence() if result.evidence_ids else []
        return AssessmentReport.from_assessment_result(
            api_base_url=self.base_url,
            claim_payload=payload,
            result=result,
            evidence_records=evidence_records,
        )

    def export_report(
        self,
        claim: ClaimInput | dict[str, Any],
        output_path: str | Path,
        *,
        include_graph: bool = True,
    ) -> AssessmentReport:
        """Assess a claim and export the machine-readable report directly to disk."""
        report = self.build_report(claim, include_graph=include_graph)
        report.write_json(output_path)
        return report
