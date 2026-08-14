import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const dhoHeaders = { "X-Tulina-Role": "dho_approver" };
const screenshotRoot = path.resolve(import.meta.dirname, "..", "..", "docs", "screenshots");

async function captureSubmissionShot(page: Page, filename: string) {
  if (process.env.TULINA_CAPTURE_SCREENSHOTS !== "1") return;
  fs.mkdirSync(screenshotRoot, { recursive: true });
  await page.screenshot({ path: path.join(screenshotRoot, filename), fullPage: true });
}

async function resetDemo(page: Page) {
  const response = await page.request.post("http://127.0.0.1:8080/api/v1/demo/reset", {
    headers: dhoHeaders,
  });
  expect(response.ok()).toBeTruthy();
}

async function expectMoment(page: Page, name: string) {
  await expect(page.locator(".story-intro h2")).toHaveText(name, { timeout: 20_000 });
}

async function nextMoment(page: Page, name: string) {
  await page.getByRole("button", { name: "Next moment" }).click();
  await expectMoment(page, name);
}

test.beforeEach(async ({ page }) => {
  await resetDemo(page);
});

test("TR-027 completes offline, reconciles once, and rejects replay and tampering", async ({ page }) => {
  await page.goto("/judge");
  await expect(page.getByRole("heading", { name: "See Tulina take action" })).toBeVisible();
  await expect(page.getByText("Every moment below runs the real stock, policy, workflow, and audit logic.")).toBeVisible();

  await page.locator(".demo-controller").getByRole("button", { name: "Read demo card" }).click();
  await expect(page.getByRole("heading", { name: "Ready for human confirmation" })).toBeVisible();
  await page.getByText(/Evidence and confidence/).click();
  await expect(page.getByText("Saved fixture extraction · Gemini was not called")).toBeVisible();
  await expect(page.getByText("60 packs", { exact: true })).toBeVisible();
  await captureSubmissionShot(page, "02-stock-card-evidence.png");
  await page.getByRole("button", { name: "Confirm stock observation" }).click();
  await expect(page.getByText("Ready for district watch")).toBeVisible();

  await nextMoment(page, "Found nearby");
  await expect(page.getByText("6 of 6 checks")).toBeVisible();
  await page.getByText("Technical proof").click();
  await expect(page.getByText(/Google ADK/)).toBeVisible();
  await expect(page.getByText("TR-027", { exact: true }).first()).toBeVisible();
  await captureSubmissionShot(page, "01-found-nearby-and-03-agent-proof.png");

  await nextMoment(page, "Approval requested");
  await expect(page.getByText("Waiting for DHO", { exact: true })).toBeVisible();
  await nextMoment(page, "Human approved");
  await expect(page.getByText(/APR-DHO-001/).first()).toBeVisible();

  await nextMoment(page, "Tulina Note issued");
  await expect(page.getByText("Offline", { exact: true }).first()).toBeVisible();
  await expect(page.getByLabel("Scannable Tulina Note")).toBeVisible();
  await expect(page.getByText("CAP-TR027-001", { exact: false }).first()).toBeVisible();

  const offlineApiRequests: string[] = [];
  let measuringOfflineReceive = true;
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (measuringOfflineReceive && url.pathname.startsWith("/api/")) offlineApiRequests.push(url.pathname);
  });
  await nextMoment(page, "Received offline");
  measuringOfflineReceive = false;
  expect(offlineApiRequests).toEqual([]);
  await expect(page.getByText("Received offline — checking in when connected")).toBeVisible();
  await expect(page.getByText("Signature checked without internet")).toBeVisible();
  await captureSubmissionShot(page, "04-offline-facility-proof.png");

  await nextMoment(page, "Delivery confirmed");
  await expect(page.getByText("60 → 49", { exact: true })).toBeVisible();
  await expect(page.getByText("1 → 12", { exact: true })).toBeVisible();
  await expect(page.getByText("1", { exact: true }).last()).toBeVisible();

  await nextMoment(page, "Replay and tamper blocked");
  await expect(page.getByText("Rejected — signature invalid")).toBeVisible();
  await expect(page.getByText("1", { exact: true }).last()).toBeVisible();

  await page.getByRole("link", { name: "Activity" }).first().click();
  await expect(page.getByRole("heading", { name: "Every decision leaves a record" })).toBeVisible();
  await expect(page.getByText("Duplicate applied zero")).toBeVisible();
  await expect(page.getByText("Offline tamper blocked")).toBeVisible();
  await expect(page.getByText("Chain verified")).toBeVisible();
  await captureSubmissionShot(page, "05-delivery-defense-audit.png");
});

test("the service failure state is actionable and retry recovers", async ({ page }) => {
  await page.route("**/api/v1/overview", (route) => route.abort("failed"));
  await page.goto("/judge");
  await expect(page.getByRole("heading", { name: "We couldn’t reach the district service" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();

  await page.unroute("**/api/v1/overview");
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByRole("heading", { name: "See Tulina take action" })).toBeVisible();
});

test("district and facility views meet automated accessibility checks", async ({ page }) => {
  for (const route of ["/district", "/facility", "/audit"]) {
    await page.goto(route);
    await expect(page.locator("main h1")).toBeVisible();
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations, `${route}: ${results.violations.map((item) => item.id).join(", ")}`).toEqual([]);
  }
});

test("the facility view fits a small phone without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/facility");
  await expect(page.getByRole("heading", { name: "Busiu receiving view" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Mobile navigation" })).toBeVisible();
  await expect(page.getByText("DEV-F02-01")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});
