"""Command-line client for automated EIP enterprise workflows.

Usage:
    python -m eip_sdk --base-url http://127.0.0.1:8000 health
    python -m eip_sdk capabilities
    python -m eip_sdk policies
    python -m eip_sdk evidence --kind flood_extent
    python -m eip_sdk assess --claim-file claim.json --graph --report-out report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from eip_sdk.client import DEFAULT_BASE_URL, DEFAULT_TIMEOUT_SECONDS, EIPClient
from eip_sdk.errors import (
    EIPAPIError,
    EIPConnectionError,
    EIPError,
    EIPUnknownPolicyError,
    EIPUnsupportedClaimError,
    EIPValidationError,
)


def _dump_json(data: Any, *, compact: bool) -> str:
    if compact:
        return json.dumps(data, separators=(",", ":"))
    return json.dumps(data, indent=2)


def _print_error(error_type: str, message: str, extra: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"error": error_type, "message": message}
    if extra:
        payload.update(extra)
    sys.stderr.write(json.dumps(payload, indent=2) + "\n")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--base-url",
        default=argparse.SUPPRESS,
        help=f"EIP API base URL (default: $EIP_API_URL or {DEFAULT_BASE_URL})",
    )
    common.add_argument(
        "--timeout",
        type=float,
        default=argparse.SUPPRESS,
        help=f"HTTP request timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    common.add_argument(
        "--compact",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Emit single-line compact JSON suitable for log pipelines.",
    )

    parser = argparse.ArgumentParser(
        prog="eip-cli",
        parents=[common],
        description="Command-line client for the Evidence Integrity Platform (EIP) REST API.",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", parents=[common], help="Check API health and contract compatibility.")
    sub.add_parser(
        "capabilities",
        parents=[common],
        help="List supported claim types, evidence kinds, and policies.",
    )
    sub.add_parser(
        "policies",
        parents=[common],
        help="Inspect registered assessment policy specifications.",
    )

    ev_cmd = sub.add_parser(
        "evidence",
        parents=[common],
        help="List available evidence records and provenance.",
    )
    ev_cmd.add_argument("--kind", default=None, help="Filter evidence items by kind.")
    ev_cmd.add_argument(
        "--summary",
        action="store_true",
        help="Omit bulky geometry coordinates and output compact provenance summaries.",
    )

    assess_cmd = sub.add_parser(
        "assess",
        parents=[common],
        help="Submit a structured JSON claim for assessment.",
    )
    assess_cmd.add_argument(
        "--claim-file",
        required=True,
        help="Path to a JSON claim file (or '-' to read JSON from stdin).",
    )
    assess_cmd.add_argument(
        "--mode",
        choices=["retrospective", "decision_time"],
        default=None,
        help="Override assessment_mode on the claim payload.",
    )
    assess_cmd.add_argument(
        "--decision-time",
        default=None,
        help="UTC ISO 8601 decision_time (required if --mode decision_time and omitted in file).",
    )
    assess_cmd.add_argument(
        "--graph",
        action="store_true",
        help="Retrieve the full API-derived provenance/evidence graph via /v1/assess/graph.",
    )
    assess_cmd.add_argument(
        "--report-out",
        default=None,
        help="Write a full auditable machine-readable JSON report to this file path.",
    )

    return parser


def _load_claim_json(claim_file: str) -> dict[str, Any]:
    if claim_file == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(claim_file).read_text(encoding="utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Claim JSON must be an object.")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    base_url = getattr(args, "base_url", os.environ.get("EIP_API_URL", DEFAULT_BASE_URL))
    timeout = getattr(args, "timeout", DEFAULT_TIMEOUT_SECONDS)
    compact = bool(getattr(args, "compact", False))

    client = EIPClient(base_url=base_url, timeout=timeout)

    try:
        if args.command == "health":
            health = client.health()
            caps = client.check_compatibility()
            out = {"health": health.to_dict(), "capabilities": caps.to_dict()}
        elif args.command == "capabilities":
            out = client.capabilities().to_dict()
        elif args.command == "policies":
            out = {"policies": [p.to_dict() for p in client.list_policies()]}
        elif args.command == "evidence":
            records = client.list_evidence(kind=args.kind)
            out = {
                "count": len(records),
                "items": [
                    r.provenance_summary() if args.summary else r.to_dict()
                    for r in records
                ],
            }
        elif args.command == "assess":
            claim_payload = _load_claim_json(args.claim_file)
            if args.mode is not None:
                claim_payload["assessment_mode"] = args.mode
            if args.decision_time is not None:
                claim_payload["decision_time"] = args.decision_time

            if args.report_out:
                report = client.export_report(
                    claim_payload,
                    args.report_out,
                    include_graph=args.graph,
                )
                out = report.to_dict()
            elif args.graph:
                graph_res = client.assess_with_graph(claim_payload)
                out = graph_res.to_dict()
            else:
                result = client.assess(claim_payload)
                out = result.to_dict()
        else:  # pragma: no cover
            parser.error(f"Unknown command: {args.command}")
            return 1

        sys.stdout.write(_dump_json(out, compact=compact) + "\n")
        return 0

    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _print_error("input_error", str(exc))
        return 1
    except EIPConnectionError as exc:
        _print_error("connection_error", str(exc), {"base_url": base_url})
        return 2
    except EIPUnsupportedClaimError as exc:
        _print_error(
            "unsupported_claim_type",
            str(exc),
            {
                "status_code": exc.status_code,
                "claim_type": exc.claim_type,
                "supported_claim_types": exc.supported_claim_types,
            },
        )
        return 3
    except EIPUnknownPolicyError as exc:
        _print_error(
            "unknown_policy",
            str(exc),
            {
                "status_code": exc.status_code,
                "policy_id": exc.policy_id,
                "registered_policy_ids": exc.registered_policy_ids,
            },
        )
        return 3
    except EIPValidationError as exc:
        _print_error(
            "validation_error",
            str(exc),
            {"status_code": exc.status_code, "field": exc.field, "detail": exc.detail},
        )
        return 3
    except EIPAPIError as exc:
        _print_error(
            "api_error",
            str(exc),
            {"status_code": exc.status_code, "detail": exc.detail},
        )
        return 4
    except EIPError as exc:
        _print_error("eip_error", str(exc))
        return 4


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
