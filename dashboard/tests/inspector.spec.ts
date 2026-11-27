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
});
