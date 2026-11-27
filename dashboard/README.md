# Evidence Inspector Dashboard (`dashboard/`)

React + TypeScript + Vite + MapLibre GL JS reference UI for the Evidence Integrity Platform (Contract `v0.1`).

## Features

- Offline-first MapLibre GL JS vector canvas (WGS84 reference grid fallback, zero API keys required; optional online OSM basemap toggle).
- Explicit **HISTORICAL REPLAY** and **SYNTHETIC INPUT** labels.
- Live API connection via `VITE_API_BASE_URL` (default `http://localhost:8000`) plus explicit **Mock Mode** toggle (never silently falls back to mock).
- Sober status design with no green "safe" verdict (`Potential conflict`, `No mapped overlap — not proof of safety`, `Insufficient evidence`).
- Full provenance display (product ID, provider URL, timestamps + signed offset, SHA-256 local integrity digest, licence, limitations).

## Run & Test

```bash
cd dashboard
npm install
npm run dev -- --host 127.0.0.1
npm run build

# End-to-end Playwright tests (with API running on 127.0.0.1:8000 and Vite on 127.0.0.1:5173)
npx playwright test
```
