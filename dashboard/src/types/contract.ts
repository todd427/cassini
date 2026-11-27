export type AuthenticationStatus = "unknown" | "verified" | "failed";

export type AssessmentStatus =
  | "potential_conflict"
  | "no_mapped_overlap"
  | "insufficient_evidence";

export type ReasonCode =
  | "FLOOD_EXTENT_INTERSECTS"
  | "NO_MAPPED_OVERLAP"
  | "CONTEXTUAL_WATER_LEVEL_ELEVATED"
  | "CONTEXTUAL_WATER_LEVEL_NORMAL"
  | "CONTEXTUAL_RAINFALL_OBSERVED"
  | "CONTEXTUAL_RAINFALL_LOW"
  | "INDIRECT_EVIDENCE_ONLY"
  | "OBSERVATION_STALE"
  | "OBSERVATION_TIME_UNKNOWN"
  | "COVERAGE_UNKNOWN"
  | "OUTSIDE_COVERAGE"
  | "NO_EVIDENCE"
  | "AUTHENTICATION_FAILED"
  | "NOT_AVAILABLE_AT_DECISION_TIME"
  | "AVAILABILITY_TIME_UNKNOWN"
  | string;

export interface PointGeometry {
  type: "Point";
  coordinates: number[];
}

export interface LineStringGeometry {
  type: "LineString";
  coordinates: number[][];
}

export interface PolygonGeometry {
  type: "Polygon";
  coordinates: number[][][];
}

export interface MultiPolygonGeometry {
  type: "MultiPolygon";
  coordinates: number[][][][];
}

export type FloodGeometry = PolygonGeometry | MultiPolygonGeometry;
export type EvidenceGeometry = PointGeometry | LineStringGeometry | FloodGeometry;

export interface SourceProvenance {
  original_source: string | null;
  publishing_organisation: string | null;
  upstream_datasets: string[];
  derived_from: string[];
  measurement_method: string | null;
  shared_dependencies: string[];
}

export interface Evidence {
  id: string;
  source: string;
  product_id: string | null;
  source_url: string | null;
  observed_at: string | null;
  available_at?: string | null;
  retrieved_at: string | null;
  kind: string;
  geometry: EvidenceGeometry | null;
  coverage: FloodGeometry | null;
  attributes?: Record<string, unknown>;
  provenance?: SourceProvenance | null;
  authentication: AuthenticationStatus;
  sha256: string | null;
  raw_path: string | null;
  licence: string | null;
  limitations: string[];
  synthetic: boolean;
}

export interface ClaimRequest {
  claim_id: string;
  claim_type: "road_passable";
  geometry: LineStringGeometry;
  claimed_at: string;
  source_label: string;
  synthetic: boolean;
}

export interface EvidenceFinding {
  evidence_id: string;
  status: string;
  age_hours: number | null;
  reasons: ReasonCode[];
}

export interface IndependenceSummary {
  status:
    | "single_source"
    | "shared_dependencies_detected"
    | "distinct_declared_sources"
    | "unknown";
  assessed_source_count: number;
  independent_group_count: number | null;
  correlated_groups: string[][];
  shared_dependencies: string[];
  notes: string[];
}

export interface TemporalContext {
  assessment_mode: "retrospective" | "decision_time";
  claimed_at: string;
  decision_time: string | null;
  assessed_at: string | null;
  excluded_not_available_ids: string[];
  unknown_availability_ids: string[];
}

export interface AssessmentResponse {
  claim_id: string;
  status: AssessmentStatus;
  policy_version: string;
  reasons: ReasonCode[];
  evidence_ids: string[];
  findings: EvidenceFinding[];
  limitations: string[];
  synthetic: boolean;
  assessment_mode?: "retrospective" | "decision_time";
  temporal_context?: TemporalContext | null;
  independence?: IndependenceSummary | null;
}

export interface EvidenceListResponse {
  items: Evidence[];
}

export interface HealthResponse {
  status: "ok";
  contract_version: string;
}

export const STATUS_META: Record<
  AssessmentStatus,
  { label: string; summary: string; caution: string; tone: "conflict" | "neutral" | "muted" }
> = {
  potential_conflict: {
    label: "Potential conflict",
    summary: "Direct mapped flood extent intersects the claimed road segment within the 24-hour policy window.",
    caution: "An overlap is a potential conflict, NOT proof of road impassability.",
    tone: "conflict",
  },
  no_mapped_overlap: {
    label: "No mapped overlap",
    summary: "Entire road segment lies within documented observation coverage with no mapped flood intersection.",
    caution: "Not proof of safety or road passability. Floods under canopy, bridges, or after acquisition may not appear.",
    tone: "neutral",
  },
  insufficient_evidence: {
    label: "Insufficient evidence",
    summary: "Available observations cannot establish or rule out direct flood overlap for this claim.",
    caution: "Never infer absence of flooding or safety from stale, missing, indirect-only, or out-of-coverage evidence.",
    tone: "muted",
  },
};

export const INDEPENDENCE_LABELS: Record<IndependenceSummary["status"], string> = {
  distinct_declared_sources: "Distinct declared sources",
  shared_dependencies_detected: "Shared dependencies detected (correlated)",
  single_source: "Single source",
  unknown: "Unknown independence",
};

export const REASON_EXPLANATIONS: Record<string, string> = {
  FLOOD_EXTENT_INTERSECTS:
    "Qualifying direct flood extent polygon intersects the claimed road LineString within 24 hours.",
  NO_MAPPED_OVERLAP:
    "Fresh direct observation with documented coverage enclosing the entire road segment shows no mapped flood intersection.",
  CONTEXTUAL_WATER_LEVEL_ELEVATED:
    "Independent in-situ hydrometric gauge recorded elevated water level (>= historical 95th percentile); indirect context only, not direct proof of road flooding.",
  CONTEXTUAL_WATER_LEVEL_NORMAL:
    "Nearby hydrometric gauge recorded water level below historical 95th percentile; indirect context only, not proof of safety.",
  CONTEXTUAL_RAINFALL_OBSERVED:
    "Independent regional weather station recorded notable precipitation; indirect environmental context only, not direct proof of road flooding.",
  CONTEXTUAL_RAINFALL_LOW:
    "Regional weather station recorded low/zero precipitation; indirect context only, not proof of safety.",
  INDIRECT_EVIDENCE_ONLY:
    "Only indirect contextual observations qualified; direct spatial flood observation is required to assess road-segment overlap.",
  OBSERVATION_STALE:
    "Time difference between observation and claimed time exceeds the 24-hour demo policy window.",
  OBSERVATION_TIME_UNKNOWN:
    "Evidence record has no documented observation timestamp (observed_at is null).",
  COVERAGE_UNKNOWN:
    "No documented observation coverage polygon is available, so a negative finding cannot be made.",
  OUTSIDE_COVERAGE:
    "Part or all of the claimed road segment lies outside documented observation coverage or station relevance radius.",
  NO_EVIDENCE:
    "No evidence records are loaded in the active evidence store.",
  AUTHENTICATION_FAILED:
    "Evidence item failed authentication verification and was excluded from conflict determination.",
  NOT_AVAILABLE_AT_DECISION_TIME:
    "Evidence was observed or became available after the specified decision_time.",
  AVAILABILITY_TIME_UNKNOWN:
    "Evidence lacks a documented availability/publication timestamp (available_at is null) for decision-time verification.",
};
