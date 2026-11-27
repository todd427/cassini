import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type GeoJSONSource, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type {
  AssessmentStatus,
  Evidence,
  LineStringGeometry,
  LocalMapContext,
} from "../types/contract";

interface EvidenceMapProps {
  evidenceItems: Evidence[];
  claimGeometry: LineStringGeometry | null;
  assessmentStatus: AssessmentStatus | null;
  localContext: LocalMapContext | null;
  onCustomRoadChange?: (geom: LineStringGeometry) => void;
}

type BoundsTuple = [[number, number], [number, number]];

function buildGraticule(): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (let lon = -11; lon <= -5; lon += 0.05) {
    features.push({
      type: "Feature",
      properties: { axis: "lon" },
      geometry: {
        type: "LineString",
        coordinates: [
          [Number(lon.toFixed(2)), 51.0],
          [Number(lon.toFixed(2)), 56.0],
        ],
      },
    });
  }
  for (let lat = 51; lat <= 56; lat += 0.05) {
    features.push({
      type: "Feature",
      properties: { axis: "lat" },
      geometry: {
        type: "LineString",
        coordinates: [
          [-11.0, Number(lat.toFixed(2))],
          [-5.0, Number(lat.toFixed(2))],
        ],
      },
    });
  }
  return { type: "FeatureCollection", features };
}

function buildOfflineStyle(enableOsmTiles: boolean): StyleSpecification {
  const sources: StyleSpecification["sources"] = {
    graticule: {
      type: "geojson",
      data: buildGraticule(),
    },
    "baseline-water": {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    },
    coverage: {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    },
    flood: {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    },
    stations: {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    },
    claim: {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    },
    "claim-endpoints": {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    },
    "draw-draft": {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    },
  };

  const layers: StyleSpecification["layers"] = [
    {
      id: "canvas-bg",
      type: "background",
      paint: { "background-color": "#0d1520" },
    },
  ];

  if (enableOsmTiles) {
    sources["osm-raster"] = {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    };
    layers.push({
      id: "osm-basemap",
      type: "raster",
      source: "osm-raster",
      paint: {
        "raster-opacity": 0.42,
        "raster-saturation": -0.75,
        "raster-brightness-max": 0.72,
      },
    });
  }

  layers.push(
    {
      id: "graticule-lines",
      type: "line",
      source: "graticule",
      paint: {
        "line-color": "#1e2e42",
        "line-width": 1,
        "line-opacity": enableOsmTiles ? 0.25 : 0.7,
      },
    },
    {
      id: "coverage-fill",
      type: "fill",
      source: "coverage",
      paint: {
        "fill-color": "#64748b",
        "fill-opacity": 0.11,
      },
    },
    {
      id: "coverage-outline",
      type: "line",
      source: "coverage",
      paint: {
        "line-color": "#94a3b8",
        "line-width": 1.75,
        "line-dasharray": [4, 3],
      },
    },
    {
      id: "baseline-water-fill",
      type: "fill",
      source: "baseline-water",
      paint: {
        "fill-color": "#1e3a5f",
        "fill-opacity": 0.52,
      },
    },
    {
      id: "baseline-water-outline",
      type: "line",
      source: "baseline-water",
      paint: {
        "line-color": "#3b82f6",
        "line-width": 1.1,
        "line-opacity": 0.65,
      },
    },
    {
      id: "flood-fill",
      type: "fill",
      source: "flood",
      paint: {
        "fill-color": "#0ea5e9",
        "fill-opacity": 0.5,
      },
    },
    {
      id: "flood-outline",
      type: "line",
      source: "flood",
      paint: {
        "line-color": "#38bdf8",
        "line-width": 1.6,
      },
    },
    {
      id: "station-points",
      type: "circle",
      source: "stations",
      paint: {
        "circle-radius": 6,
        "circle-color": "#c084fc",
        "circle-stroke-color": "#0b111b",
        "circle-stroke-width": 2,
      },
    },
    {
      id: "claim-casing",
      type: "line",
      source: "claim",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": "#0b111b",
        "line-width": 7,
      },
    },
    {
      id: "claim-line",
      type: "line",
      source: "claim",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": "#f59e0b",
        "line-width": 3.5,
      },
    },
    {
      id: "claim-endpoints-layer",
      type: "circle",
      source: "claim-endpoints",
      paint: {
        "circle-radius": 5,
        "circle-color": "#f8fafc",
        "circle-stroke-color": "#0b111b",
        "circle-stroke-width": 2,
      },
    },
    {
      id: "draw-draft-points",
      type: "circle",
      source: "draw-draft",
      paint: {
        "circle-radius": 6,
        "circle-color": "#f59e0b",
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 2,
      },
    },
  );

  return {
    version: 8,
    sources,
    layers,
  };
}

function extendBounds(coords: unknown, acc: [number, number, number, number]): void {
  if (!Array.isArray(coords) || coords.length === 0) return;
  if (typeof coords[0] === "number" && typeof coords[1] === "number") {
    const lon = coords[0];
    const lat = coords[1];
    if (lon < acc[0]) acc[0] = lon;
    if (lat < acc[1]) acc[1] = lat;
    if (lon > acc[2]) acc[2] = lon;
    if (lat > acc[3]) acc[3] = lat;
    return;
  }
  for (const child of coords) {
    extendBounds(child, acc);
  }
}

function computeBounds(geometries: Array<{ coordinates: unknown }>): BoundsTuple | null {
  const acc: [number, number, number, number] = [Infinity, Infinity, -Infinity, -Infinity];
  for (const g of geometries) {
    extendBounds(g.coordinates, acc);
  }
  if (!Number.isFinite(acc[0])) return null;
  const padX = Math.max((acc[2] - acc[0]) * 0.25, 0.008);
  const padY = Math.max((acc[3] - acc[1]) * 0.25, 0.005);
  return [
    [acc[0] - padX, acc[1] - padY],
    [acc[2] + padX, acc[3] + padY],
  ];
}

export function EvidenceMap({
  evidenceItems,
  claimGeometry,
  assessmentStatus,
  localContext,
  onCustomRoadChange,
}: EvidenceMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState<string | null>(null);
  const [showFlood, setShowFlood] = useState(true);
  const [showCoverage, setShowCoverage] = useState(true);
  const [showContext, setShowContext] = useState(true);
  const [useOsmTiles, setUseOsmTiles] = useState(false);
  const [tileNotice, setTileNotice] = useState<string | null>(null);

  // Interactive 2-click road drawing state
  const [drawingMode, setDrawingMode] = useState(false);
  const [draftStart, setDraftStart] = useState<[number, number] | null>(null);
  const drawingModeRef = useRef(drawingMode);
  const draftStartRef = useRef(draftStart);
  const onCustomRoadChangeRef = useRef(onCustomRoadChange);

  useEffect(() => {
    drawingModeRef.current = drawingMode;
  }, [drawingMode]);
  useEffect(() => {
    draftStartRef.current = draftStart;
  }, [draftStart]);
  useEffect(() => {
    onCustomRoadChangeRef.current = onCustomRoadChange;
  }, [onCustomRoadChange]);

  const floodGeoJson = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features: evidenceItems
        .filter(
          (ev) =>
            ev.geometry !== null &&
            (ev.geometry.type === "Polygon" || ev.geometry.type === "MultiPolygon"),
        )
        .map((ev) => ({
          type: "Feature",
          properties: { id: ev.id, product_id: ev.product_id ?? ev.id },
          geometry: ev.geometry as GeoJSON.Polygon | GeoJSON.MultiPolygon,
        })),
    }),
    [evidenceItems],
  );

  const stationsGeoJson = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features: evidenceItems
        .filter((ev) => ev.geometry !== null && ev.geometry.type === "Point")
        .map((ev) => ({
          type: "Feature",
          properties: {
            id: ev.id,
            kind: ev.kind,
            label: ev.product_id ?? ev.id,
          },
          geometry: ev.geometry as GeoJSON.Point,
        })),
    }),
    [evidenceItems],
  );

  const coverageGeoJson = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features: evidenceItems
        .filter((ev) => ev.coverage !== null)
        .map((ev) => ({
          type: "Feature",
          properties: { id: ev.id },
          geometry: ev.coverage!,
        })),
    }),
    [evidenceItems],
  );

  const baselineWaterGeoJson = useMemo<GeoJSON.FeatureCollection>(
    () =>
      localContext?.baseline_water_extent ?? {
        type: "FeatureCollection",
        features: [],
      },
    [localContext],
  );

  const claimGeoJson = useMemo<GeoJSON.FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features: claimGeometry
        ? [{ type: "Feature", properties: { role: "claim" }, geometry: claimGeometry }]
        : [],
    }),
    [claimGeometry],
  );

  const endpointGeoJson = useMemo<GeoJSON.FeatureCollection>(() => {
    if (!claimGeometry || claimGeometry.coordinates.length === 0) {
      return { type: "FeatureCollection", features: [] };
    }
    const pts = [
      claimGeometry.coordinates[0],
      claimGeometry.coordinates[claimGeometry.coordinates.length - 1],
    ];
    return {
      type: "FeatureCollection",
      features: pts.map((coord, idx) => ({
        type: "Feature",
        properties: { index: idx },
        geometry: { type: "Point", coordinates: coord },
      })),
    };
  }, [claimGeometry]);

  const draftGeoJson = useMemo<GeoJSON.FeatureCollection>(() => {
    if (!draftStart) return { type: "FeatureCollection", features: [] };
    return {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { role: "draft-start" },
          geometry: { type: "Point", coordinates: draftStart },
        },
      ],
    };
  }, [draftStart]);

  // Extract concise indirect contextual telemetry for display bar
  const gsiItem = useMemo(
    () => evidenceItems.find((e) => e.kind === "hydrometric_water_level") ?? null,
    [evidenceItems],
  );
  const metItem = useMemo(
    () => evidenceItems.find((e) => e.kind === "meteorological_rainfall") ?? null,
    [evidenceItems],
  );

  // Deliberately avoid green "safe" color for any status
  const claimColor =
    assessmentStatus === "potential_conflict"
      ? "#f97316"
      : assessmentStatus === "no_mapped_overlap"
        ? "#e2e8f0"
        : "#f59e0b";

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    setMapError(null);
    setTileNotice(null);

    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container,
        style: buildOfflineStyle(useOsmTiles),
        center: [-8.13, 53.495],
        zoom: 11.5,
        attributionControl: false,
      });
    } catch (err) {
      setMapError(
        err instanceof Error
          ? `Map canvas unavailable (${err.message}). Geometry coordinates remain inspectable in the panels.`
          : "Map canvas unavailable in this browser context.",
      );
      return;
    }

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    map.on("load", () => {
      setMapReady(true);
    });

    map.on("click", (evt) => {
      if (!drawingModeRef.current || !onCustomRoadChangeRef.current) return;
      const pt: [number, number] = [
        Number(evt.lngLat.lng.toFixed(5)),
        Number(evt.lngLat.lat.toFixed(5)),
      ];
      if (!draftStartRef.current) {
        setDraftStart(pt);
      } else {
        const geom: LineStringGeometry = {
          type: "LineString",
          coordinates: [draftStartRef.current, pt],
        };
        setDraftStart(null);
        setDrawingMode(false);
        onCustomRoadChangeRef.current(geom);
      }
    });

    map.on("error", (evt) => {
      if (useOsmTiles) {
        setTileNotice("Remote basemap tiles unavailable — displaying offline vector grid fallback.");
      } else if (evt?.error?.message) {
        setTileNotice(`Map notice: ${evt.error.message}`);
      }
    });

    mapRef.current = map;
    return () => {
      for (const m of markersRef.current) m.remove();
      markersRef.current = [];
      setMapReady(false);
      mapRef.current = null;
      map.remove();
    };
  }, [useOsmTiles]);

  // Update cursor when drawingMode toggles
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    map.getCanvas().style.cursor = drawingMode ? "crosshair" : "";
  }, [mapReady, drawingMode]);

  // Sync GeoJSON sources and styles whenever data or toggles change
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    const baselineSrc = map.getSource("baseline-water") as GeoJSONSource | undefined;
    const floodSrc = map.getSource("flood") as GeoJSONSource | undefined;
    const stationsSrc = map.getSource("stations") as GeoJSONSource | undefined;
    const covSrc = map.getSource("coverage") as GeoJSONSource | undefined;
    const claimSrc = map.getSource("claim") as GeoJSONSource | undefined;
    const epSrc = map.getSource("claim-endpoints") as GeoJSONSource | undefined;
    const draftSrc = map.getSource("draw-draft") as GeoJSONSource | undefined;

    baselineSrc?.setData(baselineWaterGeoJson);
    floodSrc?.setData(floodGeoJson);
    stationsSrc?.setData(stationsGeoJson);
    covSrc?.setData(coverageGeoJson);
    claimSrc?.setData(claimGeoJson);
    epSrc?.setData(endpointGeoJson);
    draftSrc?.setData(draftGeoJson);

    map.setPaintProperty("claim-line", "line-color", claimColor);
    map.setLayoutProperty("flood-fill", "visibility", showFlood ? "visible" : "none");
    map.setLayoutProperty("flood-outline", "visibility", showFlood ? "visible" : "none");
    map.setLayoutProperty("coverage-fill", "visibility", showCoverage ? "visible" : "none");
    map.setLayoutProperty("coverage-outline", "visibility", showCoverage ? "visible" : "none");
    map.setLayoutProperty(
      "baseline-water-fill",
      "visibility",
      showContext ? "visible" : "none",
    );
    map.setLayoutProperty(
      "baseline-water-outline",
      "visibility",
      showContext ? "visible" : "none",
    );
  }, [
    mapReady,
    baselineWaterGeoJson,
    floodGeoJson,
    stationsGeoJson,
    coverageGeoJson,
    claimGeoJson,
    endpointGeoJson,
    draftGeoJson,
    claimColor,
    showFlood,
    showCoverage,
    showContext,
  ]);

  // Sync offline HTML landmark labels (zero glyph server / zero network requests)
  useEffect(() => {
    const map = mapRef.current;
    for (const m of markersRef.current) m.remove();
    markersRef.current = [];
    if (!map || !mapReady || !showContext || !localContext?.landmarks) return;

    for (const feat of localContext.landmarks.features) {
      if (feat.geometry.type !== "Point") continue;
      const [lon, lat] = feat.geometry.coordinates;
      const name = String(feat.properties?.name ?? "");
      const kind = String(feat.properties?.kind ?? "locality");
      if (!name) continue;
      const el = document.createElement("div");
      el.className = `map-landmark-label landmark-${kind}`;
      el.textContent = name;
      const marker = new maplibregl.Marker({ element: el, anchor: "bottom" })
        .setLngLat([lon, lat])
        .addTo(map);
      markersRef.current.push(marker);
    }
  }, [mapReady, showContext, localContext]);

  // Auto-fit bounds to direct flood polygons + active claim
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const geoms: Array<{ coordinates: unknown }> = [];
    if (claimGeometry) geoms.push(claimGeometry);
    for (const ev of evidenceItems) {
      if (
        ev.geometry &&
        (ev.geometry.type === "Polygon" || ev.geometry.type === "MultiPolygon")
      ) {
        geoms.push(ev.geometry);
      }
    }
    const bounds = computeBounds(geoms);
    if (bounds) {
      map.fitBounds(bounds, { padding: 48, maxZoom: 14, duration: 350 });
    }
  }, [mapReady, claimGeometry, evidenceItems]);

  const handleFitClaim = () => {
    const map = mapRef.current;
    if (!map || !claimGeometry) return;
    const bounds = computeBounds([claimGeometry]);
    if (bounds) map.fitBounds(bounds, { padding: 70, maxZoom: 15, duration: 350 });
  };

  const handleFitAoi = () => {
    const map = mapRef.current;
    if (!map) return;
    const geoms: Array<{ coordinates: unknown }> = [];
    for (const ev of evidenceItems) {
      if (ev.coverage) geoms.push(ev.coverage);
      if (ev.geometry) geoms.push(ev.geometry);
    }
    if (claimGeometry) geoms.push(claimGeometry);
    const bounds = computeBounds(geoms);
    if (bounds) map.fitBounds(bounds, { padding: 40, maxZoom: 13, duration: 350 });
  };

  const toggleDrawing = () => {
    setDrawingMode((prev) => {
      if (prev) setDraftStart(null);
      return !prev;
    });
  };

  return (
    <section className="map-panel" aria-label="Geospatial evidence map">
      <div className="map-toolbar">
        <div className="map-toggles" role="group" aria-label="Map layer controls">
          <label className="chip-toggle">
            <input
              type="checkbox"
              checked={showFlood}
              onChange={(e) => setShowFlood(e.target.checked)}
            />
            <span>Flood extent ({evidenceItems.length})</span>
          </label>
          <label className="chip-toggle">
            <input
              type="checkbox"
              checked={showCoverage}
              onChange={(e) => setShowCoverage(e.target.checked)}
            />
            <span>Coverage</span>
          </label>
          <label className="chip-toggle">
            <input
              type="checkbox"
              checked={showContext}
              onChange={(e) => setShowContext(e.target.checked)}
            />
            <span>Water &amp; landmarks</span>
          </label>
          <label className="chip-toggle">
            <input
              type="checkbox"
              checked={useOsmTiles}
              onChange={(e) => setUseOsmTiles(e.target.checked)}
            />
            <span>OSM (online)</span>
          </label>
        </div>
        <div className="map-actions">
          {onCustomRoadChange && (
            <button
              type="button"
              className={`btn-ghost ${drawingMode ? "btn-draw-active" : ""}`}
              onClick={toggleDrawing}
              data-testid="draw-road-button"
            >
              {drawingMode ? "Cancel Draw" : "Draw Road (2 clicks)"}
            </button>
          )}
          <button
            type="button"
            className="btn-ghost"
            onClick={handleFitClaim}
            disabled={!claimGeometry}
          >
            Fit Claim
          </button>
          <button
            type="button"
            className="btn-ghost"
            onClick={handleFitAoi}
            disabled={evidenceItems.length === 0 && !claimGeometry}
          >
            Fit Coverage
          </button>
        </div>
      </div>

      {/* Concise Direct vs Indirect Environmental Context Strip */}
      {(gsiItem || metItem) && (
        <div className="map-context-strip" data-testid="env-context-strip">
          <span className="context-chip chip-direct">
            <strong>Direct SAR:</strong> CEMS EMSR718 (2024-04-15 06:02Z)
          </span>
          {gsiItem && typeof gsiItem.attributes?.stage_maod === "number" && (
            <span className="context-chip chip-indirect">
              <strong>Indirect Hydro (GSI_11):</strong> {gsiItem.attributes.stage_maod} mAOD (&gt;p99{" "}
              {String(gsiItem.attributes.historical_p99_maod ?? "68.90")})
            </span>
          )}
          {metItem && typeof metItem.attributes?.rain_mm === "number" && (
            <span className="context-chip chip-indirect">
              <strong>Indirect Met (Mt Dillon):</strong> {metItem.attributes.rain_mm} mm/day ·{" "}
              {String(metItem.attributes.cumulative_5day_rain_mm ?? "?")} mm (5d, 27 km NNE)
            </span>
          )}
        </div>
      )}

      <div className="map-stage">
        {mapError ? (
          <div className="map-fallback" role="status">
            <p>{mapError}</p>
          </div>
        ) : (
          <div ref={containerRef} className="map-canvas" data-testid="map-canvas" />
        )}

        {drawingMode && (
          <div className="map-overlay-banner map-overlay-draw" role="status">
            {draftStart
              ? `Start point placed (${draftStart[0]}, ${draftStart[1]}). Click a second point on the map to evaluate that road segment.`
              : "Interactive Road Selector: Click a start point on the map, then click an end point to test any road segment."}
          </div>
        )}

        {!claimGeometry && (
          <div className="map-overlay-banner" role="status">
            Claim geometry is missing or invalid GeoJSON LineString — fix geometry to preview on map.
          </div>
        )}

        {evidenceItems.length === 0 && (
          <div className="map-overlay-banner map-overlay-bottom" role="status">
            No evidence polygons loaded in active store.
          </div>
        )}

        {tileNotice && (
          <div className="map-overlay-banner map-overlay-bottom" role="status">
            {tileNotice}
          </div>
        )}
      </div>

      <div className="map-footer">
        <div className="map-legend" aria-label="Map legend">
          <span className="legend-item">
            <span className="swatch swatch-flood" /> Direct flood extent
          </span>
          <span className="legend-item">
            <span className="swatch swatch-baseline" /> Baseline water (display context)
          </span>
          <span className="legend-item">
            <span className="swatch swatch-coverage" /> Documented AOI coverage
          </span>
          <span className="legend-item">
            <span className="swatch swatch-station" /> Hydrometric / Met station
          </span>
          <span className="legend-item">
            <span
              className="swatch swatch-claim"
              style={{ backgroundColor: claimColor }}
            />{" "}
            Claimed road segment
          </span>
        </div>
        <div className="map-attribution">
          Offline WGS84 vector canvas | © EU Copernicus EMS · GSI (CC BY 4.0) · Met Éireann (CC BY 4.0)
        </div>
      </div>
    </section>
  );
}
