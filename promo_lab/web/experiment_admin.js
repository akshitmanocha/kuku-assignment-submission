"use strict";
window.PromoExperiments = (() => {
  let currentId = null,
    root = null,
    refreshTimer = null,
    generation = 0;
  const escape = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const pct = (n) => (n == null ? "—" : `${(n * 100).toFixed(1)}%`);
  async function api(path, body) {
    const response = await fetch(
      path,
      body === undefined
        ? {}
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed");
    return data;
  }
  function fail(e) {
    const node = root?.querySelector("#study-error");
    if (node) {
      node.textContent = e.message;
      node.hidden = false;
    }
  }
  function active() {
    return (
      !!root?.querySelector("#study-report") &&
      document
        .querySelector('[data-view="experiments"]')
        ?.classList.contains("active")
    );
  }
  function detail(metric) {
    const ci = metric.wilson_95;
    const bounds = metric.missing_outcome_bounds;
    return `${pct(metric.rate)} <small>${metric.successes}/${metric.denominator} observed · ${metric.unknown} unknown${ci ? `<br>95% CI ${pct(ci[0])}–${pct(ci[1])}` : ""}${bounds && metric.unknown ? `<br>All exposed bounds ${pct(bounds[0])}–${pct(bounds[1])}` : ""}</small>`;
  }
  async function report() {
    if (!currentId || !active()) return;
    const requested = currentId,
      version = generation;
    const r = await api(`/api/experiments/${requested}`);
    if (!active() || requested !== currentId || version !== generation) return;
    const s = r.summary,
      study = r.study;
    const link = `${location.origin}/experiment/${study.id}`;
    const metrics = [
      [
        "Consented sessions",
        s.sessions,
        `${s.completed_sessions} explicitly finished · ${s.assigned_not_exposed} did not reach their promo`,
      ],
      [
        "First promo exposures",
        s.first_promo_exposures,
        `${s.repeat_exposures} repeat exposures reported separately`,
      ],
      [
        "Continue click rate",
        pct(r.metrics.clicked_continue.rate),
        `${r.metrics.clicked_continue.successes}/${r.metrics.clicked_continue.denominator} observed · ${r.metrics.clicked_continue.unknown} unknown`,
      ],
      [
        "Qualified reading rate",
        pct(r.metrics.qualified_reading_continuation.rate),
        `${r.metrics.qualified_reading_continuation.successes}/${r.metrics.qualified_reading_continuation.denominator} observed · ${r.metrics.qualified_reading_continuation.unknown} unknown`,
      ],
    ];
    root.querySelector("#study-report").innerHTML = `
      <div class="study-link-box panel"><div class="section-bar"><h3>${escape(study.name)} <span class="badge ${study.is_test ? "badge-amber" : "badge-green"}">${study.is_test ? "SOFTWARE TEST · EXCLUDED FROM TRAINING" : study.closed ? "CLOSED" : "COLLECTING"}</span></h3><button class="button button-small" id="toggle-study">${study.closed ? "Reopen study" : "Close enrollment"}</button></div>
      <label class="field-label" for="participant-link">Participant link</label><input id="participant-link" readonly value="${escape(link)}"><div class="study-actions"><a class="button button-accent" href="${escape(link)}" target="_blank" rel="noopener">Open participant feed ↗</a><button class="button" id="copy-study-link">Copy link</button><a class="button" href="${escape(link)}?fresh=1" target="_blank" rel="noopener">New participant on this browser ↗</a></div>
      <p>${study.config.source_run_id ? `Source: saved run ${escape(study.config.source_run_id)} · ${study.candidate_count} promos with source continuation. Treat supplied assignment material as confidential.` : "Source: original public demo · 3 variants with original fiction continuation."}</p><p>This link works on this computer while the local server runs. Remote hosting is not configured. A new participant link resets the browser identity only after the previous session has finished or been closed and synced. Normal refreshes keep the same assignment.</p></div>
      <div class="stats-grid">${metrics.map(([label, value, sub]) => `<div class="stat"><div class="stat-top">${label}</div><div class="stat-value">${value}</div><div class="stat-bottom">${sub}</div></div>`).join("")}</div>
      <div class="section-bar"><div><h2>Candidate outcomes</h2><p>One target promo per session · uniform random assignment · first exposure for primary rates.</p></div><button class="button button-small" id="refresh-study">Refresh data</button></div>
      <div class="table-wrap"><table><thead><tr><th>Candidate</th><th>Assigned / exposed</th><th>Held ≥3s</th><th>Continue click</th><th>Qualified reading</th></tr></thead><tbody>${r.candidates.map((c) => `<tr><td><strong>${escape(c.title)}</strong><small>${escape(c.id)}</small></td><td>${c.assigned_sessions} / ${c.first_exposures}<small>${c.finalized} finalized</small></td><td>${detail(c.metrics.held_3s_text)}</td><td>${detail(c.metrics.clicked_continue)}</td><td>${detail(c.metrics.qualified_reading_continuation)}</td></tr>`).join("")}</tbody></table></div>
      <div class="panel"><h3>${s.events ? `${s.events} logged events · ${s.training_rows} training rows` : "No interactions collected yet"}</h3><p>${study.is_test ? "This study is marked as software testing. Its raw events can be inspected, but default training exports contain no test rows." : "Exports contain only promos that were actually viewed. An assigned but unseen promo never becomes a negative training example."}</p><div class="study-actions">${["training.jsonl", "training.csv", "events.jsonl", "report.json"].map((artifact) => `<a class="button button-small" href="/api/experiments/${study.id}/export?artifact=${artifact}">↓ ${artifact}</a>`).join("")}</div></div>
      <div class="report-grid"><div class="panel"><h3>What X and Y mean here</h3><p><strong>X:</strong> frozen source segments and event IDs, word count, speakers, genre, content hash, card position, preceding card, prior exposures, session elapsed time and UTC time. No post-exposure outcomes enter X.</p><p><strong>Y:</strong> active foreground dwell, visible text coverage, ≥3-second hold, a text completion proxy, continuation click, continuation dwell and coverage, and qualified reading continuation (≥15 active seconds and ≥75% continuation units seen). Thresholds are frozen before collection.</p></div><div class="panel"><h3>How to interpret the report</h3><p>${escape(r.interpretation)}</p><p>Each metric uses its own observed denominator, shown above. A still-open or interrupted exposure keeps unobserved binary outcomes null. Positive outcomes already observed remain positive. Reading time and coverage from these visits are partial measurements.</p><p>There is no trained audience model yet. Uniform exploration collects the first labels; later train with participant-held-out validation, then test exploitation against a randomized baseline.</p></div></div>
      ${study.is_test ? '<button class="button button-small" id="remove-test-study">Delete this software-test study</button>' : ""}`;
    root.querySelector("#copy-study-link").onclick = async () => {
      try {
        await navigator.clipboard.writeText(link);
      } catch {
        root.querySelector("#participant-link").select();
      }
    };
    root.querySelector("#refresh-study").onclick = () => report().catch(fail);
    root.querySelector("#toggle-study").onclick = async () => {
      try {
        await api(`/api/experiments/${study.id}/state`, {
          closed: !study.closed,
        });
        await render(root);
      } catch (e) {
        fail(e);
      }
    };
    if (study.is_test)
      root.querySelector("#remove-test-study").onclick = async () => {
        if (!confirm("Delete this software-test study and all of its events?"))
          return;
        try {
          await api(`/api/experiments/${study.id}/remove-test`, {});
          currentId = null;
          await render(root);
        } catch (e) {
          fail(e);
        }
      };
  }
  async function render(container) {
    root = container;
    const version = ++generation;
    clearInterval(refreshTimer);
    root.innerHTML = `<div class="panel"><h3>Start with a small randomized pilot</h3><p>Participants browse seven text stories: six filler stories and one randomly assigned target promo, placed randomly at positions 3–6. Every card offers the same continuation action. Choose the original public demo or a saved analysis shortlist. Saved script text is presented verbatim; candidates without following source text are omitted. No AI model simulates participants or generates labels.</p><form id="create-study" class="study-create"><label for="study-name-input">Study name</label><input id="study-name-input" maxlength="100" required value="Text-card pilot"><label for="study-source-input">Promo source</label><select id="study-source-input"><option value="">Original public demo · 3 variants</option></select><label class="study-test-check"><input type="checkbox" id="study-test-input"> Software test only · exclude from training</label><button class="button button-accent">Create study ↗</button></form></div><div id="study-error" class="alert error" role="alert" hidden></div><div class="section-bar"><h2>Reading pilots</h2><select id="study-select" aria-label="Choose a reading study"></select></div><div id="study-report"><div class="empty-state">Loading studies…</div></div>`;
    root.querySelector("#create-study").onsubmit = async (e) => {
      e.preventDefault();
      const button = e.target.querySelector("button");
      button.disabled = true;
      try {
        const s = await api("/api/experiments", {
          name: root.querySelector("#study-name-input").value,
          is_test: root.querySelector("#study-test-input").checked,
          source_run_id:
            root.querySelector("#study-source-input").value || null,
        });
        currentId = s.id;
        await render(root);
      } catch (e) {
        fail(e);
        button.disabled = false;
      }
    };
    try {
      const [{ studies }, status] = await Promise.all([
        api("/api/experiments"),
        api("/api/status"),
      ]);
      if (version !== generation || !active()) return;
      root.querySelector("#study-source-input").innerHTML += status.runs
        .filter((r) => r.summary.shortlisted > 0)
        .map(
          (r) =>
            `<option value="${escape(r.id)}">${escape(r.id)} · ${r.summary.shortlisted} shortlisted · ${escape(r.mode)}</option>`,
        )
        .join("");
      if (!studies.some((s) => s.id === currentId))
        currentId = studies.find((s) => !s.is_test)?.id || studies[0]?.id;
      const select = root.querySelector("#study-select");
      select.innerHTML = studies
        .map(
          (s) =>
            `<option value="${s.id}">${escape(s.name)}${s.is_test ? " · TEST" : ""}${s.closed ? " · CLOSED" : ""} · ${s.sessions} sessions</option>`,
        )
        .join("");
      select.disabled = !studies.length;
      select.value = currentId || "";
      select.onchange = () => {
        currentId = select.value;
        report().catch(fail);
      };
      if (currentId) await report();
      else
        root.querySelector("#study-report").innerHTML =
          '<div class="empty-state"><h2>Ready when your participants are.</h2><p>Create a study above. No responses are pre-filled.</p></div>';
      refreshTimer = setInterval(() => {
        if (!active()) return clearInterval(refreshTimer);
        report().catch(fail);
      }, 10000);
    } catch (e) {
      fail(e);
    }
  }
  return { render };
})();
