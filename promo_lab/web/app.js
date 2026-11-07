"use strict";
const $ = (s) => document.querySelector(s);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const number = (value) => Number(value || 0).toLocaleString();
const tc = (ms) => {
  if (ms % 10) {
    return `${String(Math.floor(ms / 60000)).padStart(2, "0")}:${String(Math.floor((ms % 60000) / 1000)).padStart(2, "0")}.${String(ms % 1000).padStart(3, "0")}`;
  }
  const n = Math.round(ms / 10);
  return `${String(Math.floor(n / 6000)).padStart(2, "0")}:${String(Math.floor((n % 6000) / 100)).padStart(2, "0")}.${String(n % 100).padStart(2, "0")}`;
};
const percent = (value) =>
  value == null ? "—" : `${(value * 100).toFixed(1)}%`;
const state = {
  status: null,
  result: null,
  runId: null,
  view: [
    "discover",
    "episodes",
    "evaluation",
    "history",
    "method",
    "experiments",
    "simulations",
  ].includes(location.hash.slice(1))
    ? location.hash.slice(1)
    : "discover",
  selected: null,
  scope: "shortlist",
  episode: "all",
  search: "",
  limit: 35,
  sourceFilter: "all",
  poll: null,
  providerInitialized: false,
};
const titles = {
  simulations: [
    "Watch the feedback loop.",
    "Synthetic responses → response model → exploration and exploitation. A mechanics demonstration.",
  ],
  experiments: [
    "Let the audience decide.",
    "A randomized reading pilot. Real interactions, ready for later model training.",
  ],
  discover: [
    "Find the moment.",
    "The hook. The tension. The cut that leaves them wanting more.",
  ],
  episodes: [
    "Every episode. Every beat.",
    "A complete source inventory, with processing coverage and timing concerns.",
  ],
  evaluation: [
    "Inspect the evidence.",
    "Technical checks are measured. Audience performance is still an open question.",
  ],
  history: [
    "Keep the whole trail.",
    "Revisit analyses and export their original results.",
  ],
  method: [
    "A shortlist you can question.",
    "Source-grounded discovery, transparent checks, and honest limits.",
  ],
};

async function api(path, options) {
  const r = await fetch(path, options);
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || `Request failed (${r.status})`);
  return data;
}
function error(message) {
  $("#error").textContent = message;
  $("#error").hidden = !message;
}
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  setTimeout(() => ($("#toast").hidden = true), 3000);
}
function download(artifact) {
  if (state.runId)
    location.href = `/api/runs/${encodeURIComponent(state.runId)}?artifact=${encodeURIComponent(artifact)}&download=1`;
}

async function refreshStatus() {
  state.status = await api("/api/status");
  const provider = $("#provider");
  const previous = provider.value;
  provider.innerHTML = Object.entries(state.status.providers)
    .map(
      ([key, p]) =>
        `<option value="${key}" ${!p.ready ? "disabled" : ""}>${esc(p.label)}${p.model ? " · " + esc(p.model) : ""}${!p.ready ? " · not configured" : ""}</option>`,
    )
    .join("");
  provider.value =
    !state.providerInitialized && state.status.providers.openai.ready
      ? "openai"
      : state.status.providers[previous]?.ready
        ? previous
        : state.status.providers.openai.ready
          ? "openai"
          : "offline";
  state.providerInitialized = true;
  $('#source option[value="pack"]').disabled = !state.status.pack_available;
  if (!state.status.pack_available && $("#source").value === "pack")
    $("#source").value = "sample";
  providerHint();
}
function providerHint() {
  const mode = $("#provider").value,
    p = state.status?.providers[mode];
  $("#provider-hint").textContent =
    mode === "offline"
      ? "Reproducible rules. No model calls and no audience predictions."
      : `${p?.model || "Configured model"} · proposes source cuts, then critiques selected content without episode summaries. Free-tier rate limits may slow full-pack runs.`;
  const restricted = p?.public_inputs_only && !p?.confidential_input_authorized;
  $('#source option[value="pack"]').disabled =
    !state.status?.pack_available || !!restricted;
  if (restricted && $("#source").value === "pack")
    $("#source").value = "sample";
  $("#upload-field").hidden = $("#source").value !== "upload";
  $("#public-input-option").hidden =
    !restricted || $("#source").value !== "upload";
  if (restricted)
    $("#provider-hint").textContent =
      `${p.model} · public, non-confidential inputs only. NVIDIA's free endpoint logs inputs for improvement. Use the original demo; existing Qwen results remain in Run history.`;
  if (p?.confidential_input_authorized)
    $("#provider-hint").textContent +=
      " You have explicitly authorized confidential Kuku processing with this endpoint; the scripts remain confidential.";
}

async function loadRun(id) {
  error("");
  $("#view-content").innerHTML =
    '<div class="empty-state"><div class="spinner"></div><p>Loading source timelines and analysis…</p></div>';
  state.result = await api(`/api/runs/${encodeURIComponent(id)}`);
  state.runId = id;
  state.selected =
    state.result.shortlist_ids[0] ||
    state.result.candidates.find((c) => c.validation.valid)?.id;
  state.limit = 35;
  state.episode = "all";
  state.search = "";
  state.scope = "shortlist";
  $("#export-bundle").disabled = false;
  render();
}

function render() {
  const r = state.result;
  const [title, subtitle] = titles[state.view];
  $("#page-title").textContent = title;
  $("#page-subtitle").textContent = subtitle;
  $("#breadcrumb").textContent = {
    discover: "Discover promos",
    episodes: "Episode library",
    evaluation: "Quality report",
    history: "Run history",
    experiments: "Reading experiment",
    simulations: "Synthetic demo",
    method: "How it works",
  }[state.view];
  document
    .querySelectorAll("[data-view]")
    .forEach((b) =>
      b.classList.toggle("active", b.dataset.view === state.view),
    );
  $("#nav-count").textContent = r?.summary.shortlisted || 0;
  const experimentView = ["experiments", "simulations"].includes(state.view);
  $("#stats").hidden = experimentView;
  $("#run-context").hidden = experimentView;
  $("#export-bundle").hidden = experimentView;
  if (state.view === "experiments")
    return window.PromoExperiments.render($("#view-content"));
  if (state.view === "simulations")
    return window.PromoSimulations.render($("#view-content"));
  $("#stats").innerHTML = r
    ? [
        [
          "Episodes analyzed",
          number(r.summary.episodes),
          `${number(r.summary.events)} timestamped source entries`,
          "▤",
        ],
        [
          "Candidate cuts",
          number(r.summary.candidates),
          `${number(r.summary.distinct_candidates)} distinct valid intervals`,
          "⌁",
        ],
        [
          "Source validity",
          percent(r.evaluation.shortlist.valid_rate),
          r.summary.shortlisted
            ? "On shortlisted cuts · code-checked"
            : "No shortlisted cuts to measure",
          "✓",
        ],
        [
          "Your shortlist",
          number(r.summary.shortlisted),
          `Top ${r.config.shortlist_percent}% · minimum quality gates`,
          "↗",
        ],
      ]
        .map(
          ([label, value, sub, icon]) =>
            `<div class="stat"><div class="stat-top">${label}<span class="stat-icon">${icon}</span></div><div class="stat-value">${value}</div><div class="stat-bottom">${sub}</div></div>`,
        )
        .join("")
    : "";
  $("#run-context").innerHTML = r
    ? `<span><span class="badge ${r.mode === "offline" ? "badge-amber" : "badge-purple"}">${r.mode === "offline" ? "OFFLINE BASELINE" : r.partial ? "AI ASSISTED · PARTIAL" : "AI ASSISTED"}</span> &nbsp; ${esc(r.model || "Deterministic editorial rules")} · ${r.summary.ai_calls} logical model calls (${r.model_journal.filter((call) => call.cached).length} cached) · ${r.summary.seconds.toFixed(1)}s this run</span><span>No audience data · scores are editorial estimates</span>`
    : "";
  if (state.view === "method") return renderMethod();
  if (state.view === "history") return renderHistory();
  if (!r) {
    $("#view-content").innerHTML =
      `<div class="empty-state"><div class="empty-symbol">◈</div><h2>Your next great cut starts here.</h2><p>Bring a screenplay. Get timestamped promo recommendations, source evidence, and the reasons to inspect them.</p><button class="button button-accent" id="empty-run">Start an analysis ↗</button></div>`;
    $("#empty-run").onclick = openDialog;
    return;
  }
  if (state.view === "episodes") return renderEpisodes();
  if (state.view === "evaluation") return renderEvaluation();
  renderDiscover();
}

function filteredCandidates() {
  const r = state.result;
  return r.candidates.filter(
    (c) =>
      (state.scope === "all" ||
        (state.scope === "shortlist"
          ? c.shortlisted
          : state.scope === "eligible"
            ? c.eligible
            : c.validation.valid)) &&
      (state.episode === "all" ||
        c.segments.some((s) => s.episode_id === state.episode)) &&
      (!state.search ||
        `${c.title} ${c.assessment.hook} ${c.assessment.cliffhanger}`
          .toLowerCase()
          .includes(state.search.toLowerCase())),
  );
}
function renderDiscover() {
  const r = state.result;
  $("#view-content").innerHTML =
    `<div class="section-bar"><div><h2>The editorial shortlist <span class="badge badge-green">${r.summary.shortlisted} cuts</span></h2><p>Source moments, ranked for review. Click a cut to inspect the evidence.</p></div><div class="filters"><input id="search" type="search" placeholder="Search moments…" aria-label="Search moments" value="${esc(state.search)}"><select id="scope" aria-label="Candidate scope"><option value="shortlist">Shortlisted</option><option value="eligible">Passed quality gates</option><option value="valid">All valid candidates</option><option value="all">All candidates + failures</option></select><select id="episode-filter" aria-label="Episode filter"><option value="all">All episodes</option>${r.episodes.map((e) => `<option value="${e.id}">${esc(e.title)}</option>`).join("")}</select></div></div><div class="workspace-grid"><div><div class="candidate-list" id="candidate-list"></div><button class="button more-button" id="show-more" hidden>Show more candidates</button></div><div id="inspector"></div></div>`;
  $("#scope").value = state.scope;
  $("#episode-filter").value = state.episode;
  $("#scope").onchange = (e) => {
    state.scope = e.target.value;
    state.limit = 35;
    renderCandidateList();
  };
  $("#episode-filter").onchange = (e) => {
    state.episode = e.target.value;
    state.limit = 35;
    renderCandidateList();
  };
  $("#search").oninput = (e) => {
    state.search = e.target.value;
    state.limit = 35;
    renderCandidateList();
  };
  $("#show-more").onclick = () => {
    state.limit += 35;
    renderCandidateList();
  };
  renderCandidateList();
}
function renderCandidateList() {
  const list = filteredCandidates();
  if (!list.some((c) => c.id === state.selected)) state.selected = list[0]?.id;
  $("#candidate-list").innerHTML = list.length
    ? list
        .slice(0, state.limit)
        .map(
          (c) =>
            `<button class="candidate-card ${c.id === state.selected ? "selected" : ""}" data-candidate="${c.id}" aria-pressed="${c.id === state.selected}"><div class="candidate-meta"><span class="rank">${c.rank ? "#" + String(c.rank).padStart(2, "0") : "CUT"}</span><span>EP ${c.segments.map((s) => String(s.episode_number).padStart(2, "0")).join(" + ")}</span><span>·</span><span>${c.duration_seconds.toFixed(1)}s</span><span class="badge ${c.validation.valid ? "badge-green" : "badge-red"}">${c.validation.valid ? "Valid source" : "Invalid cut"}</span></div><h3>${esc(c.title)}</h3><div class="candidate-sub">${c.assessment.method === "llm_newcomer_critique" ? "AI newcomer assessment" : "Rules estimate · review required"}${c.segments.length > 1 ? " · assembled" : ""}</div><div class="candidate-foot"><span class="timecode">${esc(c.segments[0].start)} → ${esc(c.segments[0].end)}${c.segments.length > 1 ? " +" : ""}</span><span class="candidate-score">${c.score}<small> / 100</small></span></div></button>`,
        )
        .join("")
    : '<div class="empty-state"><h2>No cuts in this view.</h2><p>Try another episode or candidate scope. The system does not pad the shortlist when quality gates fail.</p></div>';
  $("#show-more").hidden = list.length <= state.limit;
  document.querySelectorAll("[data-candidate]").forEach(
    (b) =>
      (b.onclick = () => {
        state.selected = b.dataset.candidate;
        renderCandidateList();
      }),
  );
  renderInspector();
}

function candidateEvents(c) {
  let offset = 0;
  const events = [];
  for (let i = 0; i < c.segments.length; i++) {
    const s = c.segments[i],
      ep = state.result.episodes.find((e) => e.id === s.episode_id);
    for (const e of ep.events) {
      if (e.start_ms < s.end_ms && e.end_ms > s.start_ms)
        events.push({
          ...e,
          episode_id: ep.id,
          segment_index: i,
          playback_start_ms: offset + Math.max(0, e.start_ms - s.start_ms),
          playback_end_ms: offset + Math.min(s.end_ms, e.end_ms) - s.start_ms,
          partial: e.start_ms < s.start_ms || e.end_ms > s.end_ms,
        });
    }
    offset += s.end_ms - s.start_ms;
  }
  return events;
}
function renderInspector() {
  const c = state.result.candidates.find((c) => c.id === state.selected);
  if (!c) {
    $("#inspector").innerHTML = "";
    return;
  }
  const a = c.assessment;
  const hook = a.hook.length > 260 ? a.hook.slice(0, 257) + "…" : a.hook;
  const events = candidateEvents(c);
  $("#inspector").innerHTML =
    `<article class="inspector"><div class="inspector-top"><strong>Cut inspector</strong><span class="badge badge-purple">${esc(c.id)}</span></div><div class="script-stage"><div class="stage-top"><span>SCREENPLAY PREVIEW</span><span>TEXT ONLY</span></div><div class="stage-label">OPENING MOMENT</div><blockquote>${esc(hook)}</blockquote><div class="stage-bottom"><span>NO VIDEO GENERATED</span><span class="timecode">${esc(c.segments[0].start)} <span> / </span> ${c.duration_seconds.toFixed(1)}s</span></div></div><div class="detail-body"><h2 class="detail-title">${esc(c.title)}</h2><div class="segments">${c.segments.map((s, i) => `<span class="segment-chip">${i + 1}. EP ${s.episode_number} · ${s.start} — ${s.end}</span>`).join("")}</div>${[
      ["The hook", a.hook],
      ["The ending", a.cliffhanger],
      ["The unanswered question", a.unanswered_question],
      ["Why this cut", a.why],
    ]
      .map(
        ([label, text], i) =>
          `<div class="evidence-row"><span class="evidence-number">${i + 1}</span><div><h3>${label}</h3><p>${esc(text)}</p></div></div>`,
      )
      .join("")}<div class="score-grid">${Object.entries(a.scores)
      .map(
        ([key, value]) =>
          `<div><div class="score-label"><span>${esc(key.replaceAll("_", " "))}</span><span>${value}/3</span></div><div class="score-track"><div class="score-mark" data-width="${(value / 3) * 100}"></div></div></div>`,
      )
      .join(
        "",
      )}</div><p class="quality-note">Equal-weight editorial rubric. This ${a.method === "llm_newcomer_critique" ? "AI judgment" : "keyword-based estimate"} is not a calibrated prediction of viewer behavior.</p><div class="micro-heading">SOURCE VALIDATION</div><div class="checks">${Object.entries(
      c.validation.checks,
    )
      .map(
        ([k, v]) =>
          `<span class="badge ${v ? "badge-green" : "badge-red"}">${v ? "✓" : "×"} ${esc(k.replaceAll("_", " "))}</span>`,
      )
      .join(
        "",
      )}</div>${c.validation.errors.length ? `<div class="alert error">${c.validation.errors.map(esc).join("<br>")}</div>` : ""}<details><summary class="micro-heading">Review concerns (${a.risks.length})</summary><ul class="warning-list">${a.risks.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></details><details class="source-panel" open><summary>Selected source timeline <span class="source-count">${events.length} overlapping entries</span></summary><div class="timeline"><div class="timeline-label"><span>Playback time · dialogue and action overlap</span><span>${c.duration_seconds.toFixed(1)}s</span></div><div class="timeline-lane dialogue" aria-label="Dialogue intervals">${events
      .filter((e) => e.kind === "dialogue")
      .map(
        (e) =>
          `<div class="timeline-mark" data-left="${(e.playback_start_ms / c.validation.duration_ms) * 100}" data-width="${((e.playback_end_ms - e.playback_start_ms) / c.validation.duration_ms) * 100}"></div>`,
      )
      .join(
        "",
      )}</div><div class="timeline-lane" aria-label="Action intervals">${events
      .filter((e) => e.kind === "action")
      .map(
        (e) =>
          `<div class="timeline-mark" data-left="${(e.playback_start_ms / c.validation.duration_ms) * 100}" data-width="${((e.playback_end_ms - e.playback_start_ms) / c.validation.duration_ms) * 100}"></div>`,
      )
      .join(
        "",
      )}</div></div><div class="source-toolbar">${["all", "dialogue", "action", "camera", "sound"].map((x) => `<button class="pill ${state.sourceFilter === x ? "active" : ""}" data-source-filter="${x}">${x === "all" ? "All entries" : x[0].toUpperCase() + x.slice(1)}</button>`).join("")}</div><div id="source-events"></div></details><div class="section-bar"><span class="muted">Verify against the original episode before editing.</span><button class="button button-small" id="copy-cut">Copy edit decision</button></div></div></article>`;
  document
    .querySelectorAll("[data-width]")
    .forEach((el) => (el.style.width = `${Number(el.dataset.width)}%`));
  document
    .querySelectorAll("[data-left]")
    .forEach((el) => (el.style.left = `${Number(el.dataset.left)}%`));
  document.querySelectorAll("[data-source-filter]").forEach(
    (b) =>
      (b.onclick = () => {
        state.sourceFilter = b.dataset.sourceFilter;
        document
          .querySelectorAll("[data-source-filter]")
          .forEach((x) => x.classList.toggle("active", x === b));
        renderSource(events);
      }),
  );
  $("#copy-cut").onclick = async () => {
    const text = [
      c.title,
      ...c.segments.map(
        (s, i) =>
          `${i + 1}. Episode ${s.episode_number}: ${s.start} – ${s.end}`,
      ),
      `Hook: ${a.hook}`,
      `Ending: ${a.cliffhanger}`,
      `Why: ${a.why}`,
    ].join("\n");
    try {
      await navigator.clipboard.writeText(text);
      toast("Edit decision copied");
    } catch {
      toast("Clipboard unavailable; use the CSV export.");
    }
  };
  renderSource(events);
}
function renderSource(events) {
  $("#source-events").innerHTML =
    events
      .filter(
        (e) => state.sourceFilter === "all" || e.kind === state.sourceFilter,
      )
      .map(
        (e) =>
          `<div class="source-event ${e.kind}"><div><div class="timecode">${tc(e.start_ms)}<br>${tc(e.end_ms)}</div><div class="event-id">${esc(e.id)}</div></div><div><div class="event-label">${esc(e.label)} ${e.partial ? '<span class="badge badge-amber">partial visual/audio interval</span>' : ""}</div><p>${esc(e.text)}</p></div></div>`,
      )
      .join("") ||
    '<p class="muted">No entries of this type in the selected interval.</p>';
}

function renderEpisodes() {
  const r = state.result;
  $("#view-content").innerHTML =
    `<div class="section-bar"><div><h2>Source inventory</h2><p>Processing every episode does not mean recommending a promo from every episode.</p></div><button class="button" id="coverage-export">↓ Coverage JSON</button></div><div class="table-wrap"><table><thead><tr><th>Episode</th><th>Duration</th><th>Entries</th><th>Candidate cuts</th><th>Eligible</th><th>AI reviewed</th><th>Shortlisted</th><th>Timing flags</th><th></th></tr></thead><tbody>${r.coverage
      .map((row) => {
        const ep = r.episodes.find((e) => e.id === row.episode_id);
        return `<tr><td><strong>${esc(ep.title)}</strong></td><td class="timecode">${tc(ep.duration_ms)}</td><td>${row.events}</td><td>${number(row.candidates)}</td><td>${row.eligible}</td><td>${row.ai_assessed ?? "—"}</td><td>${row.shortlisted}</td><td><span class="badge ${row.warnings ? "badge-amber" : "badge-green"}">${row.warnings || "None"}</span></td><td><button class="link-button" data-open-episode="${ep.id}">Inspect cuts ↗</button></td></tr>`;
      })
      .join("")}</tbody></table></div>`;
  $("#coverage-export").onclick = () => download("episode_coverage.json");
  document.querySelectorAll("[data-open-episode]").forEach(
    (b) =>
      (b.onclick = () => {
        state.view = "discover";
        state.scope = "valid";
        state.episode = b.dataset.openEpisode;
        state.search = "";
        render();
      }),
  );
}
function renderEvaluation() {
  const r = state.result,
    e = r.evaluation;
  $("#view-content").innerHTML =
    `<div class="section-bar"><div><h2>Measured checks, explicit limits</h2><p>Baseline: a roughly 30-second interval from each episode’s first spoken line, without boundary refinement.</p></div><button class="button" id="evaluation-export">↓ Report JSON</button></div><div class="report-grid"><div class="panel"><h3>Source & duration validity</h3><div class="metric-comparison"><div><div class="value">${percent(e.baseline.valid_rate)}</div><div class="label">Fixed-window baseline · n=${e.baseline.count}</div></div><div><div class="value highlight">${percent(e.shortlist.valid_rate)}</div><div class="label">Shortlist · n=${e.shortlist.count}</div></div></div><p>Checks source bounds, referenced boundary IDs, duration, chronology, and complete dialogue.</p></div><div class="panel"><h3>Dialogue cut-through rate</h3><div class="metric-comparison"><div><div class="value">${percent(e.baseline.dialogue_cut_rate)}</div><div class="label">Fixed-window baseline</div></div><div><div class="value highlight">${percent(e.shortlist.dialogue_cut_rate)}</div><div class="label">Shortlist</div></div></div><p>Camera endpoints can fall inside spoken lines. The pipeline checks overlapping dialogue before accepting a cut.</p></div><div class="panel"><h3>Audience performance</h3><div class="metric-comparison"><div><div class="value">—</div><div class="label">Qualified continuation</div></div><div><div class="value">—</div><div class="label">Human acceptance</div></div></div><p>This editorial analysis contains no audience measurements. Inspect Reading experiment for real text interactions and Synthetic demo for generated feedback. Neither editorial scores nor synthetic rewards establish customer lift.</p></div><div class="panel"><h3>Coverage & model use</h3><p>${r.summary.episodes} episodes · ${number(r.summary.events)} source entries<br>${number(r.summary.valid_candidates)} valid intervals · ${number(r.summary.distinct_candidates)} distinct<br>${r.summary.ai_assessed} AI-assessed candidates · ${r.summary.ai_calls} logical calls<br>${r.summary.parse_warnings} timing flags · ${r.rejected_proposals.length} malformed AI proposals</p></div></div><div class="alert note">${esc(e.interpretation)}</div><div class="panel"><h3>Observed failure examples</h3><p>These are actual rejected cuts from this run, not invented customer outcomes.</p>${
      e.failures
        .slice(0, 6)
        .map(
          (c) =>
            `<div class="failed-sample"><span class="run-name">${esc(c.id)}</span> · ${c.segments.map((s) => `EP ${s.episode_number} ${s.start}–${s.end}`).join(" + ")}<br><span class="badge badge-red">${esc(c.errors.join(" · "))}</span></div>`,
        )
        .join("") ||
      "<p>No technically invalid candidates were generated in this run. This does not establish semantic quality.</p>"
    }</div><div class="panel"><h3>Run notices</h3><ul>${r.notices.map((n) => `<li>${esc(n)}</li>`).join("")}</ul></div>`;
  $("#evaluation-export").onclick = () => download("evaluation.json");
}
function renderHistory() {
  const runs = state.status?.runs || [];
  $("#view-content").innerHTML =
    `<div class="section-bar"><div><h2>Saved analyses</h2><p>Private raw outputs remain in this workspace. Exports include source text.</p></div></div>${runs.length ? `<div class="table-wrap"><table><thead><tr><th>Run</th><th>Engine</th><th>Episodes</th><th>Shortlist</th><th>Created</th><th></th></tr></thead><tbody>${runs.map((r) => `<tr><td class="run-name">${esc(r.id)}</td><td>${esc(r.mode)}</td><td>${r.summary.episodes}</td><td>${r.summary.shortlisted}</td><td>${esc(new Date(r.created_at).toLocaleString())}</td><td><button class="link-button" data-open-run="${esc(r.id)}">Open analysis ↗</button></td></tr>`).join("")}</tbody></table></div>` : '<div class="empty-state"><h2>No analyses yet.</h2><p>Start with the original demo or your screenplay pack.</p></div>'}`;
  document.querySelectorAll("[data-open-run]").forEach(
    (b) =>
      (b.onclick = async () => {
        state.view = "discover";
        try {
          await loadRun(b.dataset.openRun);
        } catch (e) {
          error(e.message);
        }
      }),
  );
}
function renderMethod() {
  $("#view-content").innerHTML =
    `<div class="panel"><h3>01 / Read the source, preserve the evidence</h3><p>Episodes are parsed into overlapping dialogue, action, camera, and sound intervals. Timestamps use integer milliseconds. Each proposal points back to original source events; episode summaries never stand in for what a newcomer sees.</p></div><div class="panel"><h3>02 / Search broadly, then inspect the cut</h3><p>Search plausible event boundaries for 20–60-second intervals. With an AI provider, propose up to three additional promos per episode and independently critique one finalist using candidate-only content. Assemblies use at most three chronological segments. Unreviewed AI-mode candidates cannot enter the AI shortlist.</p></div><div class="panel"><h3>03 / Validate, score, and group variants</h3><p>Code validates source IDs, duration, complete dialogue and chronology. Six rubric dimensions use anchored 0–3 estimates: hook, comprehension, stakes, progression, cliffhanger, and cut quality. Equal-weight totals are editorial scores, not probabilities. Hook, comprehension, and cliffhanger must each reach 2. Overlapping cuts are grouped with a 0.5 temporal IoU heuristic; semantic duplicates can remain.</p></div><div class="panel"><h3>04 / Keep uncertainty visible</h3><p>Offline mode uses disclosed keyword rules. AI mode uses a separately prompted newcomer assessment, not independent ground truth. Neither measures actual audience engagement. Camera performance, acting, precise word timing, and edit continuity require footage and human inspection. Raw prompts, model outputs, rejected proposals, and source hashes are exportable.</p></div><div class="panel"><h3>05 / Collect real reading feedback</h3><p>The Reading experiment inserts a random target promo among ordinary text stories. With consent, it records foreground reading time, skips and continuation choices. Repeated views remain separate; interrupted outcomes can remain unknown. Reading is a proxy, not video engagement.</p></div><div class="panel"><h3>06 / Demonstrate the learning loop</h3><p>The separate Synthetic demo fits a candidate-level response model, holds out validation data and compares daily epsilon-greedy updates with random control. Every generated row is labeled synthetic. A real-audience model, text embeddings, production deployment, encoder fine-tuning and contrastive learning remain future work.</p></div>`;
}

function openDialog() {
  error("");
  $("#run-dialog").showModal();
}
$("#new-run").onclick = openDialog;
$("#close-dialog").onclick = () => $("#run-dialog").close();
$("#provider").onchange = providerHint;
$("#source").onchange = providerHint;
$("#files").onchange = () =>
  ($("#file-summary").textContent = [...$("#files").files]
    .map((f) => f.name)
    .join(", "));
$("#export-bundle").onclick = () => download("bundle.zip");
document.querySelectorAll("[data-view]").forEach(
  (b) =>
    (b.onclick = async () => {
      state.view = b.dataset.view;
      history.replaceState(
        null,
        "",
        state.view === "discover" ? "/" : `/#${state.view}`,
      );
      if (state.view === "history")
        try {
          await refreshStatus();
        } catch (e) {
          error(e.message);
        }
      render();
    }),
);
$("#run-form").onsubmit = async (event) => {
  event.preventDefault();
  const button = $("#start-run");
  button.disabled = true;
  error("");
  try {
    const body = {
      source: $("#source").value,
      provider: $("#provider").value,
      shortlist_percent: Number($("#shortlist-percent").value),
      allow_partial: $("#allow-partial").checked,
      public_input: $("#public-input").checked,
    };
    const ep = $("#episode-number").value;
    if (ep) body.episode_ids = [`E${String(Number(ep)).padStart(3, "0")}`];
    if (body.source === "upload") {
      const files = [...$("#files").files];
      if (!files.length)
        throw new Error("Choose a .txt screenplay or .zip archive first.");
      if (files.reduce((n, f) => n + f.size, 0) > 15000000)
        throw new Error("Upload exceeds 15 MB.");
      body.files = await Promise.all(
        files.map(
          (file) =>
            new Promise((resolve, reject) => {
              const reader = new FileReader();
              reader.onload = () =>
                resolve({
                  name: file.name,
                  data: String(reader.result).split(",")[1],
                });
              reader.onerror = () => reject(new Error("Could not read file"));
              reader.readAsDataURL(file);
            }),
        ),
      );
    }
    const { job_id } = await api("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    $("#run-dialog").close();
    pollJob(job_id);
  } catch (e) {
    error(e.message);
    $("#run-dialog").close();
  } finally {
    button.disabled = false;
  }
};
async function pollJob(id) {
  $("#run-strip").hidden = false;
  $("#new-run").disabled = true;
  try {
    const job = await api(`/api/jobs/${id}`);
    $("#progress-message").textContent = job.message;
    $("#progress-count").textContent = `${job.done} / ${job.total}`;
    $("#progress-fill").style.width =
      `${job.total ? (job.done / job.total) * 100 : 0}%`;
    if (job.status === "complete") {
      $("#run-strip").hidden = true;
      $("#new-run").disabled = false;
      state.view = "discover";
      await refreshStatus();
      await loadRun(job.run_id);
      toast("Analysis complete. Inspect the source before editing.");
    } else if (job.status === "failed") {
      $("#run-strip").hidden = true;
      $("#new-run").disabled = false;
      error(job.message);
    } else state.poll = setTimeout(() => pollJob(id), 1200);
  } catch (e) {
    $("#new-run").disabled = false;
    $("#run-strip").hidden = true;
    error(e.message);
  }
}
(async () => {
  try {
    await refreshStatus();
    const preferred =
      state.status.runs.find((r) => r.mode !== "offline") ||
      state.status.runs[0];
    if (preferred) await loadRun(preferred.id);
    else render();
    if (state.status.active_job) pollJob(state.status.active_job);
  } catch (e) {
    error(e.message);
    render();
  }
})();
