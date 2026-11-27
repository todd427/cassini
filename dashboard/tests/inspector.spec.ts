import { expect, test } from "@playwright/test";

test.describe("Evidence Inspector E2E", () => {
  test("submits real EMSR718 intersecting, covered-clear, and stale claims against live API", async ({
    page,
  }) => {
    await page.goto("/");

    // Connected to live API with genuine Copernicus EMSR718 provenance
    await expect(page.getByTestId("connection-status")).toContainText("Live API");
    await expect(page.getByTestId("provenance-card").first()).toContainText(
      "EMSR718_AOI02_DEL_MONIT01_v2",
    );
    await expect(page.getByTestId("provenance-card").first()).toContainText(
      "2f2039bd645de3f8f1a120ea717287bb3640e421f94e107dc98a9353b95ab947",
    );
    await expect(page.getByText("HISTORICAL REPLAY", { exact: true })).toBeVisible();
    await expect(page.getByText("SYNTHETIC INPUT", { exact: true })).toBeVisible();

    // 1) Potential Conflict (intersecting Lough Funshinagh flood)
    await page.getByTestId("assess-button").click();
    await expect(page.getByTestId("assessment-status")).toHaveText("Potential conflict");
    await expect(page.getByTestId("reason-list")).toContainText("FLOOD_EXTENT_INTERSECTS");
    await expect(page.getByTestId("limitations-list")).toContainText("impassability");

    // Allow MapLibre fitBounds animation (350ms) to settle before visual screenshot
    await page.waitForTimeout(600);
    await page.screenshot({
      path: "test-results/evidence-inspector-conflict.png",
      fullPage: true,
    });

    // 2) Covered non-overlap (explicitly NOT proof of safety, no green safe verdict)
    await page.locator("#preset-select").selectOption("emsr718-covered-clear");
    await page.getByTestId("assess-button").click();
    await expect(page.getByTestId("assessment-status")).toHaveText("No mapped overlap");
    await expect(page.getByTestId("reason-list")).toContainText("NO_MAPPED_OVERLAP");
    await expect(page.getByTestId("assessment-result")).toContainText(
      "Not proof of safety or road passability",
    );

    // 3) Stale observation (>24h)
    await page.locator("#preset-select").selectOption("emsr718-stale");
    await page.getByTestId("assess-button").click();
    await expect(page.getByTestId("assessment-status")).toHaveText("Insufficient evidence");
    await expect(page.getByTestId("reason-list")).toContainText("OBSERVATION_STALE");
    await expect(page.getByTestId("assessment-result")).toContainText("72.00 h");
  });

  test("handles missing evidence dataset gracefully", async ({ page }) => {
    await page.route("**/v1/evidence", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [] }),
      });
    });
    await page.route("**/v1/assess", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          claim_id: "emsr718-road-ballagh-east",
          status: "insufficient_evidence",
          policy_version: "flood-road-0.1",
          reasons: ["NO_EVIDENCE"],
          evidence_ids: [],
          findings: [],
          limitations: ["No evidence records were available for assessment."],
          synthetic: true,
        }),
      });
    });

    await page.goto("/");
    await expect(page.getByTestId("no-evidence-note")).toBeVisible();
    await page.getByTestId("assess-button").click();
    await expect(page.getByTestId("assessment-status")).toHaveText("Insufficient evidence");
    await expect(page.getByTestId("reason-list")).toContainText("NO_EVIDENCE");
  });

  test("surfaces HTTP 422 validation error and API connectivity failure without silent mock fallback", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.getByTestId("connection-status")).toContainText("Live API");

    // Submit naive timestamp -> live FastAPI returns 422
    await page.locator("#claimed-at").fill("2024-04-15T08:00:00");
    await page.getByTestId("assess-button").click();
    await expect(page.getByTestId("assess-error")).toContainText("Validation error (HTTP 422)");

    // Simulate unreachable API on reload -> explicit error banner, NO silent mock mode
    await page.route("**/health", (route) => route.abort());
    await page.route("**/v1/evidence", (route) => route.abort());
    await page.reload();
    await expect(page.getByTestId("api-error-banner")).toBeVisible();
    await expect(page.getByTestId("mock-banner")).toHaveCount(0);

    // Explicit user toggle switches to Mock Mode
    await page.getByLabel("Toggle Mock Mode").check();
    await expect(page.getByTestId("mock-banner")).toBeVisible();
    await page.getByTestId("assess-button").click();
    await expect(page.getByTestId("assessment-status")).toHaveText("Potential conflict");
  });

  test("displays multiple genuine independent sources, independence grouping, and availability timestamps", async ({
    page,
  }) => {
    await page.goto("/");

    const provenanceCards = page.getByTestId("provenance-card");
    await expect(provenanceCards).toHaveCount(3);
    await expect(provenanceCards.nth(0)).toContainText("EMSR718_AOI02_DEL_MONIT01_v2");
    await expect(provenanceCards.nth(1)).toContainText("GSI_11_Lough_Funshinagh");
    await expect(provenanceCards.nth(1)).toContainText("69.37 mAOD");
    await expect(provenanceCards.nth(2)).toContainText("MET_EIREANN_DLY_1975_MT_DILLON");

    await page.getByTestId("assess-button").click();
    await expect(page.getByTestId("assessment-status")).toHaveText("Potential conflict");

    // Verify independence grouping summary and per-source findings across all 3 genuine sources
    await expect(page.getByTestId("independence-summary")).toContainText(
      "Distinct declared sources",
    );
    await expect(page.getByTestId("independence-summary")).toContainText(
      "3 independent group(s) / 3 source(s)",
    );
    await expect(page.getByTestId("findings-list")).toContainText("contextual_support");
    await expect(page.getByTestId("findings-list")).toContainText("Unknown (null)");
  });

  test("evaluates genuine locally verified Galileo OSNMA navigation auth and rejects positioning accuracy claims", async ({
    page,
  }) => {
    await page.goto("/");

    // Switch to Galileo OSNMA mode within the same unified Evidence Inspector
    await page.getByTestId("tab-galileo").click();
    await expect(page.getByTestId("galileo-crypto-panel")).toBeVisible();
    await expect(page.getByTestId("galileo-crypto-panel")).toContainText("188 / 188");
    await expect(page.getByTestId("galileo-crypto-panel")).toContainText("Septentrio mosaic-X5");
    await expect(page.getByTestId("provenance-card").first()).toContainText(
      "OSNMA_SBF_WN1253_PKID1",
    );

    // 1) Genuine locally verified navigation-message authentication
    await page.getByTestId("assess-button").click();
    await expect(page.getByTestId("assessment-status")).toHaveText(
      "Authenticated (Nav Message Only)",
    );
    await expect(page.getByTestId("active-policy-version")).toHaveText("galileo-osnma-0.1");
    await expect(page.getByTestId("reason-list")).toContainText("OSNMA_LOCALLY_VERIFIED");
    await expect(page.getByTestId("findings-list")).toContainText("local_osnma_cryptographic");

    await page.screenshot({
      path: "test-results/evidence-inspector-galileo.png",
      fullPage: true,
    });

    // 2) Positioning accuracy claim -> Evidence unsuitable
    await page.locator("#preset-select").selectOption("galileo-positioning-unsuitable");
    await page.getByTestId("assess-button").click();
    await expect(page.getByTestId("assessment-status")).toHaveText("Evidence unsuitable");
    await expect(page.getByTestId("reason-list")).toContainText(
      "NAV_AUTH_INSUFFICIENT_FOR_POSITIONING",
    );
  });

  test("v0.5: renders 5-second executive hero, interactive Evidence Graph, Presentation/Technical modes, and live Decision-Time Audit", async ({
    page,
  }) => {
    await page.goto("/");

    // Auto-assessed initial scenario populates Executive Hero, Graph, and Timeline immediately
    await expect(page.getByTestId("executive-summary")).toBeVisible();
    await expect(page.getByTestId("hero-status")).toHaveText("Potential conflict");
    await expect(page.getByTestId("env-context-strip")).toContainText("69.37 mAOD");
    await expect(page.getByTestId("env-context-strip")).toContainText("6.1 mm/day");

    // Backend-driven Evidence Graph with clickable node inspector
    await expect(page.getByTestId("evidence-graph")).toBeVisible();
    const evNodes = page.getByTestId("graph-node-evidence");
    await expect(evNodes).toHaveCount(3);
    await evNodes.nth(1).click();
    await expect(page.getByTestId("graph-node-inspector")).toContainText(
      "GSI_11_Lough_Funshinagh",
    );
    await expect(page.getByTestId("graph-node-inspector")).toContainText("Unknown (null)");

    await page.waitForTimeout(500);
    await page.screenshot({
      path: "test-results/evidence-inspector-v05-env.png",
      fullPage: true,
    });

    // Presentation vs Technical Inspection mode toggle
    await expect(page.locator("#geometry-json")).toHaveCount(0);
    await page.getByTestId("view-technical").click();
    await expect(page.locator("#geometry-json")).toBeVisible();
    await expect(page.getByTestId("technical-inspector")).toContainText("Input Fingerprint");
    await page.getByTestId("view-presentation").click();
    await expect(page.locator("#geometry-json")).toHaveCount(0);

    // Interactive Timeline: switch to Decision-Time Audit against live API -> honest AVAILABILITY_TIME_UNKNOWN
    await expect(page.getByTestId("evidence-timeline")).toBeVisible();
    await page.getByTestId("mode-decision-time").click();
    await expect(page.getByTestId("decision-time-controls")).toBeVisible();
    await expect(page.getByTestId("assessment-status")).toHaveText("Insufficient evidence");
    await expect(page.getByTestId("reason-list")).toContainText("AVAILABILITY_TIME_UNKNOWN");
  });

  test("v0.5: runs Galileo OSNMA controlled offline 1-bit tampering comparison and displays explicit 5-point scope disclosures", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByTestId("tab-galileo").click();
    await page.getByTestId("assess-button").click();

    await expect(page.getByTestId("assessment-status")).toHaveText(
      "Authenticated (Nav Message Only)",
    );
    await expect(page.getByTestId("evidence-graph")).toContainText("OSNMA_SBF_WN1253_PKID1");

    // Verify all 5 explicit Galileo verification disclosures
    const disclosures = page.getByTestId("galileo-scope-disclosures");
    await expect(disclosures).toContainText("2023 Public Test Phase");
    await expect(disclosures).toContainText("Retrospective & Offline");
    await expect(disclosures).toContainText("Not Positioning Accuracy");
    await expect(disclosures).toContainText("No Real-Time Replay Protection");
    await expect(disclosures).toContainText("Trust Anchor Dependency");

    // Run real local 4-layer verifier on Original vs 1-bit Tampered SBF copy
    await page.getByTestId("run-tamper-demo-button").click();
    const comparison = page.getByTestId("tamper-comparison-result");
    await expect(comparison).toBeVisible();
    await expect(comparison).toContainText("SYNTHETIC TAMPER TEST");
    await expect(comparison).toContainText("188 / 188 verified");
    await expect(comparison).toContainText("authentication_failed");
    await expect(comparison).toContainText("AUTHENTICATION_FAILED");
    await expect(comparison).toContainText("1 FAILED (HMAC mismatch detected)");

    await page.screenshot({
      path: "test-results/evidence-inspector-v05-galileo.png",
      fullPage: true,
    });
  });
});
