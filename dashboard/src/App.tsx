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
  GALILEO_PRESETS,
  MOCK_EVIDENCE_ITEMS,
  runMockAssessment,
} from "./data/presets";
import {
  INDEPENDENCE_LABELS,
  REASON_EXPLANATIONS,
  STATUS_META,
  type AssessmentResponse,
  type ClaimRequest,
  type Evidence,
  type LineStringGeometry,
} from "./types/contract";

type InspectorDomain = "environmental" | "galileo";

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
  const initialEnvPreset = CLAIM_PRESETS[0];
  const initialGalileoPreset = GALILEO_PRESETS[0];

  const [domain, setDomain] = useState<InspectorDomain>("environmental");
  const [mockMode, setMockMode] = useState(false);

  // Environmental preset/form fields
  const [selectedPresetId, setSelectedPresetId] = useState(initialEnvPreset.id);
  const [claimId, setClaimId] = useState(initialEnvPreset.claim.claim_id);
  const [claimType, setClaimType] = useState(initialEnvPreset.claim.claim_type);
  const [sourceLabel, setSourceLabel] = useState(initialEnvPreset.claim.source_label);
  const [claimedAt, setClaimedAt] = useState(initialEnvPreset.claim.claimed_at);
  const [syntheticClaim, setSyntheticClaim] = useState(initialEnvPreset.claim.synthetic);
  const [geometryText, setGeometryText] = useState(
    JSON.stringify(initialEnvPreset.claim.geometry, null, 2),
  );
  const [galileoSvid, setGalileoSvid] = useState<string>("27");

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

  const activeEvidenceItems = useMemo(() => {
    if (domain === "galileo") {
      return evidenceItems.filter((ev) => ev.kind === "gnss_osnma_auth");
    }
    return evidenceItems.filter((ev) => ev.kind !== "gnss_osnma_auth");
  }, [domain, evidenceItems]);

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
      const msg = err instanceof Error ? err.message : "Unable to connect to EIP API.";
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

  const applyPreset = (targetDomain: InspectorDomain, presetId: string) => {
    const list = targetDomain === "galileo" ? GALILEO_PRESETS : CLAIM_PRESETS;
    const preset = list.find((p) => p.id === presetId) ?? list[0];
    setSelectedPresetId(preset.id);
    setClaimId(preset.claim.claim_id);
    setClaimType(preset.claim.claim_type);
    setSourceLabel(preset.claim.source_label);
    setClaimedAt(preset.claim.claimed_at);
    setSyntheticClaim(preset.claim.synthetic);
    if (preset.claim.geometry) {
      setGeometryText(JSON.stringify(preset.claim.geometry, null, 2));
    }
    const svidVal = preset.claim.attributes?.svid;
    setGalileoSvid(typeof svidVal === "number" ? String(svidVal) : "");
    setAssessError(null);
    setAssessment(null);
  };

  const handleSwitchDomain = (nextDomain: InspectorDomain) => {
    if (nextDomain === domain) return;
    setDomain(nextDomain);
    if (nextDomain === "galileo") {
      applyPreset("galileo", initialGalileoPreset.id);
    } else {
      applyPreset("environmental", initialEnvPreset.id);
    }
  };

  const handleSelectPreset = (presetId: string) => {
    applyPreset(domain, presetId);
  };

  const handleAssess = async (e: React.FormEvent) => {
    e.preventDefault();
    setAssessError(null);

    let payload: Record<string, unknown>;

    if (domain === "galileo") {
      const attrs: Record<string, unknown> = {};
      if (claimType === "gnss_nav_message_authenticated" && galileoSvid.trim() !== "") {
        const parsedSvid = Number(galileoSvid.trim());
        attrs.svid = Number.isNaN(parsedSvid) ? galileoSvid.trim() : parsedSvid;
      }
      payload = {
        claim_id: claimId.trim(),
        claim_type: claimType,
        geometry: null,
        claimed_at: claimedAt.trim(),
        source_label: sourceLabel.trim(),
        synthetic: syntheticClaim,
        attributes: attrs,
      };
    } else {
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
      payload = {
        claim_id: claimId.trim(),
        claim_type: "road_passable",
        geometry: rawGeom,
        claimed_at: claimedAt.trim(),
        source_label: sourceLabel.trim(),
        synthetic: syntheticClaim,
      };
    }

    if (mockMode) {
      if (domain === "galileo") {
        setAssessError({
          message: "Mock Mode supports environmental flood fixtures only.",
          details: ["Switch off Mock Mode to run local Galileo OSNMA verification against the live API."],
        });
        return;
      }
      if (!parsedGeometry) {
        setAssessError({
          message: "Validation error (Mock Mode)",
          details: [geometryHint ?? "Invalid LineString geometry."],
        });
        return;
      }
      setAssessment(runMockAssessment(payload as unknown as ClaimRequest, activeEvidenceItems));
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
    activeEvidenceItems.some((e) => e.synthetic);

  const presetsForDomain = domain === "galileo" ? GALILEO_PRESETS : CLAIM_PRESETS;
  const primaryGalileoEvidence = activeEvidenceItems[0] ?? null;

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
              Evidence Integrity Platform · Contract v{contractVersion} · Multi-Policy Assessment
            </p>
          </div>
        </div>

        <div className="domain-tabs" role="tablist" aria-label="Assessment domain">
          <button
            type="button"
            role="tab"
            aria-selected={domain === "environmental"}
            className={`domain-tab ${domain === "environmental" ? "domain-tab-active" : ""}`}
            onClick={() => handleSwitchDomain("environmental")}
            data-testid="tab-environmental"
          >
            Environmental (Flood / Road)
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={domain === "galileo"}
            className={`domain-tab ${domain === "galileo" ? "domain-tab-active" : ""}`}
            onClick={() => handleSwitchDomain("galileo")}
            data-testid="tab-galileo"
          >
            Galileo OSNMA (Nav Auth)
          </button>
        </div>

        <div className="header-badges" aria-label="Session context labels">
          <span className="pill pill-replay" title="Evaluating archived historical event data">
            HISTORICAL REPLAY
          </span>
          {anySynthetic && (
            <span
              className="pill pill-synthetic"
              title="Includes explicitly synthetic claim or fixture"
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
          Switch off Mock Mode to query genuine recorded evidence from <code>{API_BASE_URL}</code>.
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
            <span className="panel-tag" data-testid="active-claim-type">
              {claimType}
            </span>
          </div>

          <div className="field-group">
            <label htmlFor="preset-select">Historical Replay Scenario</label>
            <select
              id="preset-select"
              value={selectedPresetId}
              onChange={(e) => handleSelectPreset(e.target.value)}
            >
              {presetsForDomain.map((preset) => (
                <option key={preset.id} value={preset.id}>
                  {preset.label}
                </option>
              ))}
            </select>
            <p className="field-help">
              {presetsForDomain.find((p) => p.id === selectedPresetId)?.description}
            </p>
          </div>

          <form onSubmit={handleAssess} className="claim-form" noValidate>
            {domain === "galileo" && (
              <div className="field-group">
                <label htmlFor="galileo-claim-type">Claim Type</label>
                <select
                  id="galileo-claim-type"
                  value={claimType}
                  onChange={(e) => setClaimType(e.target.value)}
                >
                  <option value="gnss_nav_message_authenticated">
                    gnss_nav_message_authenticated (Nav Message Auth)
                  </option>
                  <option value="gnss_position_accurate">
                    gnss_position_accurate (Position Accuracy — Unsuitable)
                  </option>
                </select>
              </div>
            )}

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

            {domain === "galileo" && claimType === "gnss_nav_message_authenticated" && (
              <div className="field-group">
                <label htmlFor="galileo-svid">Target Galileo SVID / PRN (1–36, optional)</label>
                <input
                  id="galileo-svid"
                  type="text"
                  value={galileoSvid}
                  onChange={(e) => setGalileoSvid(e.target.value)}
                  placeholder="e.g. 27 (E27) or leave blank for any"
                />
              </div>
            )}

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

            {domain === "environmental" && (
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
            )}

            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={syntheticClaim}
                onChange={(e) => setSyntheticClaim(e.target.checked)}
              />
              <span>Explicitly synthetic claim (required for simulated inputs)</span>
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

        {/* Center Column: Map (Environmental) OR Cryptographic Verification View (Galileo OSNMA) */}
        {domain === "environmental" ? (
          <EvidenceMap
            evidenceItems={activeEvidenceItems}
            claimGeometry={parsedGeometry}
            assessmentStatus={assessment?.status ?? null}
          />
        ) : (
          <section className="panel crypto-panel" aria-label="Galileo OSNMA verification overview" data-testid="galileo-crypto-panel">
            <div className="panel-header">
              <h2>Galileo OSNMA Cryptographic Verification</h2>
              <span className="panel-tag">SIS ICD v1.1 · Offline Local</span>
            </div>

            {!primaryGalileoEvidence ? (
              <div className="empty-state">
                No Galileo OSNMA evidence records loaded in active store.
              </div>
            ) : (
              <div className="crypto-stack">
                <div className="crypto-banner">
                  <strong>What OSNMA Cryptographically Authenticates:</strong>{" "}
                  {String(primaryGalileoEvidence.attributes?.authenticated_scope ?? "Galileo I/NAV ADKD=0 navigation data")}
                </div>

                <div className="crypto-layers">
                  <div className="crypto-step">
                    <span className="step-num">1</span>
                    <div>
                      <strong>GSC Merkle Tree Proof (SHA-256)</strong>
                      <p className="muted-note">
                        Status:{" "}
                        <strong>
                          {primaryGalileoEvidence.attributes?.merkle_proof_verified ? "Verified locally" : "Failed / Unverified"}
                        </strong>{" "}
                        · PKID {String(primaryGalileoEvidence.attributes?.pkid ?? "?")} ({String(primaryGalileoEvidence.attributes?.pk_type ?? "?")})
                      </p>
                      <code className="hash-code">
                        Root: {String(primaryGalileoEvidence.attributes?.merkle_root_sha256 ?? "N/A")}
                      </code>
                    </div>
                  </div>

                  <div className="crypto-step">
                    <span className="step-num">2</span>
                    <div>
                      <strong>DSM-KROOT Digital Signature (ECDSA P-256)</strong>
                      <p className="muted-note">
                        Status:{" "}
                        <strong>
                          {primaryGalileoEvidence.attributes?.ecdsa_kroot_verified ? "Verified locally" : "Failed / Unverified"}
                        </strong>{" "}
                        · Chain ID {String(primaryGalileoEvidence.attributes?.chain_id ?? "?")} · NMAS:{" "}
                        <code>{String(primaryGalileoEvidence.attributes?.nma_status ?? "?")}</code>
                      </p>
                    </div>
                  </div>

                  <div className="crypto-step">
                    <span className="step-num">3</span>
                    <div>
                      <strong>TESLA One-Way Key Chain (SHA-256)</strong>
                      <p className="muted-note">
                        Verified subframes chained to KROOT:{" "}
                        <strong>{String(primaryGalileoEvidence.attributes?.tesla_verified_subframes ?? 0)}</strong>{" "}
                        (Key size {String(primaryGalileoEvidence.attributes?.key_size_bits ?? "?")} bits)
                      </p>
                    </div>
                  </div>

                  <div className="crypto-step">
                    <span className="step-num">4</span>
                    <div>
                      <strong>I/NAV ADKD=0 MAC Tag0 Verification (HMAC-SHA-256)</strong>
                      <p className="muted-note">
                        Tags verified:{" "}
                        <strong>
                          {String(primaryGalileoEvidence.attributes?.tag0_verified_count ?? 0)} /{" "}
                          {String(primaryGalileoEvidence.attributes?.tag0_checked_count ?? 0)}
                        </strong>{" "}
                        ({String(primaryGalileoEvidence.attributes?.tag_size_bits ?? "?")}-bit tags) · SVIDs:{" "}
                        <code>
                          {Array.isArray(primaryGalileoEvidence.attributes?.authenticated_svids)
                            ? (primaryGalileoEvidence.attributes.authenticated_svids as number[])
                                .map((s) => `E${String(s).padStart(2, "0")}`)
                                .join(", ")
                            : "none"}
                        </code>
                      </p>
                    </div>
                  </div>
                </div>

                <div className="scope-warning-box">
                  <strong>Explicit Scope Boundary — What OSNMA Does NOT Prove:</strong>
                  <ul>
                    <li>Does NOT guarantee accurate user position or valid pseudorange measurements.</li>
                    <li>Does NOT verify receiver hardware, antenna, or firmware trustworthiness.</li>
                    <li>Does NOT protect against signal replay / meaconing spoofing without live trusted time sync.</li>
                  </ul>
                </div>

                <dl className="meta-grid">
                  <div>
                    <dt>Verification Method</dt>
                    <dd>
                      <code>{String(primaryGalileoEvidence.attributes?.verification_method ?? "unknown")}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>Recorded Receiver</dt>
                    <dd>
                      {String(primaryGalileoEvidence.attributes?.receiver_model ?? "Unknown")} (fw{" "}
                      {String(primaryGalileoEvidence.attributes?.receiver_firmware ?? "?")})
                    </dd>
                  </div>
                  <div>
                    <dt>Galileo System Time</dt>
                    <dd>
                      WN {String(primaryGalileoEvidence.attributes?.gst_week ?? "?")} · TOW{" "}
                      {String(primaryGalileoEvidence.attributes?.gst_tow_start ?? "?")}–
                      {String(primaryGalileoEvidence.attributes?.gst_tow_end ?? "?")} s
                    </dd>
                  </div>
                  <div>
                    <dt>Zero-NMA Subframes</dt>
                    <dd>{String(primaryGalileoEvidence.attributes?.unauthenticated_zero_nma_subframes ?? 0)}</dd>
                  </div>
                </dl>
              </div>
            )}
          </section>
        )}

        {/* Right Column: Assessment Verdict, Findings & Provenance */}
        <section className="panel results-panel" aria-label="Assessment result and provenance">
          <div className="panel-header">
            <h2>2. Assessment &amp; Provenance</h2>
            <span className="panel-tag" data-testid="active-policy-version">
              {assessment
                ? assessment.policy_version
                : domain === "galileo"
                  ? "galileo-osnma-0.1"
                  : "flood-road-0.1"}
            </span>
          </div>

          {!assessment ? (
            <div className="empty-state" data-testid="empty-assessment">
              <p>
                Select a historical replay scenario or edit the claim fields, then click{" "}
                <strong>Assess Claim</strong> to run deterministic evaluation via <code>POST /v1/assess</code>.
              </p>
              <p className="muted-note">
                Loaded evidence records for active domain: <strong>{activeEvidenceItems.length}</strong>{" "}
                {activeEvidenceItems.length > 0 && activeEvidenceItems.every((e) => !e.synthetic)
                  ? "(genuine recorded provider data)"
                  : activeEvidenceItems.length > 0
                    ? "(includes synthetic fixture)"
                    : "(none)"}
              </p>
            </div>
          ) : (
            <div className="assessment-content" data-testid="assessment-result">
              <div className={`status-card status-${statusMeta?.tone ?? "muted"}`}>
                <div className="status-top">
                  <span className="status-badge" data-testid="assessment-status">
                    {statusMeta?.label ?? assessment.status}
                  </span>
                  <span className="status-code">{assessment.status}</span>
                </div>
                <p className="status-summary">{statusMeta?.summary}</p>
                <p className="status-caution">{statusMeta?.caution}</p>
                <div className="status-meta-row">
                  <span>Claim type: {claimType}</span>
                  <span>
                    Policy: {assessment.traceability?.policy_id ?? "policy"} ({assessment.policy_version})
                  </span>
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
                      <span>{REASON_EXPLANATIONS[code] ?? code}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {assessment.independence && (
                <div className="section-block" data-testid="independence-summary">
                  <h3>Source Independence</h3>
                  <div className="finding-card">
                    <div className="finding-header">
                      <strong>{INDEPENDENCE_LABELS[assessment.independence.status]}</strong>
                      <span className="mini-badge">
                        {assessment.independence.independent_group_count !== null
                          ? `${assessment.independence.independent_group_count} independent group(s) / ${assessment.independence.assessed_source_count} source(s)`
                          : `Unknown groups (${assessment.independence.assessed_source_count} sources)`}
                      </span>
                    </div>
                    {assessment.independence.correlated_groups.length > 0 && (
                      <div className="group-chips">
                        {assessment.independence.correlated_groups.map((grp, idx) => (
                          <span key={idx} className="group-chip">
                            Group {idx + 1}: {grp.join(" + ")}
                          </span>
                        ))}
                      </div>
                    )}
                    {assessment.independence.shared_dependencies.length > 0 && (
                      <p className="field-warning">
                        Shared upstream links: {assessment.independence.shared_dependencies.join(", ")}
                      </p>
                    )}
                    {assessment.independence.notes.map((note, idx) => (
                      <p key={idx} className="muted-note">
                        {note}
                      </p>
                    ))}
                  </div>
                </div>
              )}

              <div className="section-block">
                <h3>Per-Source Findings ({assessment.findings.length})</h3>
                {assessment.findings.length === 0 ? (
                  <p className="muted-note">No evidence records were evaluated.</p>
                ) : (
                  <div className="findings-list" data-testid="findings-list">
                    {assessment.findings.map((finding) => {
                      const ev = evidenceById.get(finding.evidence_id);
                      const isIndirect =
                        ev?.attributes?.evidence_role === "indirect_contextual" ||
                        ev?.kind === "hydrometric_water_level" ||
                        ev?.kind === "meteorological_rainfall";
                      const verMethod = ev?.attributes?.verification_method;
                      return (
                        <article key={finding.evidence_id} className="finding-card">
                          <div className="finding-header">
                            <strong>{ev?.product_id ?? finding.evidence_id}</strong>
                            <div className="badge-row">
                              <span className="mini-badge">
                                {ev?.kind === "gnss_osnma_auth"
                                  ? "OSNMA crypto"
                                  : isIndirect
                                    ? "Indirect contextual"
                                    : "Direct"}
                              </span>
                              <span className="mini-badge">{finding.status}</span>
                            </div>
                          </div>
                          <dl className="meta-grid">
                            <div>
                              <dt>Observation (UTC)</dt>
                              <dd>{ev?.observed_at ?? "Unknown (null)"}</dd>
                            </div>
                            <div>
                              <dt>Available (UTC)</dt>
                              <dd>{ev?.available_at ?? "Unknown (null)"}</dd>
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
                              <dt>Reasons</dt>
                              <dd>
                                <code>{finding.reasons.join(", ")}</code>
                              </dd>
                            </div>
                            <div>
                              <dt>Authentication</dt>
                              <dd>
                                {ev?.authentication === "verified"
                                  ? `Verified (${String(verMethod ?? "local")})`
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
            <h3>Loaded Evidence Provenance ({activeEvidenceItems.length})</h3>
            {activeEvidenceItems.length === 0 ? (
              <p className="muted-note" data-testid="no-evidence-note">
                No evidence records loaded.
              </p>
            ) : (
              activeEvidenceItems.map((ev) => {
                const isIndirect =
                  ev.attributes?.evidence_role === "indirect_contextual" ||
                  ev.kind === "hydrometric_water_level" ||
                  ev.kind === "meteorological_rainfall";
                return (
                  <article key={ev.id} className="provenance-card" data-testid="provenance-card">
                    <div className="finding-header">
                      <strong>{ev.product_id ?? ev.id}</strong>
                      <div className="badge-row">
                        <span className="mini-badge">
                          {ev.kind === "gnss_osnma_auth"
                            ? "OSNMA crypto"
                            : isIndirect
                              ? "Indirect contextual"
                              : "Direct"}
                        </span>
                        <span className={`mini-badge ${ev.synthetic ? "mini-synth" : "mini-real"}`}>
                          {ev.synthetic ? "Synthetic fixture" : "Genuine evidence"}
                        </span>
                      </div>
                    </div>
                    <dl className="meta-grid">
                      <div>
                        <dt>Source / Kind</dt>
                        <dd>
                          {ev.source} · <code>{ev.kind}</code>
                        </dd>
                      </div>
                      <div>
                        <dt>Publisher</dt>
                        <dd>{ev.provenance?.publishing_organisation ?? "Undeclared"}</dd>
                      </div>
                      <div>
                        <dt>Observed (UTC)</dt>
                        <dd>{ev.observed_at ?? "Unknown (null)"}</dd>
                      </div>
                      <div>
                        <dt>Available (UTC)</dt>
                        <dd>{ev.available_at ?? "Unknown (null)"}</dd>
                      </div>
                      <div>
                        <dt>Retrieved (UTC)</dt>
                        <dd>{ev.retrieved_at ?? "Unknown"}</dd>
                      </div>
                      <div>
                        <dt>Authentication</dt>
                        <dd>
                          {ev.authentication === "verified"
                            ? `Verified (${String(ev.attributes?.verification_method ?? "local")})`
                            : ev.authentication === "failed"
                              ? "Failed"
                              : "Unknown (unverified)"}
                        </dd>
                      </div>
                      {ev.provenance?.original_source && (
                        <div className="span-2">
                          <dt>Original Observation Source</dt>
                          <dd>{ev.provenance.original_source}</dd>
                        </div>
                      )}
                      {typeof ev.attributes?.stage_maod === "number" && (
                        <div className="span-2">
                          <dt>Hydrometric Reading</dt>
                          <dd>
                            {ev.attributes.stage_maod} mAOD (median{" "}
                            {String(ev.attributes.historical_median_maod ?? "?")}, p99{" "}
                            {String(ev.attributes.historical_p99_maod ?? "?")}, max{" "}
                            {String(ev.attributes.historical_max_maod ?? "?")})
                          </dd>
                        </div>
                      )}
                      {typeof ev.attributes?.rain_mm === "number" && (
                        <div className="span-2">
                          <dt>Meteorological Reading</dt>
                          <dd>
                            {ev.attributes.rain_mm} mm/day (5-day cumulative:{" "}
                            {String(ev.attributes.cumulative_5day_rain_mm ?? "?")} mm)
                          </dd>
                        </div>
                      )}
                      {typeof ev.attributes?.tag0_verified_count === "number" && (
                        <div className="span-2">
                          <dt>Cryptographic Summary</dt>
                          <dd>
                            {String(ev.attributes.tag0_verified_count)} /{" "}
                            {String(ev.attributes.tag0_checked_count)} ADKD=0 tags verified ·{" "}
                            {String(ev.attributes.tesla_verified_subframes)} TESLA subframes · PKID{" "}
                            {String(ev.attributes.pkid)} · NMAS={String(ev.attributes.nma_status)}
                          </dd>
                        </div>
                      )}
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
                          <dt>Raw Artifact SHA-256</dt>
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
                );
              })
            )}
          </div>
        </section>
      </main>

      <footer className="disclaimer-footer">
        Evidence Integrity Platform (v0.4.0) — Independent evidence consistency &amp; cryptographic navigation-message verification tool.
        Not a truth oracle, safety certification, positioning accuracy guarantee, or emergency routing service.
      </footer>
    </div>
  );
}
