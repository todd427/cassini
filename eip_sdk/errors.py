"""Structured error classes for the EIP Python client SDK."""

from __future__ import annotations

from typing import Any


class EIPError(Exception):
    """Base exception for all EIP client SDK errors."""


class EIPConnectionError(EIPError):
    """Raised when the EIP REST API cannot be reached.

    The SDK never silently substitutes mock or synthetic results on failure.
    """

    def __init__(self, message: str, *, base_url: str | None = None) -> None:
        super().__init__(message)
        self.base_url = base_url


class EIPTimeoutError(EIPConnectionError):
    """Raised when a request to the EIP REST API exceeds the configured timeout."""


class EIPCompatibilityError(EIPError):
    """Raised when the remote API contract version is incompatible with the SDK."""

    def __init__(
        self,
        message: str,
        *,
        server_contract: str | None = None,
        supported_contracts: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.server_contract = server_contract
        self.supported_contracts = supported_contracts


class EIPAPIError(EIPError):
    """Raised when the EIP API returns a non-2xx HTTP response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        error_code: str | None = None,
        detail: Any = None,
        raw_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail
        self.raw_body = raw_body


class EIPUnsupportedClaimError(EIPAPIError):
    """Raised when a claim_type is not supported by any registered policy."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 422,
        claim_type: str | None = None,
        supported_claim_types: list[str] | None = None,
        detail: Any = None,
        raw_body: str | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            error_code="unsupported_claim_type",
            detail=detail,
            raw_body=raw_body,
        )
        self.claim_type = claim_type
        self.supported_claim_types = list(supported_claim_types or [])


class EIPUnknownPolicyError(EIPAPIError):
    """Raised when an explicit policy_id is not registered on the server."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 422,
        policy_id: str | None = None,
        registered_policy_ids: list[str] | None = None,
        detail: Any = None,
        raw_body: str | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            error_code="unknown_policy",
            detail=detail,
            raw_body=raw_body,
        )
        self.policy_id = policy_id
        self.registered_policy_ids = list(registered_policy_ids or [])


class EIPValidationError(EIPAPIError):
    """Raised when a claim or request payload fails API or policy validation (HTTP 422)."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 422,
        field: str | None = None,
        errors: list[dict[str, Any]] | None = None,
        detail: Any = None,
        raw_body: str | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            error_code="validation_error",
            detail=detail,
            raw_body=raw_body,
        )
        self.field = field
        self.errors = list(errors or [])
