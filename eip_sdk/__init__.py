"""Evidence Integrity Platform (EIP) — Reusable Python Client SDK.

Communicates exclusively over the public EIP REST API with zero internal imports
from `core`, `policies`, `connectors`, or `api`.
"""

from eip_sdk.client import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    SDK_VERSION,
    EIPClient,
    RawHTTPResponse,
)
from eip_sdk.errors import (
    EIPAPIError,
    EIPCompatibilityError,
    EIPConnectionError,
    EIPError,
    EIPTimeoutError,
    EIPUnknownPolicyError,
    EIPUnsupportedClaimError,
    EIPValidationError,
)
from eip_sdk.models import (
    NON_ORACLE_DISCLAIMER,
    AssessmentGraphResult,
    AssessmentReport,
    AssessmentResult,
    Capabilities,
    ClaimInput,
    EvidenceGraph,
    EvidenceRecord,
    Finding,
    GraphEdge,
    GraphNode,
    HealthStatus,
    IndependenceReport,
    PolicySummary,
    TemporalContextReport,
    TraceabilityReport,
)

__version__ = SDK_VERSION

__all__ = [
    "AssessmentGraphResult",
    "AssessmentReport",
    "AssessmentResult",
    "Capabilities",
    "ClaimInput",
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT_SECONDS",
    "EIPAPIError",
    "EIPClient",
    "EIPCompatibilityError",
    "EIPConnectionError",
    "EIPError",
    "EIPTimeoutError",
    "EIPUnknownPolicyError",
    "EIPUnsupportedClaimError",
    "EIPValidationError",
    "EvidenceGraph",
    "EvidenceRecord",
    "Finding",
    "GraphEdge",
    "GraphNode",
    "HealthStatus",
    "IndependenceReport",
    "NON_ORACLE_DISCLAIMER",
    "PolicySummary",
    "RawHTTPResponse",
    "SDK_VERSION",
    "TemporalContextReport",
    "TraceabilityReport",
    "__version__",
]
