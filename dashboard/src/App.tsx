import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  API_BASE_URL,
  ApiError,
  fetchAssessmentGraph,
  fetchEvidence,
  fetchHealth,
  fetchLocalMapContext,
  runGalileoTamperDemo,
  submitAssessment,
} from "./api/client";
import { EvidenceGraphView } from "./components/EvidenceGraphView";
import { EvidenceMap } from "./components/EvidenceMap";
import { EvidenceTimeline } from "./components/EvidenceTimeline";
import { GalileoPanel } from "./components/GalileoPanel";
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
  type EvidenceGraph,
  type GalileoTamperComparison,
  type LineStringGeometry,
  type LocalMapContext,
} from "./types/contract";

type InspectorDomain = "environmental" | "galileo";
type ViewMode = "presentation" | "technical";
type AssessmentTemporalMode = "retrospective" | "decision_time";

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

function buildFallbackMissingGraph(
  claimId: string,
  claimType: string,
  claimedAt: string,
  synthetic: boolean,
  result: AssessmentResponse,
): EvidenceGraph {
  return {
    independence_status: result.independence?.status ?? "unknown",
    independent_group_count: result.independence?.independent_group_count ?? 0,
    assessed_source_count: 0,
    nodes: [
      {
        id: `claim:${claimId}`,
        node_type: "claim",
        label: claimId,
        subtitle: claimType,
        status: result.status,
        relation_role: null,
        authentication: null,
        freshness: null,
        age_hours: null,
        observed_at: claimedAt,
        available_at: null,
        retrieved_at: null,
        independence_group: null,
        synthetic,
        reasons: result.reasons,
        limitations: result.limitations,
        metadata: {},
      },
      {
        id: "missing:evidence",
        node_type: "missing_evidence",
        label: "No matching evidence available",
        subtitle: "Zero evidence records in active store for this policy",
        status: "missing",
        relation_role: "inconclusive",
        authentication: null,
        freshness: null,
        age_hours: null,
        observed_at: null,
        available_at: null,
        retrieved_at: null,
        independence_group: null,
        synthetic: false,
        reasons: ["NO_EVIDENCE"],
        limitations: result.limitations,
        metadata: {},
      },
    ],
    edges: [
      {
        id: "edge:missing:claim",
        source: "missing:evidence",
        target: `claim:${claimId}`,
        relation: "missing_evidence",
        label: "Missing evidence",
        shared: false,
      },
    ],
  };
}

export function App() {
  const initialEnvPreset = CLAIM_PRESETS[0];
  const initialGalileoPreset = GALILEO_PRESETS[0];

  const [domain, setDomain] = useState<InspectorDomain>("environmental");
  const [viewMode, setViewMode] = useState<ViewMode>("presentation");
  const [mockMode, setMockMode] = useState(false);

  // Temporal mode state
  const [assessmentMode, setAssessmentMode] = useState<AssessmentTemporalMode>("retrospective");
  const [decisionTime, setDecisionTime] = useState<string>(initialEnvPreset.claim.claimed_at);

  // Claim fields
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
  const [localContext, setLocalContext] = useState<LocalMapContext | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  // Assessment & graph state
  const [assessing, setAssessing] = useState(false);
  const [assessment, setAssessment] = useState<AssessmentResponse | null>(null);
  const [evidenceGraph, setEvidenceGraph] = useState<EvidenceGraph | null>(null);
  const [assessedAtHeader, setAssessedAtHeader] = useState<string | null>(null);
  const [assessError, setAssessError] = useState<{
    message: string;
    details: string[];
  } | null>(null);

  // Controlled Galileo tampering demonstration state
  const [tamperComparison, setTamperComparison] = useState<GalileoTamperComparison | null>(null);
  const [tamperLoading, setTamperLoading] = useState(false);
  const [tamperError, setTamperError] = useState<string | null>(null);

  const initialAutoRunDone = useRef(false);

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

  const buildPayloadFromParams = useCallback(
    (params: {
      targetDomain: InspectorDomain;
      cId: string;
      cType: string;
      cAt: string;
      sLabel: string;
      synth: boolean;
      geomRaw: unknown;
      svid: string;
      mode: AssessmentTemporalMode;
      decTime: string;
    }): Record<string, unknown> => {
      const base: Record<string, unknown> = {
        claim_id: params.cId.trim(),
        claim_type: params.targetDomain === "galileo" ? params.cType : "road_passable",
        claimed_at: params.cAt.trim(),
        source_label: params.sLabel.trim(),
        synthetic: params.synth,
      };
      if (params.mode === "decision_time") {
        base.assessment_mode = "decision_time";
        base.decision_time = params.decTime.trim() || params.cAt.trim();
      } else {
        base.assessment_mode = "retrospective";
      }

      if (params.targetDomain === "galileo") {
        const attrs: Record<string, unknown> = {};
        if (params.cType === "gnss_nav_message_authenticated" && params.svid.trim() !== "") {
          const parsedSvid = Number(params.svid.trim());
          attrs.svid = Number.isNaN(parsedSvid) ? params.svid.trim() : parsedSvid;
        }
        base.geometry = null;
        base.attributes = attrs;
      } else {
        base.geometry = params.geomRaw;
      }
      return base;
    },
    [],
  );

  const runLiveAssessment = useCallback(
    async (payload: Record<string, unknown>, cId: string, cType: string, cAt: string, synth: boolean) => {
      setAssessing(true);
      setAssessError(null);
      try {
        const { result, assessedAtHeader: tsHeader } = await submitAssessment(payload);
        setAssessment(result);
        setAssessedAtHeader(tsHeader ?? result.traceability?.assessed_at ?? null);

        if (result.evidence_ids.length > 0) {
          try {
            const graphRes = await fetchAssessmentGraph(payload);
            setEvidenceGraph(graphRes.graph);
          } catch {
            setEvidenceGraph(null);
          }
        } else {
          setEvidenceGraph(buildFallbackMissingGraph(cId, cType, cAt, synth, result));
        }
      } catch (err) {
        setAssessment(null);
        setEvidenceGraph(null);
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
    },
    [],
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

      // Load optional offline local map context (baseline water & landmarks)
      fetchLocalMapContext()
        .then((ctx) => setLocalContext(ctx))
        .catch(() => setLocalContext(null));

      // Auto-assess default scenario once on initial connection when genuine evidence exists
      if (!initialAutoRunDone.current && evRes.items.length > 0) {
        initialAutoRunDone.current = true;
        const payload = buildPayloadFromParams({
          targetDomain: "environmental",
          cId: initialEnvPreset.claim.claim_id,
          cType: initialEnvPreset.claim.claim_type,
          cAt: initialEnvPreset.claim.claimed_at,
          sLabel: initialEnvPreset.claim.source_label,
          synth: initialEnvPreset.claim.synthetic,
          geomRaw: initialEnvPreset.claim.geometry,
          svid: "27",
          mode: "retrospective",
          decTime: initialEnvPreset.claim.claimed_at,
        });
        void runLiveAssessment(
          payload,
          initialEnvPreset.claim.claim_id,
          initialEnvPreset.claim.claim_type,
          initialEnvPreset.claim.claimed_at,
          initialEnvPreset.claim.synthetic,
        );
      }
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
  }, [buildPayloadFromParams, initialEnvPreset, runLiveAssessment]);

  useEffect(() => {
    if (mockMode) {
      setHealthStatus("mock");
      setEvidenceError(null);
      setEvidenceItems(MOCK_EVIDENCE_ITEMS);
      setAssessment(null);
      setEvidenceGraph(null);
      setAssessError(null);
      setTamperComparison(null);
    } else {
      setAssessment(null);
      setEvidenceGraph(null);
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
    setDecisionTime(preset.claim.claimed_at);
    setSyntheticClaim(preset.claim.synthetic);
    if (preset.claim.geometry) {
      setGeometryText(JSON.stringify(preset.claim.geometry, null, 2));
    }
    const svidVal = preset.claim.attributes?.svid;
    setGalileoSvid(typeof svidVal === "number" ? String(svidVal) : "");
    setAssessError(null);
    setAssessment(null);
    setEvidenceGraph(null);
  };

  const handleSwitchDomain = (nextDomain: InspectorDomain) => {
    if (nextDomain === domain) return;
    setDomain(nextDomain);
    setTamperComparison(null);
    setTamperError(null);
    setAssessmentMode("retrospective");
    if (nextDomain === "galileo") {
      applyPreset("galileo", initialGalileoPreset.id);
    } else {
      applyPreset("environmental", initialEnvPreset.id);
    }
  };

  const handleSelectPreset = (presetId: string) => {
    applyPreset(domain, presetId);
  };

  const handleCustomRoadChange = (geom: LineStringGeometry) => {
    setGeometryText(JSON.stringify(geom, null, 2));
    setClaimId("custom-map-road-segment");
    setSourceLabel("Interactive map-drawn road segment (synthetic user input)");
    setSyntheticClaim(true);
    if (!mockMode && healthStatus === "connected") {
      const payload = buildPayloadFromParams({
        targetDomain: "environmental",
        cId: "custom-map-road-segment",
        cType: "road_passable",
        cAt: claimedAt,
        sLabel: "Interactive map-drawn road segment (synthetic user input)",
        synth: true,
        geomRaw: geom,
        svid: galileoSvid,
        mode: assessmentMode,
        decTime: decisionTime,
      });
      void runLiveAssessment(payload, "custom-map-road-segment", "road_passable", claimedAt, true);
    }
  };

  const handleTemporalModeChange = (nextMode: AssessmentTemporalMode) => {
    setAssessmentMode(nextMode);
    const nextDecTime = decisionTime || claimedAt;
    if (nextMode === "decision_time" && !decisionTime) {
      setDecisionTime(claimedAt);
    }
    if (!mockMode && healthStatus === "connected") {
      let rawGeom: unknown = null;
      if (domain === "environmental") {
        try {
          rawGeom = JSON.parse(geometryText);
        } catch {
          return;
        }
      }
      const payload = buildPayloadFromParams({
        targetDomain: domain,
        cId: claimId,
        cType: claimType,
        cAt: claimedAt,
        sLabel: sourceLabel,
        synth: syntheticClaim,
        geomRaw: rawGeom,
        svid: galileoSvid,
        mode: nextMode,
        decTime: nextDecTime,
      });
      void runLiveAssessment(payload, claimId, claimType, claimedAt, syntheticClaim);
    }
  };

  const handleAssess = async (e: React.FormEvent) => {
    e.preventDefault();
    setAssessError(null);

    let rawGeom: unknown = null;
    if (domain === "environmental") {
      try {
        rawGeom = JSON.parse(geometryText);
      } catch (err) {
        setAssessError({
          message: "Malformed GeoJSON in geometry field.",
          details: [err instanceof Error ? err.message : "Could not parse JSON."],
        });
        return;
      }
    }

    const payload = buildPayloadFromParams({
      targetDomain: domain,
      cId: claimId,
      cType: claimType,
      cAt: claimedAt,
      sLabel: sourceLabel,
      synth: syntheticClaim,
      geomRaw: rawGeom,
      svid: galileoSvid,
      mode: assessmentMode,
      decTime: decisionTime,
    });

    if (mockMode) {
      if (domain === "galileo") {
        setAssessError({
          message: "Mock Mode supports environmental flood fixtures only.",
          details: [
            "Switch off Mock Mode to run local Galileo OSNMA verification against the live API.",
          ],
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
      const mockRes = runMockAssessment(
        payload as unknown as ClaimRequest,
        activeEvidenceItems,
      );
      setAssessment(mockRes);
      setEvidenceGraph(null);
      return;
    }

    await runLiveAssessment(payload, claimId, claimType, claimedAt, syntheticClaim);
  };

  const handleRunTamperDemo = async () => {
    setTamperLoading(true);
    setTamperError(null);
    try {
      const res = await runGalileoTamperDemo();
      setTamperComparison(res);
      setAssessment(res.tampered.assessment);
      setEvidenceGraph(res.tampered.graph);
    } catch (err) {
      setTamperError(
        err instanceof Error ? err.message : "Failed to run controlled tampering comparison.",
      );
    } finally {
      setTamperLoading(false);
    }
  };

  const handleClearTamperDemo = () => {
    setTamperComparison(null);
    setTamperError(null);
  };

  const evidenceById = useMemo(() => {
    const map = new Map<string, Evidence>();
    for (const ev of evidenceItems) {
      map.set(ev.id, ev);
    }
    if (tamperComparison) {
      for (const ev of tamperComparison.original.evidence) map.set(ev.id, ev);
      for (const ev of tamperComparison.tampered.evidence) map.set(ev.id, ev);
    }
    return map;
  }, [evidenceItems, tamperComparison]);

  const statusMeta = assessment ? STATUS_META[assessment.status] : null;
  const anySynthetic =
    syntheticClaim ||
    Boolean(assessment?.synthetic) ||
    activeEvidenceItems.some((e) => e.synthetic) ||
    Boolean(tamperComparison);

  const presetsForDomain = domain === "galileo" ? GALILEO_PRESETS : CLAIM_PRESETS;
  const primaryGalileoEvidence = activeEvidenceItems[0] ?? null;

  const activePreset = presetsForDomain.find((p) => p.id === selectedPresetId);

  // Executive 5-second plain-English summary derived strictly from actual state
  const executiveSummary = useMemo(() => {
    const claimDesc =
      domain === "galileo"
        ? claimType === "gnss_position_accurate"
          ? "Claim asserting accurate user GNSS positioning from Galileo OSNMA navigation data."
          : `Claim asserting Galileo ${galileoSvid ? `E${galileoSvid.padStart(2, "0")}` : "I/NAV"} navigation messages were authenticated at ${claimedAt}.`
        : `Claim asserting road segment (${claimId}) was passable at ${claimedAt}.`;

    const evDesc =
      activeEvidenceItems.length === 0
        ? "0 evidence records loaded in active store."
        : domain === "galileo"
          ? `${activeEvidenceItems.length} genuine locally verified Septentrio SBF recording (188/188 ADKD=0 tags, GSC Merkle + ECDSA + TESLA).`
          : `${activeEvidenceItems.length} genuine recorded source(s): Copernicus EMSR718 (direct SAR), GSI Lough Funshinagh gauge, Met Éireann Mt Dillon.${
              assessment?.independence?.independent_group_count
                ? ` (${assessment.independence.independent_group_count} independent group(s)).`
                : ""
            }`;

    const establishes = !assessment
      ? "Pending assessment — click Assess Claim to evaluate deterministically."
      : statusMeta?.summary ?? assessment.status;

    const doesNotEstablish = !assessment
      ? "EIP never certifies road safety, impassability, or GNSS user positioning accuracy."
      : statusMeta?.caution ??
        "Absence of conflict does not prove safety; OSNMA does not prove positioning accuracy.";

    const unknownAvail = activeEvidenceItems.filter((e) => !e.available_at).length;
    const unverifiedAuth = activeEvidenceItems.filter((e) => e.authentication !== "verified").length;
    const trustNote =
      domain === "galileo"
        ? tamperComparison
          ? "Tampered SBF copy is synthetic; local 4-layer OSNMA verifier detected the 1-bit ephemeris modification."
          : "Locally verified (SIS ICD v1.1) on 2023 public test-phase recording (NMAS=1); relies on trusted GSC public key & Merkle root; offline without live replay defense."
        : `${unverifiedAuth}/${activeEvidenceItems.length} source(s) have unverified origin auth; ${unknownAvail}/${activeEvidenceItems.length} lack publication time (available_at = null); 24h window is a demo policy.`;

    return { claimDesc, evDesc, establishes, doesNotEstablish, trustNote };
  }, [
    domain,
    claimType,
    galileoSvid,
    claimedAt,
    claimId,
    activeEvidenceItems,
    assessment,
    statusMeta,
    tamperComparison,
  ]);

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
              Evidence Integrity Platform v0.5.0 · Contract v{contractVersion} · Unified Provenance &amp; Policy Engine
            </p>
          </div>
        </div>

        <div className="nav-switches">
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

          <div className="view-tabs" role="group" aria-label="Interface detail level">
            <button
              type="button"
              className={`domain-tab ${viewMode === "presentation" ? "domain-tab-active" : ""}`}
              onClick={() => setViewMode("presentation")}
              data-testid="view-presentation"
            >
              Presentation
            </button>
            <button
              type="button"
              className={`domain-tab ${viewMode === "technical" ? "domain-tab-active" : ""}`}
              onClick={() => setViewMode("technical")}
              data-testid="view-technical"
            >
              Technical Inspection
            </button>
          </div>
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

      {/* 5-Second Executive Summary Hero */}
      <section
        className={`exec-hero exec-tone-${statusMeta?.tone ?? "muted"}`}
        aria-label="Executive assessment overview"
        data-testid="executive-summary"
      >
        <div className="exec-verdict-col">
          <span className="exec-eyebrow">Deterministic Assessment</span>
          <div className="exec-status-line">
            <strong className="exec-status" data-testid="hero-status">
              {statusMeta ? statusMeta.label : assessing ? "Evaluating…" : "Ready to Assess"}
            </strong>
            {assessment && (
              <span className="mini-badge">
                {assessment.assessment_mode === "decision_time"
                  ? "Decision-Time Audit"
                  : "Retrospective Replay"}
              </span>
            )}
          </div>
          <p className="exec-sub">{activePreset?.label ?? claimId}</p>
        </div>

        <div className="exec-grid">
          <div className="exec-cell">
            <span className="exec-label">1. Claim Evaluated</span>
            <p>{executiveSummary.claimDesc}</p>
          </div>
          <div className="exec-cell">
            <span className="exec-label">2. Available Evidence</span>
            <p>{executiveSummary.evDesc}</p>
          </div>
          <div className="exec-cell">
            <span className="exec-label">3. What It Establishes</span>
            <p>{executiveSummary.establishes}</p>
          </div>
          <div className="exec-cell exec-cell-caution">
            <span className="exec-label">4. What It Does NOT Establish</span>
            <p>{executiveSummary.doesNotEstablish}</p>
          </div>
          <div className="exec-cell">
            <span className="exec-label">5. Why Trust or Treat With Caution</span>
            <p>{executiveSummary.trustNote}</p>
          </div>
        </div>
      </section>

      <main className="workspace-grid">
        {/* Left Column: Structured Claim Input */}
        <section className="panel claim-panel" aria-label="Claim input">
          <div className="panel-header">
            <h2>1. Claim Scenario</h2>
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
            <p className="field-help">{activePreset?.description}</p>
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

            {viewMode === "presentation" && domain === "environmental" && (
              <div className="presentation-hint">
                <strong>Interactive geometry:</strong> Select a scenario above, click{" "}
                <em>Draw Road (2 clicks)</em> on the map to test any custom road segment, or switch to{" "}
                <strong>Technical Inspection</strong> to edit raw WGS84 GeoJSON.
              </div>
            )}

            {viewMode === "technical" && (
              <div className="technical-fields" data-testid="technical-claim-fields">
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
                      rows={6}
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
              </div>
            )}

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
                  {evidenceLoading ? "Loading…" : "Reload"}
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

          {viewMode === "technical" && assessment && (
            <div className="tech-trace-box" data-testid="technical-inspector">
              <h3>Technical Traceability</h3>
              <dl className="meta-grid">
                <div>
                  <dt>Policy ID</dt>
                  <dd>
                    <code>{assessment.traceability?.policy_id ?? "unknown"}</code>
                  </dd>
                </div>
                <div>
                  <dt>Policy Version</dt>
                  <dd>
                    <code>{assessment.policy_version}</code>
                  </dd>
                </div>
                <div className="span-2">
                  <dt>Input Fingerprint (SHA-256)</dt>
                  <dd>
                    <code className="hash-code">
                      {assessment.traceability?.input_fingerprint ?? "N/A"}
                    </code>
                  </dd>
                </div>
              </dl>
              <details className="raw-json-details">
                <summary>Raw Assessment JSON</summary>
                <pre>{JSON.stringify(assessment, null, 2)}</pre>
              </details>
            </div>
          )}
        </section>

        {/* Center Column: Map (Environmental) OR Galileo 4-Stage + Tamper Panel */}
        {domain === "environmental" ? (
          <EvidenceMap
            evidenceItems={activeEvidenceItems}
            claimGeometry={parsedGeometry}
            assessmentStatus={assessment?.status ?? null}
            localContext={localContext}
            onCustomRoadChange={handleCustomRoadChange}
          />
        ) : (
          <GalileoPanel
            evidence={primaryGalileoEvidence}
            tamperComparison={tamperComparison}
            tamperLoading={tamperLoading}
            tamperError={tamperError}
            mockMode={mockMode}
            onRunTamperDemo={() => void handleRunTamperDemo()}
            onClearTamperDemo={handleClearTamperDemo}
          />
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
                Select a historical replay scenario or draw a road segment, then click{" "}
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
                  <span>Claim: {claimType}</span>
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
                                  ? `Verified (${String(verMethod ?? "local")})`
                                  : ev?.authentication === "failed"
                                    ? "Failed (excluded)"
                                    : "Unknown (unverified)"}
                              </dd>
                            </div>
                            <div className="span-2">
                              <dt>Reasons</dt>
                              <dd>
                                <code>{finding.reasons.join(", ")}</code>
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
                        <dt>Publisher</dt>
                        <dd>{ev.provenance?.publishing_organisation ?? ev.source}</dd>
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
                        <dt>Authentication</dt>
                        <dd>
                          {ev.authentication === "verified"
                            ? `Verified (${String(ev.attributes?.verification_method ?? "local")})`
                            : ev.authentication === "failed"
                              ? "Failed"
                              : "Unknown (unverified)"}
                        </dd>
                      </div>
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
                      {ev.sha256 && (
                        <div className="span-2">
                          <dt>Raw Artifact SHA-256</dt>
                          <dd>
                            <code className="hash-code">{ev.sha256}</code>
                          </dd>
                        </div>
                      )}
                      {viewMode === "technical" && ev.provenance?.original_source && (
                        <div className="span-2">
                          <dt>Original Observation Source</dt>
                          <dd>{ev.provenance.original_source}</dd>
                        </div>
                      )}
                      {viewMode === "technical" && ev.raw_path && (
                        <div className="span-2">
                          <dt>Local Raw Artifact</dt>
                          <dd>
                            <code>{ev.raw_path}</code>
                          </dd>
                        </div>
                      )}
                      {viewMode === "technical" && ev.source_url && (
                        <div className="span-2">
                          <dt>Provider URL</dt>
                          <dd>
                            <a href={ev.source_url} target="_blank" rel="noreferrer">
                              {ev.source_url}
                            </a>
                          </dd>
                        </div>
                      )}
                      {viewMode === "technical" && ev.licence && (
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

      {/* Full-Width Interactive Visualisation Band: Domain-Independent Evidence Graph + Temporal Timeline */}
      <section className="visualisation-band" aria-label="Evidence graph and temporal integrity">
        <EvidenceGraphView graph={evidenceGraph} />

        <EvidenceTimeline
          claimedAt={claimedAt}
          assessmentMode={assessmentMode}
          decisionTime={decisionTime}
          assessedAt={assessedAtHeader}
          evidenceItems={activeEvidenceItems}
          assessment={assessment}
          policyWindowHours={domain === "galileo" ? 1 : 24}
          policyWindowNote={
            domain === "galileo"
              ? "1-hour navigation-message freshness policy window (demonstration parameter)"
              : "24-hour flood observation relevance window (demonstration policy — NOT a validated safety threshold)"
          }
          onModeChange={handleTemporalModeChange}
          onDecisionTimeChange={setDecisionTime}
        />
      </section>

      <footer className="disclaimer-footer">
        Evidence Integrity Platform (v0.5.0) — Independent evidence consistency, provenance graph &amp; cryptographic navigation-message verification infrastructure.
        Not a truth oracle, safety certification, positioning accuracy guarantee, or emergency routing service.
      </footer>
    </div>
  );
}
