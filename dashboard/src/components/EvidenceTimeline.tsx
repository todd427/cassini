import { useMemo } from "react";
import type { AssessmentResponse, Evidence } from "../types/contract";

interface EvidenceTimelineProps {
  claimedAt: string;
  assessmentMode: "retrospective" | "decision_time";
  decisionTime: string;
  assessedAt: string | null;
  evidenceItems: Evidence[];
  assessment: AssessmentResponse | null;
  policyWindowHours: number;
  policyWindowNote: string;
  onModeChange: (mode: "retrospective" | "decision_time") => void;
  onDecisionTimeChange: (value: string) => void;
}

interface TimelineMarker {
  id: string;
  label: string;
  timeMs: number;
  iso: string;
  kind: "claim" | "decision" | "observed" | "available" | "retrieved" | "assessed";
}

function safeParseMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? null : ms;
}

export function EvidenceTimeline({
  claimedAt,
  assessmentMode,
  decisionTime,
  assessedAt,
  evidenceItems,
  assessment,
  policyWindowHours,
  policyWindowNote,
  onModeChange,
  onDecisionTimeChange,
}: EvidenceTimelineProps) {
  const claimMs = safeParseMs(claimedAt);
  const decisionMs = assessmentMode === "decision_time" ? safeParseMs(decisionTime) : null;
  const windowMs = policyWindowHours * 3600 * 1000;

  // Build focused temporal range centered on claim time + observed/available/decision times
  const { minMs, maxMs, markers } = useMemo(() => {
    const pts: TimelineMarker[] = [];
    const rangeTimes: number[] = [];

    if (claimMs !== null) {
      pts.push({
        id: "claim",
        label: "Claim time",
        timeMs: claimMs,
        iso: claimedAt,
        kind: "claim",
      });
      rangeTimes.push(claimMs - windowMs * 1.1, claimMs + windowMs * 1.1);
    }

    if (decisionMs !== null) {
      pts.push({
        id: "decision",
        label: "Decision time",
        timeMs: decisionMs,
        iso: decisionTime,
        kind: "decision",
      });
      rangeTimes.push(decisionMs);
    }

    for (const ev of evidenceItems) {
      const obsMs = safeParseMs(ev.observed_at);
      if (obsMs !== null) {
        pts.push({
          id: `obs:${ev.id}`,
          label: `${ev.product_id ?? ev.id} (observed)`,
          timeMs: obsMs,
          iso: ev.observed_at!,
          kind: "observed",
        });
        // Keep range readable if observation is within 10 days of claim
        if (claimMs === null || Math.abs(obsMs - claimMs) <= 10 * 86400 * 1000) {
          rangeTimes.push(obsMs);
        }
      }
      const availMs = safeParseMs(ev.available_at);
      if (availMs !== null) {
        pts.push({
          id: `avail:${ev.id}`,
          label: `${ev.product_id ?? ev.id} (available)`,
          timeMs: availMs,
          iso: ev.available_at!,
          kind: "available",
        });
        if (claimMs === null || Math.abs(availMs - claimMs) <= 10 * 86400 * 1000) {
          rangeTimes.push(availMs);
        }
      }
    }

    if (rangeTimes.length === 0) {
      const now = Date.now();
      return { minMs: now - windowMs, maxMs: now + windowMs, markers: pts };
    }
    const lo = Math.min(...rangeTimes);
    const hi = Math.max(...rangeTimes);
    const pad = Math.max((hi - lo) * 0.08, 1800 * 1000);
    return { minMs: lo - pad, maxMs: hi + pad, markers: pts };
  }, [claimMs, claimedAt, decisionMs, decisionTime, evidenceItems, windowMs]);

  const toPct = (ms: number): number => {
    if (maxMs <= minMs) return 50;
    const raw = ((ms - minMs) / (maxMs - minMs)) * 100;
    return Math.max(1, Math.min(99, raw));
  };

  const windowLeftPct = claimMs !== null ? toPct(claimMs - windowMs) : 0;
  const windowRightPct = claimMs !== null ? toPct(claimMs + windowMs) : 0;
  const decisionPct = decisionMs !== null ? toPct(decisionMs) : null;

  const unknownAvailCount = evidenceItems.filter((e) => !e.available_at).length;

  return (
    <section className="timeline-panel" aria-label="Temporal evidence visualisation" data-testid="evidence-timeline">
      <div className="timeline-top">
        <div>
          <strong>Temporal Integrity &amp; Evidence Timeline</strong>
          <span className="muted-note"> — {policyWindowNote}</span>
        </div>

        <div className="temporal-controls" role="group" aria-label="Assessment temporal mode">
          <button
            type="button"
            className={`mode-btn ${assessmentMode === "retrospective" ? "mode-btn-active" : ""}`}
            onClick={() => onModeChange("retrospective")}
            data-testid="mode-retrospective"
          >
            Retrospective Replay
          </button>
          <button
            type="button"
            className={`mode-btn ${assessmentMode === "decision_time" ? "mode-btn-active" : ""}`}
            onClick={() => onModeChange("decision_time")}
            data-testid="mode-decision-time"
          >
            Decision-Time Audit
          </button>
        </div>
      </div>

      {assessmentMode === "decision_time" && (
        <div className="decision-time-bar" data-testid="decision-time-controls">
          <label htmlFor="decision-time-input">Decision Time (UTC ISO 8601):</label>
          <input
            id="decision-time-input"
            type="text"
            value={decisionTime}
            onChange={(e) => onDecisionTimeChange(e.target.value)}
            placeholder="2024-04-15T08:00:00Z"
          />
          <button
            type="button"
            className="btn-ghost"
            onClick={() => onDecisionTimeChange(claimedAt)}
          >
            Set to Claim Time
          </button>
          <span className="muted-note">
            Evidence acquired or published after <code>decision_time</code> — or with unknown{" "}
            <code>available_at</code> — is excluded from decision-time findings.
          </span>
        </div>
      )}

      {/* Visual timeline axis */}
      <div className="timeline-track-wrapper">
        <div className="timeline-track">
          {/* Policy relevance window */}
          {claimMs !== null && (
            <div
              className="timeline-window"
              style={{
                left: `${windowLeftPct}%`,
                width: `${Math.max(2, windowRightPct - windowLeftPct)}%`,
              }}
              title={`Policy relevance window (±${policyWindowHours}h around claimed_at)`}
            />
          )}

          {/* Future / Post-decision exclusion shading in decision_time mode */}
          {decisionPct !== null && (
            <div
              className="timeline-future-zone"
              style={{
                left: `${decisionPct}%`,
                width: `${100 - decisionPct}%`,
              }}
              title="Post-decision zone: evidence acquired or published here cannot be treated as available at decision_time"
            />
          )}

          {/* Plot markers */}
          {markers.map((m) => (
            <div
              key={m.id}
              className={`timeline-dot dot-${m.kind}`}
              style={{ left: `${toPct(m.timeMs)}%` }}
              title={`${m.label}: ${m.iso}`}
            />
          ))}
        </div>

        <div className="timeline-axis-labels">
          <span>{new Date(minMs).toISOString().replace(".000Z", "Z")}</span>
          <span>
            Policy window: ±{policyWindowHours} h (demo policy, not validated safety threshold)
          </span>
          <span>{new Date(maxMs).toISOString().replace(".000Z", "Z")}</span>
        </div>
      </div>

      {/* Explicit 6-timestamp breakdown table */}
      <div className="timeline-table">
        <div className="timeline-meta-chips">
          <span className="mini-badge">Claim: {claimedAt}</span>
          <span className="mini-badge">
            Decision: {assessmentMode === "decision_time" ? decisionTime || "Required" : "N/A (retrospective)"}
          </span>
          <span className="mini-badge">
            Assessed: {assessedAt ?? assessment?.traceability?.assessed_at ?? "Pending run"}
          </span>
          {unknownAvailCount > 0 && (
            <span className="mini-badge mini-synth">
              {unknownAvailCount} source(s) with unknown availability time (available_at = null)
            </span>
          )}
        </div>

        <div className="timeline-rows">
          {evidenceItems.map((ev) => {
            const isExcludedFuture =
              assessment?.temporal_context?.excluded_not_available_ids?.includes(ev.id) ?? false;
            const isUnknownAvail =
              assessment?.temporal_context?.unknown_availability_ids?.includes(ev.id) ?? false;
            return (
              <div key={ev.id} className="timeline-row">
                <strong className="tl-name">{ev.product_id ?? ev.id}</strong>
                <span>
                  Observed: <code>{ev.observed_at ?? "Unknown (null)"}</code>
                </span>
                <span>
                  Available:{" "}
                  <code className={ev.available_at ? "" : "text-warn"}>
                    {ev.available_at ?? "Unknown (null)"}
                  </code>
                </span>
                <span>
                  Retrieved: <code>{ev.retrieved_at ?? "Unknown"}</code>
                </span>
                {isExcludedFuture && (
                  <span className="mini-badge mini-danger">Excluded (post-decision)</span>
                )}
                {isUnknownAvail && (
                  <span className="mini-badge mini-synth">Excluded (availability unknown)</span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
