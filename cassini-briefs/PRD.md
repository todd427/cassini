# Evidence Integrity Platform (EIP)
## CASSINI 12 | Hackathon PRD v0.1 | 27 November 2026

**Status:** proposed for team agreement. EIP is a working label, not a cleared brand. Primary entry proposed: Challenge 2, civil resilience; confirm official challenge wording, eligibility, AI usage, submission deadline and IP terms with organisers.

## 1. Product and purpose
A reusable API for assessing geographically and temporally scoped claims against independent evidence. One reference application, Evidence Inspector, demonstrates the API. Target users are developers, emergency planners and analysts; eventual customers include authorities, utilities, insurers and logistics providers. The platform is not a truth oracle, safety certification or emergency routing service.

**Weekend use case:** assess a report that a road segment was passable at a specified time during a historical flood. Overlay a genuine Copernicus flood product and explain whether observed flooding is consistent with the report. An overlap is a potential conflict, not proof of impassability; absence of mapped flooding is not proof of safety. Use an explicitly synthetic report if no licensed historical report exists. Clearly label historical replay and synthetic inputs.

**Space contribution:** Copernicus supplies independent Earth observations with spatial and temporal metadata. Galileo OSNMA is a stretch connector using recorded or compatible live receiver data; it authenticates navigation messages, not the user's location or arbitrary reports. No need for new ESA infrastructure.

## 2. Scope and requirements
P0: import one genuine processed Copernicus flood extent dataset; provenance and checksums; structured claim input (GeoJSON road segment, observation time, claim type); deterministic spatial/temporal assessment; REST API; single map dashboard; replayable offline demo; automated tests; concise pitch.
P1: second real evidence source, STAC discovery, recorded OSNMA demonstration, alternate scenario using the same API. P2: multi-tenancy, billing, production security, live alerts, mobile, SDK, additional claim types. No LLM required; free-text interpretation is out of scope.

## 3. Architecture
Connectors → versioned evidence JSON + local GeoJSON → FastAPI/Pydantic → deterministic assessment (Shapely/pyproj) → React/TypeScript/MapLibre dashboard. SQLite optional; file-backed immutable fixtures suffice. Python 3.12, Node 22 LTS or installed compatible LTS, npm, pytest, Playwright. WSL Ubuntu on Lava; no GPU. Bind local services to localhost; no public deployment needed. Keep secrets in environment variables, never commit them. See CONTRACT.md for authoritative interface.

## 4. Data and assessment
Obtain a documented CEMS Rapid Mapping flood extent via https://mapping.emergency.copernicus.eu/ or https://dataspace.copernicus.eu/. STAC documentation: https://documentation.dataspace.copernicus.eu/APIs/STAC.html. Ask mentors for a suitable historical Irish event with usable vector flood extent and observation timestamps. Storm Éowyn is a candidate only if relevant verified flood products exist; otherwise select another event. Record event/product ID, source URL, acquisition time, retrieval time, licence/attribution, geometry, coverage, known limitations and SHA-256 of raw artifact. Never invent missing metadata. Do not equate catalogue footprint with flood extent. If coverage is unavailable, no negative finding is possible. Use WGS84 GeoJSON; validate geometry; use suitable projected CRS for metric distances if needed. No numerical truth probability.

Assessment logic: qualifying flood extent intersects road segment and time difference is within configured 24 hours → potential_conflict; stale observations or observations outside valid coverage → insufficient_evidence; non-intersection with documented coverage → no_mapped_overlap (not corroboration of passability). Unknown acquisition time → insufficient_evidence. Evidence authenticity remains unknown unless independently verified; checksum proves local byte integrity only. Sources derived from the same observation are not independent. Never infer absence of flooding from missing evidence. Always include reason codes, timestamps, limitations and evidence links. 24h is a demo policy, not operational safety guidance.

## 5. Acceptance and evaluation
- Real product provenance traceable to provider, original artefact hash reproducible.
- Three deterministic fixtures: intersecting recent flood, non-overlapping covered road, stale/missing evidence. Add outside coverage, invalid geometry and unknown observation time cases.
- API validates malformed input (422); identical inputs and same evidence/policy version yield identical assessment status/reasons.
- Dashboard submits a claim, shows claim geometry, actual flood geometry, timestamps, source and limitations; no green 'safe' verdict.
- Historical/synthetic labels visible; local replay works without remote data API or map tiles (plain map background acceptable).
- Record pass/fail for labelled fixtures. These test rule behaviour, not real-world predictive accuracy. No efficacy or market claims without evidence.

## 6. Build schedule (Irish local time, provisional)
| Target | Milestone |
|---|---|
| Fri 16:00–17:00 | Confirm team/rules, freeze contract, choose event and assign roles |
| Fri 17:00–20:00 | Parallel connectors, engine, UI against fixtures |
| Fri 20:00–22:00 | First integration with mock data; confirm real product availability |
| Sat 09:00–11:00 | Real data import and end-to-end integration |
| Sat 11:00–14:00 | Complete assessment and map UX |
| Sat 14:00–17:00 | Independent tests, data provenance, failure modes |
| Sat 17:00–20:00 | Pitch, demo recording, feature freeze |
| Sun 09:00–11:00 | Regression, rehearsal and submission buffer |
Adjust to confirmed organiser timetable. No overnight work required. If data access fails, use a previously obtained documented public product; if none is available, label synthetic prototype and disclose missing real space integration. Cut OSNMA first.

## 7. Team and workflow
Solo: human architect/integrator; Claude data, Codex core, Antigravity UI. Three humans: one per workstream, share QA/pitch. Four: fourth owns independent validation, customer discovery and pitch. Use separate Git worktrees and branches; commit contract on main first; merge data/core/UI after tests; human approves merges, no agent changes contract unilaterally. Shared AGENTS.md is authoritative. Use separate ports if parallel servers. No credentials in logs or repo.

## 8. Commercial roadmap
API licensing/usage-based assessments and enterprise deployment are hypotheses. First design partner: local authority or infrastructure operator; validate procurement, data licensing, risk and willingness to pay. Weeks 1–2: reliable connectors and API; weeks 3–4: SDK and documentation; months 2–3: pilot with measured utility; months 4–6: security, access control, audit and beta. No production emergency use until validated and approved. Cross-sector expansion via connectors and policy modules, not three weekend products.

## 9. Pitch
Problem: consequential decisions rely on fragmented, stale or conflicting information. Solution: independent evidence assessment as a reusable API. Demo: a historical road report compared with Copernicus flood extent. Show what is known, what is not, and why. Impact: better calibrated trust. Ask: design partners and access to validated datasets.
