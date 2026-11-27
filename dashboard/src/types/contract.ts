export type AuthenticationStatus = "unknown" | "verified" | "failed";

export type AssessmentStatus =
  | "potential_conflict"
  | "no_mapped_overlap"
  | "insufficient_evidence";

export type ReasonCode =
  | "FLOOD_EXTENT_INTERSECTS"
  | "NO_MAPPED_OVERLAP"
  | "OBSERVATION_STALE"
  | "OBSERVATION_TIME_UNKNOWN"
  | "COVERAGE_UNKNOWN"
  | "OUTSIDE_COVERAGE"
  | "NO_EVIDENCE"
  | "AUTHENTICATION_FAILED";

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

export interface Evidence {
  id: string;
  source: string;
  product_id: string | null;
  source_url: string | null;
  observed_at: string | null;
  retrieved_at: string | null;
  kind: "flood_extent";
  geometry: FloodGeometry;
  coverage: FloodGeometry | null;
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
  status: AssessmentStatus;
  age_hours: number | null;
  reasons: ReasonCode[];
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
    summary: "Mapped flood extent intersects the claimed road segment within the 24-hour policy window.",
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
    summary: "Available observations cannot establish or rule out flood overlap for this claim.",
    caution: "Never infer absence of flooding or safety from stale, missing, or out-of-coverage evidence.",
    tone: "muted",
  },
};

export const REASON_EXPLANATIONS: Record<ReasonCode, string> = {
  FLOOD_EXTENT_INTERSECTS:
    "Qualifying flood extent polygon intersects the claimed road LineString within 24 hours.",
  NO_MAPPED_OVERLAP:
    "Fresh observation with documented coverage enclosing the entire road segment shows no mapped flood intersection.",
  OBSERVATION_STALE:
    "Time difference between satellite acquisition and claimed time exceeds the 24-hour demo policy window.",
  OBSERVATION_TIME_UNKNOWN:
    "Evidence record has no documented acquisition timestamp (observed_at is null).",
  COVERAGE_UNKNOWN:
    "No documented observation coverage polygon is available, so a negative finding cannot be made.",
  OUTSIDE_COVERAGE:
    "Part or all of the claimed road segment lies outside documented observation coverage.",
  NO_EVIDENCE:
    "No evidence records are loaded in the active evidence store.",
  AUTHENTICATION_FAILED:
    "Evidence item failed authentication verification and was excluded from conflict determination.",
};
