// Run with PLAYWRIGHT_MODULE pointing to an installed Playwright package if needed.
import assert from "node:assert/strict";
import fs from "node:fs/promises";
const { chromium } = await import(
  process.env.PLAYWRIGHT_MODULE || "playwright"
);
const browser = await chromium.launch({
  headless: true,
  channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => {
  if (m.type() === "error" && !m.text().includes("favicon"))
    errors.push(m.text());
});
const base = process.env.PROMO_TEST_URL || "http://127.0.0.1:8765";
await fs.mkdir("tmp/screenshots", { recursive: true });
try {
  await page.goto(base, { waitUntil: "networkidle" });
  await page.locator(".candidate-card").first().waitFor();
  await page.screenshot({
    path: "tmp/screenshots/desktop.png",
    fullPage: true,
  });
  assert.ok((await page.locator(".source-event").count()) > 0);
  await page.locator('[data-source-filter="dialogue"]').click();
  assert.equal(await page.locator(".source-event.camera").count(), 0);
  await page.locator("#scope").selectOption("valid");
  assert.ok((await page.locator(".candidate-card").count()) > 0);
  await page.locator("#search").fill("this-string-will-not-exist-475");
  await page.getByText("No cuts in this view.").waitFor();
  await page.locator("#search").fill("");
  await page.locator('[data-view="episodes"]').click();
  assert.ok((await page.locator("tbody tr").count()) > 0);
  await page.locator("[data-open-episode]").first().click();
  await page.locator(".candidate-card").first().waitFor();
  await page.locator('[data-view="evaluation"]').click();
  await page
    .getByText("This editorial analysis contains no audience measurements.", {
      exact: false,
    })
    .waitFor();
  await page.locator('[data-view="history"]').click();
  await page.locator("[data-open-run]").first().waitFor();
  await page.locator('[data-view="method"]').click();
  await page.getByText("01 / Read the source, preserve the evidence").waitFor();
  await page.locator("#new-run").click();
  await page.locator("#source").selectOption("sample");
  await page.locator("#provider").selectOption("offline");
  await page.locator("#start-run").click();
  await page
    .getByText("Analysis complete. Inspect the source before editing.")
    .waitFor({ timeout: 30000 });
  const downloadPromise = page.waitForEvent("download");
  await page.locator("#export-bundle").click();
  const download = await downloadPromise;
  assert.ok(download.suggestedFilename().endsWith(".zip"));
  // New input upload, not just the bundled pack.
  await page.locator("#new-run").click();
  await page.locator("#source").selectOption("upload");
  await page
    .locator("#files")
    .setInputFiles("promo_lab/examples/episode-001.txt");
  await page.locator("#provider").selectOption("offline");
  const uploadStarted = page.waitForResponse(
    (r) => r.url().endsWith("/api/runs") && r.request().method() === "POST",
  );
  await page.locator("#start-run").click();
  await uploadStarted;
  await page.locator("#run-strip").waitFor({ state: "hidden", timeout: 30000 });
  await page.locator(".candidate-card").first().waitFor();
  await page.waitForTimeout(1500);
  await page.locator("#run-strip").waitFor({ state: "hidden", timeout: 30000 });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "tmp/screenshots/mobile.png", fullPage: true });
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  assert.equal(overflow, false, "Mobile layout overflows horizontally");
  assert.deepEqual(errors, [], `Browser errors: ${errors.join("\n")}`);
  console.log(
    JSON.stringify({
      passed: true,
      checks: [
        "source inspection",
        "filters",
        "episode coverage",
        "quality report",
        "run history",
        "method",
        "new analysis",
        "upload",
        "bundle export",
        "mobile layout",
      ],
      screenshots: [
        "tmp/screenshots/desktop.png",
        "tmp/screenshots/mobile.png",
      ],
    }),
  );
} finally {
  await browser.close();
}
