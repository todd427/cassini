# Shared Agent Instructions (EIP v0.2)

Read [CONTRACT.md](CONTRACT.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/POLICY-DEVELOPMENT.md](docs/POLICY-DEVELOPMENT.md), and the archived hackathon brief in `cassini-briefs/PRD.md` before making changes.

## Architectural Boundaries
- **`core/` (Generic Evidence Engine):** MUST remain completely domain-independent. Never add flood-road rules, domain-specific claim literals, LLM calls, or numerical truth scores to `core/`.
- **`policies/` (Domain Assessment Policies):** All domain rules, thresholds, reason explanations, and claim-type validations belong in dedicated policy modules registered in `PolicyRegistry`.
- **`connectors/` (Evidence Connectors):** Implement `connectors.base.EvidenceConnector`. Preserve raw artefacts, SHA-256 digests, and honest provenance; never invent `observed_at`, `available_at`, `coverage`, or `authentication="verified"`.
- **`api/` (REST Interface):** Preserve Contract v0.1 backward compatibility on `/health`, `/v1/evidence`, and `/v1/assess` alongside v0.2 discovery endpoints (`/v1/capabilities`, `/v1/policies`).
- **`dashboard/` (Reference UI):** Keep offline-first operation, explicit `HISTORICAL REPLAY` / `SYNTHETIC INPUT` labels, explicit Mock Mode toggle, and no green "safe" verdicts.

## Engineering Discipline
- Use `~/dev/venvs/cassini` for the Python virtual environment.
- Never commit secrets, credentials, or generated build artefacts.
- Distinguish genuine provider evidence (`synthetic: false`), synthetic claims, and deterministic test fixtures (`synthetic: true`).
- Run `~/dev/venvs/cassini/bin/pytest -v tests/`, `cd dashboard && npm run build`, and Playwright E2E tests before committing.
- Never fabricate test outcomes, provenance metadata, or authentication claims.
