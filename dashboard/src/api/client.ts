import type {
  AssessmentResponse,
  ClaimRequest,
  EvidenceListResponse,
  HealthResponse,
} from "../types/contract";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
).replace(/\/+$/, "");

export class ApiError extends Error {
  status: number;
  details: string[];

  constructor(message: string, status: number, details: string[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

async function parseErrorResponse(res: Response): Promise<ApiError> {
  const details: string[] = [];
  let message = `API request failed (HTTP ${res.status})`;
  try {
    const body = await res.json();
    if (Array.isArray(body?.detail)) {
      for (const item of body.detail) {
        const loc = Array.isArray(item.loc) ? item.loc.join(".") : "";
        const msg = item.msg || JSON.stringify(item);
        details.push(loc ? `${loc}: ${msg}` : msg);
      }
      message = `Validation error (HTTP ${res.status})`;
    } else if (typeof body?.detail === "string") {
      message = body.detail;
    }
  } catch {
    // non-JSON response body
  }
  return new ApiError(message, res.status, details);
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE_URL}/health`, { signal });
  if (!res.ok) throw await parseErrorResponse(res);
  return (await res.json()) as HealthResponse;
}

export async function fetchEvidence(signal?: AbortSignal): Promise<EvidenceListResponse> {
  const res = await fetch(`${API_BASE_URL}/v1/evidence`, { signal });
  if (!res.ok) throw await parseErrorResponse(res);
  return (await res.json()) as EvidenceListResponse;
}

export async function submitAssessment(
  payload: ClaimRequest | Record<string, unknown>,
  signal?: AbortSignal,
): Promise<AssessmentResponse> {
  const res = await fetch(`${API_BASE_URL}/v1/assess`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) throw await parseErrorResponse(res);
  return (await res.json()) as AssessmentResponse;
}
