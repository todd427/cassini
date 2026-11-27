import { useMemo, useState } from "react";
import {
  INDEPENDENCE_LABELS,
  REASON_EXPLANATIONS,
  type EvidenceGraph,
  type GraphEdge,
  type GraphNode,
  type IndependenceSummary,
} from "../types/contract";

interface EvidenceGraphViewProps {
  graph: EvidenceGraph | null;
}

const ROLE_LABELS: Record<string, string> = {
  potentially_contradicting: "Potential conflict",
  supporting: "Consistent / Verified",
  contextual: "Contextual (indirect)",
  failed_authentication: "Auth failed",
  unsuitable: "Unsuitable for claim",
  inconclusive: "Inconclusive",
};

const FRESHNESS_LABELS: Record<string, string> = {
  fresh: "Fresh",
  stale: "Stale",
  time_unknown: "Time unknown",
  not_available_at_decision: "Unavailable at decision",
  availability_unknown: "Availability unknown",
};

export function EvidenceGraphView({ graph }: EvidenceGraphViewProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const { upstreamNodes, evidenceGroups, claimNode, missingNode, edgeBySource } = useMemo(() => {
    if (!graph) {
      return {
        upstreamNodes: [] as GraphNode[],
        evidenceGroups: [] as Array<{ group: number | null; nodes: GraphNode[] }>,
        claimNode: null as GraphNode | null,
        missingNode: null as GraphNode | null,
        edgeBySource: new Map<string, GraphEdge[]>(),
      };
    }

    const upstream = graph.nodes.filter(
      (n) =>
        n.node_type === "original_source" ||
        n.node_type === "publisher" ||
        n.node_type === "upstream_dependency",
    );
    const evNodes = graph.nodes.filter((n) => n.node_type === "evidence");
    const claim = graph.nodes.find((n) => n.node_type === "claim") ?? null;
    const missing = graph.nodes.find((n) => n.node_type === "missing_evidence") ?? null;

    const groupMap = new Map<number | null, GraphNode[]>();
    for (const ev of evNodes) {
      const k = ev.independence_group ?? null;
      const list = groupMap.get(k) ?? [];
      list.push(ev);
      groupMap.set(k, list);
    }
    const groups = Array.from(groupMap.entries())
      .sort((a, b) => (a[0] ?? 999) - (b[0] ?? 999))
      .map(([group, nodes]) => ({ group, nodes }));

    const eMap = new Map<string, GraphEdge[]>();
    for (const edge of graph.edges) {
      const list = eMap.get(edge.source) ?? [];
      list.push(edge);
      eMap.set(edge.source, list);
    }

    return {
      upstreamNodes: upstream,
      evidenceGroups: groups,
      claimNode: claim,
      missingNode: missing,
      edgeBySource: eMap,
    };
  }, [graph]);

  const selectedNode = useMemo(() => {
    if (!graph) return null;
    if (selectedNodeId) {
      const found = graph.nodes.find((n) => n.id === selectedNodeId);
      if (found) return found;
    }
    return graph.nodes.find((n) => n.node_type === "evidence") ?? graph.nodes[0] ?? null;
  }, [graph, selectedNodeId]);

  const connectedEdges = useMemo(() => {
    if (!graph || !selectedNode) return [];
    return graph.edges.filter(
      (e) => e.source === selectedNode.id || e.target === selectedNode.id,
    );
  }, [graph, selectedNode]);

  if (!graph) {
    return (
      <div className="empty-state" data-testid="evidence-graph-empty">
        Run an assessment to generate the backend-derived evidence &amp; provenance graph.
      </div>
    );
  }

  const indLabel =
    INDEPENDENCE_LABELS[graph.independence_status as IndependenceSummary["status"]] ??
    graph.independence_status;

  return (
    <div className="graph-container" data-testid="evidence-graph">
      <div className="graph-header-bar">
        <div>
          <strong>Provenance &amp; Evidence Graph</strong>
          <span className="muted-note">
            {" "}
            — Derived strictly from API provenance, independence, and assessment findings
          </span>
        </div>
        <span className="mini-badge">
          {indLabel} ·{" "}
          {graph.independent_group_count !== null
            ? `${graph.independent_group_count} independent group(s)`
            : "Unknown independence"}
        </span>
      </div>

      <div className="graph-columns">
        {/* Column 1: Provenance, Original Sources, Publishers, Shared Dependencies */}
        <div className="graph-col">
          <div className="graph-col-title">1. Sources, Publishers &amp; Upstream</div>
          {upstreamNodes.length === 0 ? (
            <div className="graph-empty-col">No declared upstream provenance metadata</div>
          ) : (
            upstreamNodes.map((node) => {
              const isSelected = selectedNode?.id === node.id;
              const isShared = node.status === "shared";
              return (
                <button
                  key={node.id}
                  type="button"
                  className={`graph-node node-${node.node_type} ${isShared ? "node-shared" : ""} ${
                    isSelected ? "node-selected" : ""
                  }`}
                  onClick={() => setSelectedNodeId(node.id)}
                  data-testid={`graph-node-${node.node_type}`}
                >
                  <div className="node-top">
                    <span className="node-kind">{node.node_type.replace("_", " ")}</span>
                    {isShared && <span className="mini-badge mini-synth">Shared</span>}
                  </div>
                  <div className="node-label">{node.label}</div>
                  {node.subtitle && <div className="node-sub">{node.subtitle}</div>}
                </button>
              );
            })
          )}
        </div>

        {/* Column 2: Evidence Records Grouped by Independence Group */}
        <div className="graph-col">
          <div className="graph-col-title">2. Assessed Evidence (by Independence Group)</div>
          {missingNode ? (
            <button
              type="button"
              className={`graph-node node-missing ${
                selectedNode?.id === missingNode.id ? "node-selected" : ""
              }`}
              onClick={() => setSelectedNodeId(missingNode.id)}
              data-testid="graph-node-missing"
            >
              <div className="node-top">
                <span className="node-kind">Missing evidence</span>
                <span className="mini-badge">NO_EVIDENCE</span>
              </div>
              <div className="node-label">{missingNode.label}</div>
            </button>
          ) : (
            evidenceGroups.map(({ group, nodes }) => {
              const isCorrelatedGroup = nodes.length > 1;
              return (
                <div
                  key={String(group)}
                  className={`graph-group-box ${isCorrelatedGroup ? "graph-group-correlated" : ""}`}
                >
                  <div className="graph-group-label">
                    {group !== null ? `Independence Group ${group}` : "Ungrouped"}
                    {isCorrelatedGroup ? " · Correlated / Shared Upstream" : ""}
                  </div>
                  {nodes.map((node) => {
                    const isSelected = selectedNode?.id === node.id;
                    const outEdges = edgeBySource.get(node.id) ?? [];
                    const claimEdge = outEdges.find((e) => e.target.startsWith("claim:"));
                    return (
                      <button
                        key={node.id}
                        type="button"
                        className={`graph-node node-evidence role-${node.relation_role ?? "inconclusive"} ${
                          isSelected ? "node-selected" : ""
                        }`}
                        onClick={() => setSelectedNodeId(node.id)}
                        data-testid="graph-node-evidence"
                      >
                        <div className="node-top">
                          <span className="node-kind">
                            {ROLE_LABELS[node.relation_role ?? "inconclusive"]}
                          </span>
                          <span className="mini-badge">
                            {FRESHNESS_LABELS[node.freshness ?? "fresh"]}
                          </span>
                        </div>
                        <div className="node-label">{node.label}</div>
                        <div className="node-sub">{node.subtitle}</div>
                        <div className="node-badges">
                          <span className="mini-badge">
                            Auth: {node.authentication ?? "unknown"}
                          </span>
                          <span className={`mini-badge ${node.synthetic ? "mini-synth" : "mini-real"}`}>
                            {node.synthetic ? "Synthetic" : "Genuine"}
                          </span>
                          {claimEdge && (
                            <span className="edge-pill">→ {claimEdge.label}</span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>

        {/* Column 3: Claim & Overall Verdict */}
        <div className="graph-col">
          <div className="graph-col-title">3. Claim &amp; Verdict</div>
          {claimNode && (
            <button
              type="button"
              className={`graph-node node-claim ${
                selectedNode?.id === claimNode.id ? "node-selected" : ""
              }`}
              onClick={() => setSelectedNodeId(claimNode.id)}
              data-testid="graph-node-claim"
            >
              <div className="node-top">
                <span className="node-kind">Claim</span>
                <span className="mini-badge">{claimNode.status}</span>
              </div>
              <div className="node-label">{claimNode.label}</div>
              {claimNode.subtitle && <div className="node-sub">{claimNode.subtitle}</div>}
              <div className="node-badges">
                <span className={`mini-badge ${claimNode.synthetic ? "mini-synth" : "mini-real"}`}>
                  {claimNode.synthetic ? "Synthetic claim" : "Real claim"}
                </span>
                {claimNode.observed_at && (
                  <span className="mini-badge">{claimNode.observed_at}</span>
                )}
              </div>
            </button>
          )}
        </div>
      </div>

      {/* Interactive Selected Node Inspector */}
      {selectedNode && (
        <div className="node-inspector" data-testid="graph-node-inspector">
          <div className="finding-header">
            <strong>Selected Node: {selectedNode.label}</strong>
            <span className="mini-badge">{selectedNode.node_type.replace("_", " ")}</span>
          </div>

          <dl className="meta-grid">
            {selectedNode.status && (
              <div>
                <dt>Status / Contribution</dt>
                <dd>
                  <code>{selectedNode.status}</code>
                  {selectedNode.relation_role
                    ? ` (${ROLE_LABELS[selectedNode.relation_role]})`
                    : ""}
                </dd>
              </div>
            )}
            {selectedNode.authentication && (
              <div>
                <dt>Authentication</dt>
                <dd>{selectedNode.authentication}</dd>
              </div>
            )}
            {selectedNode.freshness && (
              <div>
                <dt>Temporal Freshness</dt>
                <dd>
                  {FRESHNESS_LABELS[selectedNode.freshness]}
                  {selectedNode.age_hours !== null
                    ? ` (${selectedNode.age_hours.toFixed(2)} h offset)`
                    : ""}
                </dd>
              </div>
            )}
            {selectedNode.observed_at && (
              <div>
                <dt>Observed / Claimed (UTC)</dt>
                <dd>{selectedNode.observed_at}</dd>
              </div>
            )}
            {selectedNode.node_type === "evidence" && (
              <div>
                <dt>Available (UTC)</dt>
                <dd>{selectedNode.available_at ?? "Unknown (null)"}</dd>
              </div>
            )}
            {selectedNode.retrieved_at && (
              <div>
                <dt>Retrieved (UTC)</dt>
                <dd>{selectedNode.retrieved_at}</dd>
              </div>
            )}
            {connectedEdges.length > 0 && (
              <div className="span-2">
                <dt>Graph Relationships ({connectedEdges.length})</dt>
                <dd>
                  {connectedEdges.map((e) => (
                    <span key={e.id} className={`edge-pill ${e.shared ? "edge-shared" : ""}`}>
                      {e.relation}: {e.label}
                    </span>
                  ))}
                </dd>
              </div>
            )}
            {selectedNode.reasons.length > 0 && (
              <div className="span-2">
                <dt>Reason Codes</dt>
                <dd>
                  {selectedNode.reasons.map((r) => (
                    <div key={r}>
                      <code>{r}</code> — {REASON_EXPLANATIONS[r] ?? r}
                    </div>
                  ))}
                </dd>
              </div>
            )}
            {selectedNode.limitations.length > 0 && (
              <div className="span-2">
                <dt>Limitations</dt>
                <dd>
                  <ul className="limitations-list">
                    {selectedNode.limitations.map((lim, i) => (
                      <li key={i}>{lim}</li>
                    ))}
                  </ul>
                </dd>
              </div>
            )}
          </dl>
        </div>
      )}
    </div>
  );
}
