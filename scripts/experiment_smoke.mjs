// Automated browser interactions are software tests, never audience evidence.
import assert from "node:assert/strict";
import fs from "node:fs/promises";
const { chromium } = await import(
  process.env.PLAYWRIGHT_MODULE || "playwright"
);
const base = process.env.PROMO_TEST_URL || "http://127.0.0.1:8765";
const browser = await chromium.launch({
  headless: true,
  channel: process.env.PLAYWRIGHT_CHANNEL || "chrome",
});
const context = await browser.newContext({
  viewport: { width: 1100, height: 920 },
});
const page = await context.newPage();
const errors = [],
  failedUploads = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("response", async (r) => {
  if (r.url().endsWith("/events") && r.status() >= 400)
    failedUploads.push(await r.text());
});
const api = async (path, body) => {
  const response = await fetch(
    base + path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const result = await response.json();
  assert.ok(response.ok, JSON.stringify(result));
  return result;
};
const study = await api("/api/experiments", {
  name: "AUTOMATED browser smoke",
  is_test: true,
  source_run_id: process.env.PROMO_EXPERIMENT_SOURCE_RUN || null,
});
async function waitForReport(predicate, label) {
  for (let i = 0; i < 60; i++) {
    const r = await api(`/api/experiments/${study.id}`);
    if (predicate(r)) return r;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`Timed out: ${label}`);
}
try {
  await fs.mkdir("tmp/screenshots", { recursive: true });
  await page.goto(base);
  await page.locator('[data-view="experiments"]').click();
  await page.locator("#study-select").selectOption(study.id);
  await page
    .getByText("No interactions collected yet", { exact: true })
    .waitFor();
  await page.screenshot({
    path: "tmp/screenshots/experiment-admin.png",
    fullPage: true,
  });
  await page.goto(`${base}/experiment/${study.id}`);
  await page
    .locator("#study-name")
    .getByText(/AUTOMATED/)
    .waitFor();
  assert.equal(await page.locator("#begin").isDisabled(), true);
  await page.locator("#consent").check();
  await page.locator("#begin").click();
  await page.locator(".story-card").first().waitFor();
  await page.bringToFront();
  await page.screenshot({ path: "tmp/screenshots/experiment-feed.png" });
  const cards = await page.locator(".story-card").count();
  assert.equal(cards, 7);
  // Reach the assigned target through normal controls. Every target is at 3–6.
  const report = await api(`/api/experiments/${study.id}`);
  const target = report.candidates.find((c) => c.assigned_sessions === 1);
  assert.ok(target);
  let reached = false;
  for (let i = 0; i < 7; i++) {
    await page.waitForTimeout(300);
    const title = await page
      .locator(".story-card")
      .nth(i)
      .locator("h2")
      .textContent();
    if (title === target.title) {
      reached = true;
      break;
    }
    await page.locator("#next").click();
  }
  assert.ok(reached, "Assigned target not encountered");
  await page.waitForTimeout(3400);
  let r = await waitForReport(
    (r) => r.summary.first_promo_exposures === 1,
    "promo exposure",
  );
  // Reload preserves assignment and censors the interrupted exposure.
  await page.reload();
  await page.locator("#consent").check();
  await page.locator("#begin").click();
  await page.locator("#experience").waitFor({ state: "visible" });
  await waitForReport(
    (r) => r.summary.repeat_exposures === 1,
    "reload exposure",
  );
  r = await api(`/api/experiments/${study.id}`);
  assert.equal(r.metrics.clicked_continue.unknown, 1);
  const index =
    Number(
      (await page.locator("#position").textContent()).split("/")[0].trim(),
    ) - 1;
  await page
    .locator(".story-card")
    .nth(index)
    .locator(".continue-button")
    .click();
  await page.locator("#reader-body .story-unit").first().waitFor();
  await page.waitForTimeout(1200);
  await page.locator("#reader-body").evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  await page.waitForTimeout(400);
  await page.screenshot({ path: "tmp/screenshots/experiment-reader.png" });
  await page.locator("#close-reader").click();
  // Offline interactions persist locally, then sync without duplicates.
  await context.setOffline(true);
  await page.locator("#exit").click();
  await page.locator("#finish").waitFor({ state: "visible" });
  assert.match(
    await page.locator("#finish-sync").textContent(),
    /waiting to sync/,
  );
  await context.setOffline(false);
  r = await waitForReport(
    (r) => r.summary.completed_sessions === 1,
    "offline queue upload",
  );
  assert.equal(r.summary.training_rows, 0);
  const training = await fetch(
    `${base}/api/experiments/${study.id}/export?artifact=training.jsonl`,
  );
  assert.equal(await training.text(), "");
  const raw = await fetch(
    `${base}/api/experiments/${study.id}/export?artifact=events.jsonl`,
  );
  const events = (await raw.text()).trim().split("\n").map(JSON.parse);
  assert.equal(new Set(events.map((e) => e.event_id)).size, events.length);
  assert.ok(events.some((e) => e.type === "continue_open"));
  assert.ok(events.some((e) => e.continuation_ms > 0));
  assert.ok(events.some((e) => e.type === "view_end" && e.reason === "unload"));
  // Another participant, using a deliberate shared-device reset.
  await page.goto(`${base}/experiment/${study.id}?fresh=1`);
  await page.locator("#consent").check();
  await page.locator("#begin").click();
  await page.locator("#experience").waitFor({ state: "visible" });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "tmp/screenshots/experiment-mobile.png" });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
    false,
  );
  // Headless Chrome can report every tab focused. Inject only the focus signal
  // in this software-test profile to exercise the production timing guard.
  await page.waitForTimeout(800);
  await page.evaluate(() => {
    Object.defineProperty(document, "hasFocus", {
      configurable: true,
      value: () => false,
    });
    window.dispatchEvent(new Event("blur"));
  });
  await page.waitForTimeout(1500);
  await page.evaluate(() => {
    delete document.hasFocus;
    window.dispatchEvent(new Event("focus"));
  });
  await page.waitForTimeout(300);
  await page.locator("#exit").click();
  await waitForReport(
    (r) => r.summary.completed_sessions === 2,
    "second session finish",
  );
  const backgroundRaw = await fetch(
    `${base}/api/experiments/${study.id}/export?artifact=events.jsonl`,
  );
  const backgroundEvents = (await backgroundRaw.text())
    .trim()
    .split("\n")
    .map(JSON.parse);
  const lastEnd = backgroundEvents.filter((e) => e.type === "view_end").at(-1);
  const blur = backgroundEvents
    .filter(
      (e) => e.session_id === lastEnd.session_id && e.reason === "window_blur",
    )
    .at(-1);
  assert.ok(blur, "Missing blur telemetry");
  assert.ok(
    lastEnd.active_ms - blur.active_ms < 1200,
    `Background time was counted as reading: ${lastEnd.active_ms - blur.active_ms}`,
  );
  page.once("dialog", (d) => d.accept());
  await page.locator("#finish-withdraw").click();
  await page.getByText("Your session was deleted.", { exact: true }).waitFor();
  r = await api(`/api/experiments/${study.id}`);
  assert.equal(r.summary.sessions, 1);
  assert.deepEqual(errors, []);
  assert.deepEqual(
    failedUploads,
    [],
    `Server rejected events: ${failedUploads.join("\n")}`,
  );
  console.log(
    JSON.stringify({
      passed: true,
      checks: [
        "consent",
        "neutral randomized feed",
        "real DOM controls",
        "refresh censoring",
        "continuation events",
        "offline queue and retry",
        "test export exclusion",
        "shared-device reset",
        "mobile layout",
        "withdrawal",
      ],
      testStudy: study.id,
    }),
  );
} finally {
  await browser.close();
  await api(`/api/experiments/${study.id}/remove-test`, {});
}
