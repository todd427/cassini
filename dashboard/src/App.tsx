import { useCallback, useEffect, useMemo, useState } from "react";
import {
  API_BASE_URL,
  ApiError,
  fetchEvidence,
  fetchHealth,
  submitAssessment,
} from "./api/client";
import { EvidenceMap } from "./components/EvidenceMap";
import {
  CLAIM_PRESETS,
  MOCK_EVIDENCE_ITEMS,
  runMockAssessment,
} from "./data/presets";
import {
  REASON_EXPLANATIONS,
  STATUS_META,
  type AssessmentResponse,
  type ClaimRequest,
  type Evidence,
  type LineStringGeometry,
} from "./types/contract";

function parseLineString(raw: string): {
  geometry: LineStringGeometry | null;
  parseError: string | null;
} {
  try {
    const parsed = JSON.parse(raw);
    if (
      !parsed ||
      typeof parsed !== "object" ||
      parsed.type !== "LineString" ||
      !Array.isArray(parsed.coordinates) ||
      parsed.coordinates.length < 2
    ) {
      return {
        geometry: null,
        parseError: "Geometry must be a GeoJSON LineString with at least 2 [lon, lat] coordinates.",
      };
    }
    return { geometry: parsed as LineStringGeometry, parseError: null };
  } catch (err) {
    return {
      geometry: null,
      parseError: err instanceof Error ? `Invalid JSON: ${err.message}` : "Invalid GeoJSON.",
    };
  }
}

function formatSignedDelta(observedAt: string | null, claimedAt: string): string {
  if (!observedAt) return "Observation time unknown";
  const obsMs = Date.parse(observedAt);
  const claimMs = Date.parse(claimedAt);
  if (Number.isNaN(obsMs) || Number.isNaN(claimMs)) return "Invalid timestamp";
  const diffHours = (claimMs - obsMs) / 36e5;
  const absH = Math.abs(diffHours).toFixed(2);
  if (Math.abs(diffHours) < 0.005) return "0.00 h (contemporaneous)";
  return diffHours > 0
    ? `Claim is +${absH} h after observation`
    : `Claim is -${absH} h before observation`;
}

export function App() {
  const initialPreset = CLAIM_PRESETS[0];

  const [mockMode, setMockMode] = useState(false);
  const [selectedPresetId, setSelectedPresetId] = useState(initialPreset.id);

  // Form fields
  const [claimId, setClaimId] = useState(initialPreset.claim.claim_id);
  const [sourceLabel, setSourceLabel] = useState(initialPreset.claim.source_label);
  const [claimedAt, setClaimedAt] = useState(initialPreset.claim.claimed_at);
  const [syntheticClaim, setSyntheticClaim] = useState(initialPreset.claim.synthetic);
  const [geometryText, setGeometryText] = useState(
    JSON.stringify(initialPreset.claim.geometry, null, 2),
  );

  // Remote / evidence state
  const [healthStatus, setHealthStatus] = useState<"checking" | "connected" | "error" | "mock">(
    "checking",
  );
  const [contractVersion, setContractVersion] = useState<string>("0.1");
  const [evidenceItems, setEvidenceItems] = useState<Evidence[]>([]);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  // Assessment state
  const [assessing, setAssessing] = useState(false);
  const [assessment, setAssessment] = useState<AssessmentResponse | null>(null);
  const [assessError, setAssessError] = useState<{
    message: string;
    details: string[];
  } | null>(null);

  const { geometry: parsedGeometry, parseError: geometryHint } = useMemo(
    () => parseLineString(geometryText),
    [geometryText],
  );

  const loadLiveEvidence = useCallback(async () => {
    setEvidenceLoading(true);
    setEvidenceError(null);
    setHealthStatus("checking");
    try {
      const [health, evRes] = await Promise.all([fetchHealth(), fetchEvidence()]);
      setHealthStatus("connected");
      setContractVersion(health.contract_version);
      setEvidenceItems(evRes.items);
    } catch (err) {
      setHealthStatus("error");
      setEvidenceItems([]);
      const msg =
        err instanceof Error
          ? err.message
          : "Unable to connect to EIP API.";
      setEvidenceError(
        `Live API unreachable at ${API_BASE_URL} (${msg}). Mock mode is NOT enabled automatically — fix API connectivity or explicitly switch to Mock Mode.`,
      );
    } finally {
      setEvidenceLoading(false);
    }
  }, []);

  useEffect(() => {
    if (mockMode) {
      setHealthStatus("mock");
      setEvidenceError(null);
      setEvidenceItems(MOCK_EVIDENCE_ITEMS);
      setAssessment(null);
      setAssessError(null);
    } else {
      setAssessment(null);
      setAssessError(null);
      void loadLiveEvidence();
    }
  }, [mockMode, loadLiveEvidence]);

  const handleSelectPreset = (presetId: string) => {
    setSelectedPresetId(presetId);
    const preset = CLAIM_PRESETS.find((p) => p.id === presetId);
    if (!preset) return;
    setClaimId(preset.claim.claim_id);
    setSourceLabel(preset.claim.source_label);
    setClaimedAt(preset.claim.claimed_at);
    setSyntheticClaim(preset.claim.synthetic);
    setGeometryText(JSON.stringify(preset.claim.geometry, null, 2));
    setAssessError(null);
  };

  const handleAssess = async (e: React.FormEvent) => {
    e.preventDefault();
    setAssessError(null);

    let rawGeom: unknown;
    try {
      rawGeom = JSON.parse(geometryText);
    } catch (err) {
      setAssessError({
        message: "Malformed GeoJSON in geometry field.",
        details: [err instanceof Error ? err.message : "Could not parse JSON."],
      });
      return;
    }

    const payload = {
      claim_id: claimId.trim(),
      claim_type: "road_passable" as const,
      geometry: rawGeom,
      claimed_at: claimedAt.trim(),
      source_label: sourceLabel.trim(),
      synthetic: syntheticClaim,
    };

    if (mockMode) {
      if (!parsedGeometry) {
        setAssessError({
          message: "Validation error (Mock Mode)",
          details: [geometryHint ?? "Invalid LineString geometry."],
        });
        return;
      }
      setAssessment(runMockAssessment(payload as ClaimRequest, evidenceItems));
      return;
    }

    setAssessing(true);
    try {
      const result = await submitAssessment(payload);
      setAssessment(result);
    } catch (err) {
      setAssessment(null);
      if (err instanceof ApiError) {
        setAssessError({ message: err.message, details: err.details });
      } else {
        setAssessError({
          message: `API request failed against ${API_BASE_URL}.`,
          details: [
            err instanceof Error ? err.message : "Network error",
            "Live mode never falls back to mock data silently.",
          ],
        });
      }
    } finally {
      setAssessing(false);
    }
  };

  const evidenceById = useMemo(() => {
    const map = new Map<string, Evidence>();
    for (const ev of evidenceItems) {
      map.set(ev.id, ev);
    }
    return map;
  }, [evidenceItems]);

  const statusMeta = assessment ? STATUS_META[assessment.status] : null;
  const anySynthetic =
    syntheticClaim ||
    Boolean(assessment?.synthetic) ||
    evidenceItems.some((e) => e.synthetic);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-group">
          <div className="brand-mark" aria-hidden="true">
            EIP
          </div>
          <div>
            <h1 className="brand-title">Evidence Inspector</h1>
            <p className="brand-subtitle">
              Evidence Integrity Platform · Contract v{contractVersion} · Geospatial &amp; Temporal Consistency
            </p>
          </div>
        </div>

        <div className="header-badges" aria-label="Session context labels">
          <span className="pill pill-replay" title="Evaluating archived historical event data">
            HISTORICAL REPLAY
          </span>
          {anySynthetic && (
            <span
              className="pill pill-synthetic"
              title="Includes explicitly synthetic road report or fixture"
            >
              SYNTHETIC INPUT
            </span>
          )}
          <span
            className={`pill ${
              healthStatus === "connected"
                ? "pill-api-ok"
                : healthStatus === "mock"
                  ? "pill-mock"
                  : healthStatus === "error"
                    ? "pill-error"
                    : "pill-neutral"
            }`}
            data-testid="connection-status"
          >
            {healthStatus === "connected"
              ? `Live API (${API_BASE_URL})`
              : healthStatus === "mock"
                ? "Mock Mode (Synthetic)"
                : healthStatus === "error"
                  ? "API Disconnected"
                  : "Checking API…"}
          </span>

          <label className="mode-switch">
            <input
              type="checkbox"
              checked={mockMode}
              onChange={(e) => setMockMode(e.target.checked)}
              aria-label="Toggle Mock Mode"
            />
            <span>Mock Mode</span>
          </label>
        </div>
      </header>

      {mockMode && (
        <div className="banner banner-mock" role="status" data-testid="mock-banner">
          <strong>Mock Mode Active:</strong> Displaying built-in simplified synthetic fixtures in the browser.
          Switch off Mock Mode to query genuine Copernicus EMS evidence from <code>{API_BASE_URL}</code>.
        </div>
      )}

      {evidenceError && !mockMode && (
        <div className="banner banner-error" role="alert" data-testid="api-error-banner">
          <span>{evidenceError}</span>
          <button
            type="button"
            className="btn-ghost"
            onClick={() => void loadLiveEvidence()}
          >
            Retry API
          </button>
        </div>
      )}

      <main className="workspace-grid">
        {/* Left Column: Structured Claim Input */}
        <section className="panel claim-panel" aria-label="Claim input">
          <div className="panel-header">
            <h2>1. Structured Claim</h2>
            <span className="panel-tag">road_passable</span>
          </div>

          <div className="field-group">
            <label htmlFor="preset-select">Historical Replay Scenario</label>
            <select
              id="preset-select"
              value={selectedPresetId}
              onChange={(e) => handleSelectPreset(e.target.value)}
            >
              {CLAIM_PRESETS.map((preset) => (
                <option key={preset.id} value={preset.id}>
                  {preset.label}
                </option>
              ))}
            </select>
            <p className="field-help">
              {CLAIM_PRESETS.find((p) => p.id === selectedPresetId)?.description}
            </p>
          </div>

          <form onSubmit={handleAssess} className="claim-form" noValidate>
            <div className="field-row">
              <div className="field-group">
                <label htmlFor="claim-id">Claim ID</label>
                <input
                  id="claim-id"
                  type="text"
                  value={claimId}
                  onChange={(e) => setClaimId(e.target.value)}
                  required
                />
              </div>

              <div className="field-group">
                <label htmlFor="claimed-at">Claimed At (UTC ISO 8601)</label>
                <input
                  id="claimed-at"
                  type="text"
                  value={claimedAt}
                  onChange={(e) => setClaimedAt(e.target.value)}
                  placeholder="2024-04-15T08:00:00Z"
                  required
                />
              </div>
            </div>

            <div className="field-group">
              <label htmlFor="source-label">Claim Source Label</label>
              <input
                id="source-label"
                type="text"
                value={sourceLabel}
                onChange={(e) => setSourceLabel(e.target.value)}
                required
              />
            </div>

            <div className="field-group">
              <label htmlFor="geometry-json">Road Geometry (WGS84 GeoJSON LineString)</label>
              <textarea
                id="geometry-json"
                rows={7}
                value={geometryText}
                onChange={(e) => setGeometryText(e.target.value)}
                spellCheck={false}
              />
              {geometryHint && (
                <p className="field-warning" role="status">
                  {geometryHint}
                </p>
              )}
            </div>

            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={syntheticClaim}
                onChange={(e) => setSyntheticClaim(e.target.checked)}
              />
              <span>Explicitly synthetic road report (required for simulated claims)</span>
            </label>

            <div className="form-actions">
              <button
                type="submit"
                className="btn-primary"
                disabled={assessing}
                data-testid="assess-button"
              >
                {assessing ? "Assessing…" : "Assess Claim"}
              </button>
              {!mockMode && (
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => void loadLiveEvidence()}
                  disabled={evidenceLoading}
                >
                  {evidenceLoading ? "Loading…" : "Reload Evidence"}
                </button>
              )}
            </div>
          </form>

          {assessError && (
            <div className="error-box" role="alert" data-testid="assess-error">
              <strong>{assessError.message}</strong>
              {assessError.details.length > 0 && (
                <ul>
                  {assessError.details.map((d, idx) => (
                    <li key={idx}>{d}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>

        {/* Center Column: Interactive MapLibre Evidence Map */}
        <EvidenceMap
          evidenceItems={evidenceItems}
          claimGeometry={parsedGeometry}
          assessmentStatus={assessment?.status ?? null}
        />

        {/* Right Column: Assessment Verdict, Findings & Provenance */}
        <section className="panel results-panel" aria-label="Assessment result and provenance">
          <div className="panel-header">
            <h2>2. Assessment &amp; Provenance</h2>
            <span className="panel-tag">
              {assessment ? assessment.policy_version : "flood-road-0.1"}
            </span>
          </div>

          {!assessment ? (
            <div className="empty-state" data-testid="empty-assessment">
              <p>
                Select a historical replay scenario or edit the WGS84 GeoJSON road segment, then click{" "}
                <strong>Assess Claim</strong> to run deterministic spatial and temporal evaluation.
              </p>
              <p className="muted-note">
                Loaded evidence records: <strong>{evidenceItems.length}</strong>{" "}
                {evidenceItems.length > 0 && evidenceItems.every((e) => !e.synthetic)
                  ? "(genuine Copernicus EMS archive)"
                  : evidenceItems.length > 0
                    ? "(includes synthetic fixture)"
                    : "(none)"}
              </p>
            </div>
          ) : (
            <div className="assessment-content" data-testid="assessment-result">
              <div className={`status-card status-${statusMeta?.tone}`}>
                <div className="status-top">
                  <span className="status-badge" data-testid="assessment-status">
                    {statusMeta?.label}
                  </span>
                  <span className="status-code">{assessment.status}</span>
                </div>
                <p className="status-summary">{statusMeta?.summary}</p>
                <p className="status-caution">{statusMeta?.caution}</p>
                <div className="status-meta-row">
                  <span>Policy: {assessment.policy_version}</span>
                  <span>Synthetic: {assessment.synthetic ? "Yes" : "No"}</span>
                  <span>Evidence checked: {assessment.evidence_ids.length}</span>
                </div>
              </div>

              <div className="section-block">
                <h3>Reason Codes</h3>
                <ul className="reason-list" data-testid="reason-list">
                  {assessment.reasons.map((code) => (
                    <li key={code} className="reason-item">
                      <code>{code}</code>
                      <span>{REASON_EXPLANATIONS[code]}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="section-block">
                <h3>Per-Source Findings</h3>
                {assessment.findings.length === 0 ? (
                  <p className="muted-note">No evidence records were evaluated.</p>
                ) : (
                  <div className="findings-list">
                    {assessment.findings.map((finding) => {
                      const ev = evidenceById.get(finding.evidence_id);
                      return (
                        <article key={finding.evidence_id} className="finding-card">
                          <div className="finding-header">
                            <strong>{ev?.product_id ?? finding.evidence_id}</strong>
                            <span className="mini-badge">{finding.status}</span>
                          </div>
                          <dl className="meta-grid">
                            <div>
                              <dt>Observation (UTC)</dt>
                              <dd>{ev?.observed_at ?? "Unknown (null)"}</dd>
                            </div>
                            <div>
                              <dt>Claim (UTC)</dt>
                              <dd>{claimedAt}</dd>
                            </div>
                            <div>
                              <dt>Temporal Offset</dt>
                              <dd>
                                {finding.age_hours !== null
                                  ? `${finding.age_hours.toFixed(2)} h (${formatSignedDelta(
                                      ev?.observed_at ?? null,
                                      claimedAt,
                                    )})`
                                  : "Unknown"}
                              </dd>
                            </div>
                            <div>
                              <dt>Authentication</dt>
                              <dd>
                                {ev?.authentication === "verified"
                                  ? "Verified"
                                  : ev?.authentication === "failed"
                                    ? "Failed (excluded)"
                                    : "Unknown (unverified)"}
                              </dd>
                            </div>
                          </dl>
                        </article>
                      );
                    })}
                  </div>
                )}
              </div>

              <div className="section-block">
                <h3>Known Limitations</h3>
                <ul className="limitations-list" data-testid="limitations-list">
                  {assessment.limitations.map((lim, idx) => (
                    <li key={idx}>{lim}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Always display active evidence provenance when loaded */}
          <div className="section-block provenance-section">
            <h3>Loaded Evidence Provenance ({evidenceItems.length})</h3>
            {evidenceItems.length === 0 ? (
              <p className="muted-note" data-testid="no-evidence-note">
                No evidence records loaded.
              </p>
            ) : (
              evidenceItems.map((ev) => (
                <article key={ev.id} className="provenance-card" data-testid="provenance-card">
                  <div className="finding-header">
                    <strong>{ev.product_id ?? ev.id}</strong>
                    <span className={`mini-badge ${ev.synthetic ? "mini-synth" : "mini-real"}`}>
                      {ev.synthetic ? "Synthetic fixture" : "Genuine Copernicus"}
                    </span>
                  </div>
                  <dl className="meta-grid">
                    <div>
                      <dt>Source</dt>
                      <dd>{ev.source}</dd>
                    </div>
                    <div>
                      <dt>Observed (UTC)</dt>
                      <dd>{ev.observed_at ?? "Unknown"}</dd>
                    </div>
                    <div>
                      <dt>Retrieved (UTC)</dt>
                      <dd>{ev.retrieved_at ?? "Unknown"}</dd>
                    </div>
                    <div>
                      <dt>Documented Coverage</dt>
                      <dd>{ev.coverage ? "Present (AOI / Footprint)" : "None (null)"}</dd>
                    </div>
                    {ev.raw_path && (
                      <div className="span-2">
                        <dt>Local Raw Artifact</dt>
                        <dd>
                          <code>{ev.raw_path}</code>
                        </dd>
                      </div>
                    )}
                    {ev.sha256 && (
                      <div className="span-2">
                        <dt>Raw Artifact SHA-256 (local integrity only)</dt>
                        <dd>
                          <code className="hash-code">{ev.sha256}</code>
                        </dd>
                      </div>
                    )}
                    {ev.source_url && (
                      <div className="span-2">
                        <dt>Provider URL</dt>
                        <dd>
                          <a href={ev.source_url} target="_blank" rel="noreferrer">
                            {ev.source_url}
                          </a>
                        </dd>
                      </div>
                    )}
                    {ev.licence && (
                      <div className="span-2">
                        <dt>Licence / Attribution</dt>
                        <dd>{ev.licence}</dd>
                      </div>
                    )}
                  </dl>
                </article>
              ))
            )}
          </div>
        </section>
      </main>

      <footer className="disclaimer-footer">
        Evidence Integrity Platform (CASSINI 12 Hackathon Prototype) — Independent evidence consistency check only.
        Not a truth oracle, safety certification, or emergency routing service. 24-hour window is a demo policy.
      </footer>
    </div>
  );
}
