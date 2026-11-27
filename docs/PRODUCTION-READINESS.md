# EIP Enterprise Production Readiness Boundaries (v0.6.0)

EIP v0.6.0 is a **verified local architectural reference implementation and developer SDK** demonstrating deterministic, domain-independent evidence assessment. It is **not** production-hardened cloud software.

This document explicitly identifies the engineering, security, operational, and scientific requirements that must be implemented before deploying EIP in a production enterprise environment. None of the production controls listed below are implemented in v0.6.0.

---

## 1. API Authentication and Authorisation
- **Current state (v0.6.0):** Local unauthenticated HTTP server (`127.0.0.1:8000`) with CORS restricted to localhost UI origins.
- **Required for production:**
  - TLS 1.3 termination (mTLS or HTTPS via reverse proxy / API gateway).
  - Enterprise authentication (OAuth 2.0 / OIDC JWTs or mTLS service certificates; scoped API keys only for machine-to-machine pipelines with rotation).
  - Role-Based / Attribute-Based Access Control (RBAC/ABAC) separating read-only discovery, claim assessment, evidence ingestion, and policy administration.

## 2. Tenant Isolation
- **Current state (v0.6.0):** Single shared in-process `EvidenceStore` (`sample_data/evidence.json`) and single `PolicyRegistry`.
- **Required for production:**
  - Strict tenant scoping on evidence stores, assessment logs, custom policies, and cryptographic trust anchors (separate schemas/databases or row-level security with enforced tenant claims from verified tokens).
  - Explicit separation between shared public reference datasets (e.g., Copernicus EMS) and private tenant-submitted evidence or claims.

## 3. Rate Limiting and Resource Quotas
- **Current state (v0.6.0):** No rate limiting, payload size caps, or concurrency quotas.
- **Required for production:**
  - Per-tenant / per-client request rate limiting (`429 Too Many Requests`) and request body size limits (especially for large GeoJSON polygons or binary GNSS streams).
  - CPU/memory execution timeouts on spatial intersection operations and cryptographic verification endpoints to prevent algorithmic complexity DoS.

## 4. Audit Logging and Non-Repudiation
- **Current state (v0.6.0):** Stateless deterministic `input_fingerprint` (SHA-256) and `X-EIP-Assessed-At` header; no persistent server-side audit log.
- **Required for production:**
  - Append-only, tamper-evident structured audit logs recording caller identity, timestamp, `claim_id`, `policy_id` / `policy_version`, `input_fingerprint`, `evidence_ids`, `status`, and response latency.
  - Separation of operational telemetry logs from sensitive claim payloads (PII/location redaction where required).

## 5. Data Retention and Deletion
- **Current state (v0.6.0):** Local JSON/raw files retained indefinitely on disk.
- **Required for production:**
  - Configurable retention policies per tenant and data classification (GDPR / regulatory compliance for geospatial track claims or personal claim references).
  - Cryptographic erasure or verifiable deletion workflows for customer claims while preserving immutable policy definitions and public reference provenance needed for statutory audits.

## 6. Evidence Licensing and Attribution Governance
- **Current state (v0.6.0):** Openly licensed datasets (Copernicus EMS, GSI CC BY 4.0, Met Éireann CC BY 4.0, GSC/OSNMAlib EUPL-1.2) carry free-text `licence` metadata.
- **Required for production:**
  - Machine-readable licence enforcement (e.g., SPDX identifiers and commercial redistribution flags) preventing non-commercial or restricted third-party feeds from being mixed into commercial workflows without authorisation.
  - Automated attribution propagation into downstream enterprise reports.

## 7. Connector Monitoring and Data Pipeline Operations
- **Current state (v0.6.0):** Offline batch connectors run manually against preserved local artifacts.
- **Required for production:**
  - Scheduled ingestion pipelines with connector health checks, schema drift alerts, upstream API outage handling, freshness SLA monitoring, and dead-letter queues.
  - Accurate capture of genuine `available_at` publication timestamps at ingestion time (eliminating `available_at = null` ambiguity for live decision-time auditing).
  - Cryptographic verification of upstream artifacts on ingestion where providers support signatures or trusted digests.

## 8. Policy Governance and Versioning
- **Current state (v0.6.0):** Policies are Python modules registered at startup in `PolicyRegistry`.
- **Required for production:**
  - Formal change-control workflow, peer review, and immutable semantic versioning of `policy_version` so historical assessments remain reproducible years later.
  - Shadow-mode / canary evaluation when introducing revised thresholds, plus signed policy release registries and clear deprecation lifecycles.

## 9. Service Availability, Scaling, and Recovery
- **Current state (v0.6.0):** Single-process `uvicorn` server backed by local JSON files.
- **Required for production:**
  - Stateless horizontal replicas behind a load balancer, backed by durable spatial/document storage (e.g., PostgreSQL/PostGIS + object storage for raw artifacts).
  - Automated backups, documented RTO/RPO targets, readiness/liveness probes distinguishing API liveness from evidence-store health, and graceful degradation without ever fabricating evidence.

## 10. Independent Security Assessment
- **Current state (v0.6.0):** Internal unit/integration tests and static boundary checks only.
- **Required for production:**
  - Independent third-party penetration testing, dependency vulnerability scanning (SBOM + CVE monitoring for Python/Node/native geospatial libraries like GEOS/Shapely), and formal cryptographic review of the Galileo OSNMA verification implementation and GSC trust-anchor key rotation lifecycle.

## 11. Domain-Specific Scientific and Operational Validation
- **Current state (v0.6.0):** Policy parameters (e.g., 24-hour flood window, 1-hour GNSS window, hydrometric/rainfall contextual thresholds) are explicitly labelled as **demonstration policies**, not validated operational or safety thresholds.
- **Required for production:**
  - Domain expert calibration and empirical validation (hydrologists, civil protection agencies, GNSS timing engineers, actuaries) against regional failure modes, false-negative rates (e.g., SAR flooding under tree canopy or urban radar shadow), and real-time GNSS spoofing/meaconing threat models.
  - Human-in-the-loop governance ensuring EIP outputs inform—rather than solely automate—high-consequence legal, financial, or life-safety decisions.
