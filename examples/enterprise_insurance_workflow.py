"""Independent External Enterprise CLI Demo: Hypothetical Infrastructure & Flood Claims Triage.

IMPORTANT DISCLOSURES:
- HYPOTHETICAL COMMERCIAL WORKFLOW for architectural demonstration only.
- Uses SYNTHETIC CLAIMS evaluated against archived historical Lough Funshinagh (Apr 2024) data.
- Consumes EIP EXCLUSIVELY through the public `eip_sdk` REST client (zero internal imports).
- NEVER automates a consequential final decision (such as approving or rejecting an
  insurance claim or dispatching emergency vehicles) based solely on EIP's assessment.
  All outputs are structured human decision-support dossiers requiring qualified review.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eip_sdk import (
    ClaimInput,
    EIPClient,
    EIPConnectionError,
    EIPError,
    NON_ORACLE_DISCLAIMER,
)

# Illustrative synthetic intake cases mapped to County Roscommon (Apr 2024 historical replay)
SYNTHETIC_CASES: dict[str, dict[str, Any]] = {
    "CASE-RF-2024-001": {
        "policyholder_ref": "SYNTHETIC-INFRA-001",
        "incident_summary": (
            "Synthetic claim asserting Ballagh East local access road remained passable "
            "at 08:00 UTC on 15 April 2024 for commercial fleet delivery."
        ),
        "coordinates": [[-8.1165, 53.4916], [-8.1113, 53.4916], [-8.1075, 53.4916]],
        "claimed_at": "2024-04-15T08:00:00Z",
    },
    "CASE-RF-2024-002": {
        "policyholder_ref": "SYNTHETIC-INFRA-002",
        "incident_summary": (
            "Synthetic claim asserting Rahara South road corridor was clear at 08:00 UTC "
            "on 15 April 2024."
        ),
        "coordinates": [[-8.175, 53.462], [-8.155, 53.462]],
        "claimed_at": "2024-04-15T08:00:00Z",
    },
}


def derive_human_review_guidance(
    status: str,
    *,
    unknown_avail_count: int,
    unverified_auth_count: int,
    independent_groups: int | None,
) -> dict[str, Any]:
    """Translate EIP output into human decision-support triage guidance (never auto-decision)."""
    if status == "potential_conflict":
        action = "escalate_for_human_claims_adjuster_review"
        rationale = (
            "Direct satellite flood extent intersects the claimed road segment within the "
            "24-hour demonstration policy window. This flags a potential conflict for human "
            "verification, NOT proof of road impassability or grounds for automated rejection."
        )
    elif status == "no_mapped_overlap":
        action = "collect_corroborating_ground_documentation"
        rationale = (
            "No mapped flood overlap was found within documented satellite coverage. "
            "Absence of mapped flooding does NOT establish passability or absence of loss; "
            "human adjuster must review local ground evidence."
        )
    else:
        action = "hold_for_manual_evidence_gathering"
        rationale = (
            "Available evidence is insufficient under policy criteria. No inference can be "
            "drawn regarding passability or claim validity."
        )

    caution_flags: list[str] = []
    if unverified_auth_count > 0:
        caution_flags.append(
            f"{unverified_auth_count} source(s) lack cryptographic origin authentication."
        )
    if unknown_avail_count > 0:
        caution_flags.append(
            f"{unknown_avail_count} source(s) have unknown publication time (available_at=null), "
            "so decision-time availability cannot be proven."
        )
    if independent_groups is not None:
        caution_flags.append(
            f"Declared provenance indicates {independent_groups} independent source group(s); "
            "undeclared operational correlations cannot be ruled out."
        )

    return {
        "automated_final_decision": False,
        "recommended_human_action": action,
        "rationale": rationale,
        "caution_flags": caution_flags,
        "human_signoff_required": True,
    }


def run_workflow(
    *,
    base_url: str,
    case_id: str,
    audit_mode: str,
    decision_time: str | None,
    timeout: float,
) -> dict[str, Any]:
    if case_id not in SYNTHETIC_CASES:
        raise ValueError(
            f"Unknown case_id {case_id!r}. Choose from: {', '.join(sorted(SYNTHETIC_CASES))}"
        )
    case = SYNTHETIC_CASES[case_id]

    client = EIPClient(base_url, timeout=timeout)
    caps = client.check_compatibility()
    if "road_passable" not in caps.supported_claim_types:
        raise RuntimeError(
            f"Remote EIP server does not support 'road_passable' (available: {caps.supported_claim_types})."
        )

    claim = ClaimInput.road_passable(
        claim_id=f"intake-{case_id.lower()}",
        coordinates=case["coordinates"],
        claimed_at=case["claimed_at"],
        source_label=f"HYPOTHETICAL CLAIMS TRIAGE ({case['policyholder_ref']})",
        synthetic=True,
        assessment_mode="decision_time" if audit_mode == "decision_time" else "retrospective",
        decision_time=(decision_time or case["claimed_at"]) if audit_mode == "decision_time" else None,
    )

    graph_res = client.assess_with_graph(claim)
    assessment = graph_res.assessment

    unverified_auth = sum(1 for ev in graph_res.evidence if ev.authentication != "verified")
    unknown_avail = sum(1 for ev in graph_res.evidence if ev.available_at is None)
    ind_groups = (
        assessment.independence.independent_group_count
        if assessment.independence
        else None
    )

    triage = derive_human_review_guidance(
        assessment.status,
        unknown_avail_count=unknown_avail,
        unverified_auth_count=unverified_auth,
        independent_groups=ind_groups,
    )

    return {
        "workflow_type": "infrastructure_flood_claims_triage_demo",
        "hypothetical_workflow": True,
        "synthetic_claim": True,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "api_base_url": base_url,
        "case": {
            "case_id": case_id,
            "policyholder_ref": case["policyholder_ref"],
            "incident_summary": case["incident_summary"],
            "claimed_at": case["claimed_at"],
            "audit_mode": audit_mode,
        },
        "eip_assessment": {
            "claim_id": assessment.claim_id,
            "status": assessment.status,
            "policy_version": assessment.policy_version,
            "reasons": assessment.reasons,
            "assessed_at_header": assessment.assessed_at_header,
            "input_fingerprint": (
                assessment.traceability.input_fingerprint
                if assessment.traceability
                else None
            ),
            "independence": (
                assessment.independence.to_dict() if assessment.independence else None
            ),
            "findings": [f.to_dict() for f in assessment.findings],
            "limitations": assessment.limitations,
        },
        "evidence_provenance_summary": [ev.provenance_summary() for ev in graph_res.evidence],
        "graph_overview": {
            "node_count": len(graph_res.graph.nodes),
            "edge_count": len(graph_res.graph.edges),
            "independence_status": graph_res.graph.independence_status,
            "independent_group_count": graph_res.graph.independent_group_count,
            "shared_edges": [e.to_dict() for e in graph_res.graph.shared_edges()],
        },
        "decision_support_guidance": triage,
        "governance_notice": (
            "HYPOTHETICAL ENTERPRISE DEMONSTRATION ONLY: Do not automate claim approval, "
            "rejection, pricing, or operational safety decisions solely from EIP outputs. "
            + NON_ORACLE_DISCLAIMER
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Hypothetical enterprise claims-triage CLI consuming EIP exclusively via eip_sdk."
        )
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("EIP_API_URL", "http://127.0.0.1:8000"),
        help="EIP REST API base URL.",
    )
    parser.add_argument(
        "--case-id",
        default="CASE-RF-2024-001",
        choices=sorted(SYNTHETIC_CASES),
        help="Illustrative synthetic intake case ID.",
    )
    parser.add_argument(
        "--mode",
        choices=["retrospective", "decision_time"],
        default="retrospective",
        help="Temporal assessment mode.",
    )
    parser.add_argument(
        "--decision-time",
        default=None,
        help="Optional UTC ISO 8601 decision_time (defaults to claimed_at in decision_time mode).",
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output path to save the auditable JSON decision-support dossier.",
    )
    args = parser.parse_args(argv)

    try:
        dossier = run_workflow(
            base_url=args.base_url,
            case_id=args.case_id,
            audit_mode=args.mode,
            decision_time=args.decision_time,
            timeout=args.timeout,
        )
    except EIPConnectionError as exc:
        sys.stderr.write(
            json.dumps({"error": "eip_unavailable", "message": str(exc)}, indent=2) + "\n"
        )
        return 2
    except (EIPError, ValueError, RuntimeError) as exc:
        sys.stderr.write(
            json.dumps({"error": "workflow_error", "message": str(exc)}, indent=2) + "\n"
        )
        return 1

    rendered = json.dumps(dossier, indent=2)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.write(rendered + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
