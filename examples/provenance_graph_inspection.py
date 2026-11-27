"""Evidence provenance and API-derived graph inspection example using EIPClient."""

from __future__ import annotations

import argparse
import json
import os

from eip_sdk import ClaimInput, EIPClient


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect API-derived provenance and evidence graph via EIPClient."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("EIP_API_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--export",
        default=None,
        help="Optional path to export a full machine-readable JSON audit report.",
    )
    args = parser.parse_args()

    client = EIPClient(args.base_url, timeout=5.0)
    claim = ClaimInput.road_passable(
        claim_id="graph-demo-ballagh-east",
        coordinates=[[-8.1165, 53.4916], [-8.1075, 53.4916]],
        claimed_at="2024-04-15T08:00:00Z",
        source_label="Synthetic claim for provenance graph inspection",
        synthetic=True,
    )

    graph_res = client.assess_with_graph(claim)
    if args.export:
        client.export_report(claim, args.export, include_graph=True)

    summary = {
        "example": "provenance_graph_inspection",
        "claim_id": graph_res.assessment.claim_id,
        "status": graph_res.assessment.status,
        "independence_status": graph_res.graph.independence_status,
        "independent_group_count": graph_res.graph.independent_group_count,
        "node_count": len(graph_res.graph.nodes),
        "edge_count": len(graph_res.graph.edges),
        "shared_dependency_edges": [e.to_dict() for e in graph_res.graph.shared_edges()],
        "evidence_nodes": [
            {
                "id": n.id,
                "label": n.label,
                "relation_role": n.relation_role,
                "independence_group": n.independence_group,
                "authentication": n.authentication,
                "freshness": n.freshness,
                "observed_at": n.observed_at,
                "available_at": n.available_at,
            }
            for n in graph_res.graph.evidence_nodes()
        ],
        "upstream_nodes": [
            {"id": n.id, "node_type": n.node_type, "label": n.label}
            for n in graph_res.graph.upstream_nodes()
        ],
        "exported_report_path": args.export,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
