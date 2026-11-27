import type {
  AssessmentResponse,
  ClaimRequest,
  Evidence,
  EvidenceFinding,
  ReasonCode,
} from "../types/contract";

export interface ClaimPreset {
  id: string;
  label: string;
  description: string;
  claim: ClaimRequest;
}

export const CLAIM_PRESETS: ClaimPreset[] = [
  {
    id: "emsr718-intersect",
    label: "Lough Funshinagh — Flooded road (Potential Conflict)",
    description:
      "Synthetic historical replay road report crossing the eastern flooded basin of Lough Funshinagh (Co. Roscommon) ~2h after EMSR718 COSMO-SkyMed SAR acquisition.",
    claim: {
      claim_id: "emsr718-road-ballagh-east",
      claim_type: "road_passable",
      geometry: {
        type: "LineString",
        coordinates: [
          [-8.1165, 53.4916],
          [-8.1113, 53.4916],
          [-8.1075, 53.4916],
        ],
      },
      claimed_at: "2024-04-15T08:00:00Z",
      source_label: "Synthetic historical replay road report (Lough Funshinagh East)",
      synthetic: true,
    },
  },
  {
    id: "emsr718-covered-clear",
    label: "Lough Funshinagh — Covered road, no overlap (Not Proof of Safety)",
    description:
      "Synthetic road report inside EMSR718 AOI02 documented coverage south-west of Lough Funshinagh with no mapped flood intersection.",
    claim: {
      claim_id: "emsr718-road-rahara-south",
      claim_type: "road_passable",
      geometry: {
        type: "LineString",
        coordinates: [
          [-8.175, 53.462],
          [-8.155, 53.462],
        ],
      },
      claimed_at: "2024-04-15T08:00:00Z",
      source_label: "Synthetic historical replay road report (Rahara South, inside AOI02)",
      synthetic: true,
    },
  },
  {
    id: "emsr718-stale",
    label: "Lough Funshinagh — Stale observation >24h (Insufficient Evidence)",
    description:
      "Same flooded road segment queried 72 hours after satellite acquisition, exceeding the 24-hour demo policy window.",
    claim: {
      claim_id: "emsr718-road-stale-72h",
      claim_type: "road_passable",
      geometry: {
        type: "LineString",
        coordinates: [
          [-8.1165, 53.4916],
          [-8.1075, 53.4916],
        ],
      },
      claimed_at: "2024-04-18T06:02:08Z",
      source_label: "Synthetic historical replay road report (72h post-acquisition)",
      synthetic: true,
    },
  },
  {
    id: "emsr718-outside",
    label: "Athlone approach — Outside documented AOI (Insufficient Evidence)",
    description:
      "Synthetic road segment east of EMSR718 AOI02 boundary; documented coverage excludes this road.",
    claim: {
      claim_id: "emsr718-road-outside-aoi",
      claim_type: "road_passable",
      geometry: {
        type: "LineString",
        coordinates: [
          [-7.98, 53.43],
          [-7.95, 53.43],
        ],
      },
      claimed_at: "2024-04-15T08:00:00Z",
      source_label: "Synthetic historical replay road report (Outside AOI02 coverage)",
      synthetic: true,
    },
  },
];

/** Built-in mock evidence used ONLY when the user explicitly activates Mock Mode. */
export const MOCK_EVIDENCE_ITEMS: Evidence[] = [
  {
    id: "mock-emsr718-lough-funshinagh",
    source: "mock_fixture",
    product_id: "MOCK_EMSR718_AOI02_SIMPLIFIED",
    source_url: null,
    observed_at: "2024-04-15T06:02:08Z",
    retrieved_at: "2026-11-27T16:00:00Z",
    kind: "flood_extent",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [-8.1146, 53.4897],
          [-8.1095, 53.4897],
          [-8.1095, 53.4936],
          [-8.1146, 53.4936],
          [-8.1146, 53.4897],
        ],
      ],
    },
    coverage: {
      type: "Polygon",
      coordinates: [
        [
          [-8.234, 53.451],
          [-8.057, 53.451],
          [-8.057, 53.534],
          [-8.234, 53.534],
          [-8.234, 53.451],
        ],
      ],
    },
    authentication: "unknown",
    sha256: null,
    raw_path: null,
    licence: "Synthetic mock fixture (not real Copernicus geometry)",
    limitations: [
      "Mock mode active: simplified synthetic bounding polygon, not the genuine CEMS vector archive.",
    ],
    synthetic: true,
  },
];

function bboxOfRing(ring: number[][]): [number, number, number, number] {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const [x, y] of ring) {
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  }
  return [minX, minY, maxX, maxY];
}

function lineIntersectsBox(coords: number[][], box: [number, number, number, number]): boolean {
  const [minX, minY, maxX, maxY] = box;
  let lMinX = Infinity;
  let lMinY = Infinity;
  let lMaxX = -Infinity;
  let lMaxY = -Infinity;
  for (const [x, y] of coords) {
    if (x < lMinX) lMinX = x;
    if (y < lMinY) lMinY = y;
    if (x > lMaxX) lMaxX = x;
    if (y > lMaxY) lMaxY = y;
  }
  return lMaxX >= minX && lMinX <= maxX && lMaxY >= minY && lMinY <= maxY;
}

function lineInsideBox(coords: number[][], box: [number, number, number, number]): boolean {
  const [minX, minY, maxX, maxY] = box;
  return coords.every(([x, y]) => x >= minX && x <= maxX && y >= minY && y <= maxY);
}

/** Deterministic client-side mock assessment when Mock Mode is explicitly selected. */
export function runMockAssessment(
  claim: ClaimRequest,
  evidenceItems: Evidence[],
): AssessmentResponse {
  if (evidenceItems.length === 0) {
    return {
      claim_id: claim.claim_id,
      status: "insufficient_evidence",
      policy_version: "flood-road-0.1",
      reasons: ["NO_EVIDENCE"],
      evidence_ids: [],
      findings: [],
      limitations: [
        "Mock mode active with zero evidence items.",
        "Absence of evidence does not establish road passability or safety.",
      ],
      synthetic: true,
    };
  }

  const claimMs = Date.parse(claim.claimed_at);
  const findings: EvidenceFinding[] = evidenceItems.map((ev) => {
    if (ev.authentication === "failed") {
      return {
        evidence_id: ev.id,
        status: "insufficient_evidence",
        age_hours: ev.observed_at ? Math.abs(Date.parse(ev.observed_at) - claimMs) / 36e5 : null,
        reasons: ["AUTHENTICATION_FAILED"],
      };
    }
    if (!ev.observed_at) {
      return {
        evidence_id: ev.id,
        status: "insufficient_evidence",
        age_hours: null,
        reasons: ["OBSERVATION_TIME_UNKNOWN"],
      };
    }
    const ageHours = Number((Math.abs(Date.parse(ev.observed_at) - claimMs) / 36e5).toFixed(6));
    if (ageHours > 24) {
      return {
        evidence_id: ev.id,
        status: "insufficient_evidence",
        age_hours: ageHours,
        reasons: ["OBSERVATION_STALE"],
      };
    }
    const floodRing =
      ev.geometry.type === "Polygon" ? ev.geometry.coordinates[0] : ev.geometry.coordinates[0][0];
    const covRing =
      ev.coverage == null
        ? null
        : ev.coverage.type === "Polygon"
          ? ev.coverage.coordinates[0]
          : ev.coverage.coordinates[0][0];

    if (covRing && !lineIntersectsBox(claim.geometry.coordinates, bboxOfRing(covRing))) {
      return {
        evidence_id: ev.id,
        status: "insufficient_evidence",
        age_hours: ageHours,
        reasons: ["OUTSIDE_COVERAGE"],
      };
    }
    if (lineIntersectsBox(claim.geometry.coordinates, bboxOfRing(floodRing))) {
      return {
        evidence_id: ev.id,
        status: "potential_conflict",
        age_hours: ageHours,
        reasons: ["FLOOD_EXTENT_INTERSECTS"],
      };
    }
    if (!covRing) {
      return {
        evidence_id: ev.id,
        status: "insufficient_evidence",
        age_hours: ageHours,
        reasons: ["COVERAGE_UNKNOWN"],
      };
    }
    if (lineInsideBox(claim.geometry.coordinates, bboxOfRing(covRing))) {
      return {
        evidence_id: ev.id,
        status: "no_mapped_overlap",
        age_hours: ageHours,
        reasons: ["NO_MAPPED_OVERLAP"],
      };
    }
    return {
      evidence_id: ev.id,
      status: "insufficient_evidence",
      age_hours: ageHours,
      reasons: ["OUTSIDE_COVERAGE"],
    };
  });

  const status = findings.some((f) => f.status === "potential_conflict")
    ? "potential_conflict"
    : findings.some((f) => f.status === "no_mapped_overlap")
      ? "no_mapped_overlap"
      : "insufficient_evidence";

  const reasons: ReasonCode[] = [];
  for (const f of findings) {
    for (const r of f.reasons) {
      if (!reasons.includes(r)) reasons.push(r);
    }
  }

  return {
    claim_id: claim.claim_id,
    status,
    policy_version: "flood-road-0.1",
    reasons,
    evidence_ids: evidenceItems.map((e) => e.id),
    findings,
    limitations: [
      "Mock mode active: client-side preview using simplified synthetic geometry.",
      status === "potential_conflict"
        ? "Mapped flood overlap does not establish road impassability."
        : "Absence of mapped flood overlap does not establish road passability or safety.",
      "Evidence authenticity is unknown (unverified).",
    ],
    synthetic: true,
  };
}
