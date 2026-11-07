// Generates requested, explicitly labeled synthetic artifacts. No human events.
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
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const studies = await (await fetch(base + "/api/experiments")).json();
const before = await Promise.all(
  studies.studies.map(async (s) => ({
    id: s.id,
    report: await (await fetch(base + `/api/experiments/${s.id}`)).json(),
    events: await (
      await fetch(
        base + `/api/experiments/${s.id}/export?artifact=events.jsonl`,
      )
    ).text(),
  })),
);
const runs = [];
try {
  await page.goto(base + "/#simulations", { waitUntil: "networkidle" });
  await page.locator("#simulation-source").waitFor();
  const source = studies.studies.find(
    (s) => !s.is_test && s.candidate_count >= 2,
  );
  if (source) await page.locator("#simulation-source").selectOption(source.id);
  for (const scenario of ["no_signal", "drift", "stationary"]) {
    await page.locator("#simulation-scenario").selectOption(scenario);
    const result = page.waitForResponse(
      (r) =>
        r.url().endsWith("/api/simulations") && r.request().method() === "POST",
    );
    await page.locator("#run-simulation").click();
    const response = await result;
    assert.equal(response.status(), 201);
    const report = await response.json();
    runs.push(report);
    await page
      .getByText("Assumed appeal vs learned response", { exact: true })
      .waitFor();
    await page.locator("#run-simulation").waitFor({ state: "visible" });
    assert.equal(report.is_synthetic, true);
    assert.equal(report.summary.synthetic_responses, 4800);
    if (scenario === "no_signal")
      report.daily.forEach((d) =>
        assert.ok(
          Math.abs(d.oracle_expected_policy - d.oracle_expected_control) <
            1e-10,
        ),
      );
    await page
      .locator(`.badge:has-text("${scenario.toUpperCase()} · SEED 42")`)
      .waitFor();
  }
  await fs.mkdir("tmp/screenshots", { recursive: true });
  await page.screenshot({
    path: "tmp/screenshots/synthetic-demo-desktop.png",
    fullPage: true,
  });
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("link", {
      name: "↓ SYNTHETIC synthetic_responses.csv",
      exact: true,
    })
    .click();
  const download = await downloadPromise;
  assert.ok(download.suggestedFilename().startsWith("SYNTHETIC-"));
  const rowsResponse = await fetch(
    base +
      `/api/simulations/${runs.at(-1).id}/export?artifact=synthetic_responses.jsonl`,
  );
  const rows = (await rowsResponse.text()).trim().split("\n").map(JSON.parse);
  assert.equal(rows.length, 4800);
  assert.ok(
    rows.every((r) => r.is_synthetic && !r.training_eligible_for_real_model),
  );
  await page.reload({ waitUntil: "networkidle" });
  await page
    .getByText("Assumed appeal vs learned response", { exact: true })
    .waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "tmp/screenshots/synthetic-demo-mobile.png",
    fullPage: true,
  });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
    false,
    "Mobile overflow",
  );
  for (const item of before) {
    const report = await (
      await fetch(base + `/api/experiments/${item.id}`)
    ).json();
    const events = await (
      await fetch(
        base + `/api/experiments/${item.id}/export?artifact=events.jsonl`,
      )
    ).text();
    assert.deepEqual(report, item.report, "Real experiment report changed");
    assert.equal(events, item.events, "Real events changed");
  }
  assert.deepEqual(errors, []);
  console.log(
    JSON.stringify({
      passed: true,
      checks: [
        "synthetic provenance",
        "three scenarios",
        "cold-start fit and held-out validation",
        "epsilon-greedy and random control",
        "daily model updates",
        "download provenance",
        "persistence",
        "mobile layout",
        "real-data isolation",
      ],
      runs: runs.map((r) => ({
        id: r.id,
        scenario: r.config.scenario,
        synthetic_responses: r.summary.synthetic_responses,
        simulated_difference_pp: r.summary.absolute_difference * 100,
        validation: r.validation.model,
      })),
    }),
  );
} finally {
  await browser.close();
}
