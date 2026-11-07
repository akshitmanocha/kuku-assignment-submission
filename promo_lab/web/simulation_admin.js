"use strict";
window.PromoSimulations = (() => {
  let root,
    selectedId,
    generation = 0;
  const esc = (value) =>
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
  const signed = (n) => `${n >= 0 ? "+" : ""}${(n * 100).toFixed(1)} pp`;
  async function api(path, body) {
    const r = await fetch(
      path,
      body === undefined
        ? {}
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
    );
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Request failed");
    return data;
  }
  function fail(e) {
    const node = root?.querySelector("#simulation-error");
    if (node) {
      node.textContent = e.message;
      node.hidden = false;
    }
  }
  function chart(days) {
    const w = 850,
      h = 250,
      left = 49,
      top = 20,
      bottom = 36,
      right = 20;
    const max =
      Math.max(
        0.35,
        ...days.flatMap((d) => [
          d.cumulative_control.rate,
          d.cumulative_policy.rate,
        ]),
      ) * 1.1;
    const x = (i) =>
      left + (i * (w - left - right)) / Math.max(1, days.length - 1);
    const y = (p) => top + (1 - p / max) * (h - top - bottom);
    const lines = [
      ["cumulative_policy", "#668c29"],
      ["cumulative_control", "#777f9e"],
    ];
    return `<svg class="simulation-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Synthetic cumulative qualified reading rates by simulated day. Green: epsilon-greedy; purple: uniform control.">
      ${[0, 1, 2, 3, 4]
        .map((i) => {
          const p = (max * i) / 4;
          return `<line x1="${left}" y1="${y(p)}" x2="${w - right}" y2="${y(p)}" stroke="#e0e5d9"/><text x="${left - 8}" y="${y(p) + 4}" text-anchor="end" fill="#76806f" font-size="10">${pct(p)}</text>`;
        })
        .join("")}
      ${lines.map(([key, color]) => `<polyline fill="none" stroke="${color}" stroke-width="2.5" points="${days.map((d, i) => `${x(i)},${y(d[key].rate)}`).join(" ")}"/>`).join("")}
      ${days
        .filter((d, i) => i === 0 || i === days.length - 1 || d.day % 3 === 0)
        .map(
          (d) =>
            `<text x="${x(d.day - 1)}" y="${h - 11}" text-anchor="middle" fill="#76806f" font-size="10">Day ${d.day}</text>`,
        )
        .join("")}
    </svg>`;
  }
  function show(r) {
    const s = r.summary,
      c = r.config;
    root.querySelector("#simulation-result").innerHTML = `
      <div class="simulation-banner"><strong>SYNTHETIC DEMO · NOT REAL AUDIENCE RESULTS</strong><p>${esc(r.disclaimer)}</p></div>
      <div class="simulation-steps"><span>01 · ${c.cold_start} random cold-start responses</span><span>02 · Fit candidate response model</span><span>03 · ${c.validation} held-out synthetic responses</span><span>04 · ${c.days} days of policy + control</span></div>
      <div class="stats-grid">${[
        [
          "Synthetic responses",
          s.synthetic_responses,
          `0 real responses generated · ${s.candidate_count} candidates`,
        ],
        [
          "Uniform control",
          pct(s.uniform_control.rate),
          `${s.uniform_control.successes}/${s.uniform_control.denominator} synthetic qualifications`,
        ],
        [
          "Learning policy",
          pct(s.epsilon_greedy.rate),
          `${s.epsilon_greedy.successes}/${s.epsilon_greedy.denominator} synthetic qualifications`,
        ],
        [
          "Simulated difference",
          signed(s.absolute_difference),
          "Percentage points · conditional on these assumed responses",
        ],
      ]
        .map(
          ([label, value, sub]) =>
            `<div class="stat"><div class="stat-top">${label}</div><div class="stat-value">${value}</div><div class="stat-bottom">${sub}</div></div>`,
        )
        .join("")}</div>
      <div class="panel"><div class="section-bar"><div><h3>Feedback changes which promos are selected</h3><p>Cumulative synthetic qualified reading rate. Green: learning policy. Purple: randomized control. Curves can rise or fall.</p></div><span class="badge badge-amber">${esc(c.scenario.toUpperCase())} · SEED ${c.seed}</span></div>${chart(r.daily)}<p>Cold start is 100% uniform. Online exploration starts at 60% and decreases to 20% by simulated day 5. The model updates once daily using only policy feedback; control and validation responses never train it.</p></div>
      <div class="report-grid"><div class="panel"><h3>Held-out synthetic prediction check</h3><p>${r.validation.count} independent synthetic viewers, the same candidate pool, before online updates. Lower scores are better.</p><div class="table-wrap"><table><thead><tr><th>Predictor</th><th>Brier score</th><th>Log loss</th></tr></thead><tbody><tr><td>Candidate response model</td><td>${r.validation.model.brier.toFixed(4)}</td><td>${r.validation.model.log_loss.toFixed(4)}</td></tr><tr><td>Constant cold-start baseline</td><td>${r.validation.constant_cold_start_baseline.brier.toFixed(4)}</td><td>${r.validation.constant_cold_start_baseline.log_loss.toFixed(4)}</td></tr></tbody></table></div><p>A Beta-Bernoulli model learns one response probability per candidate. It is a small working baseline, with no text embeddings or semantic understanding. New candidates require exploration.</p></div><div class="panel"><h3>What this can establish</h3><p>The pipeline can collect rows, fit probabilities, hold out data, log selection probabilities, select with epsilon-greedy and update from new feedback.</p><p>The response differences are simulator assumptions. This does not establish which Kuku promo real people prefer, or that production engagement will improve. Your existing real sessions are preserved and never mixed into this run.</p><p>Try <strong>No signal</strong>: every candidate has the same assumed success probability, so there is no expected advantage to learning. Try <strong>Changing trends</strong>: candidate appeal reverses halfway through, exposing lag in adaptation.</p></div></div>
      <div class="section-bar"><div><h2>Assumed appeal vs learned response</h2><p>Assumed values below belong only to the simulator. The model never receives them as features or labels.</p></div></div>
      <div class="table-wrap"><table><thead><tr><th>Candidate</th><th>Assumed initial probability</th><th>Assumed final probability</th><th>Learned final estimate</th></tr></thead><tbody>${r.candidates.map((candidate) => `<tr><td><strong>${esc(candidate.id)}</strong><small>${esc(candidate.title)}</small></td><td>${pct(candidate.assumed_initial_qualified_probability)}</td><td>${pct(candidate.assumed_final_qualified_probability)}</td><td>${pct(candidate.final_prediction)}</td></tr>`).join("")}</tbody></table></div>
      <details class="panel"><summary>Daily updates and randomized comparison</summary><div class="table-wrap"><table><thead><tr><th>Day</th><th>Exploration</th><th>Policy / control synthetic outcomes</th><th>Assumed expected policy / control</th><th>Exploited candidates</th></tr></thead><tbody>${r.daily.map((d) => `<tr><td>${d.day}</td><td>${pct(d.epsilon)}</td><td>${d.epsilon_greedy.successes}/${d.epsilon_greedy.denominator} / ${d.uniform_control.successes}/${d.uniform_control.denominator}</td><td>${pct(d.oracle_expected_policy)} / ${pct(d.oracle_expected_control)}</td><td>${d.exploited_candidates.map(esc).join(", ")}</td></tr>`).join("")}</tbody></table></div></details>
      <div class="panel"><h3>Assumptions and reproducibility</h3><p>Source: ${esc(r.source.name)} · Simulator ${esc(r.simulator_version)} · Seed ${c.seed}. Synthetic time is simulated days, not live collection dates. Outcome generation is local and makes no LLM calls.</p><ul>${r.assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul><p>All generated rows carry <code>data_source=synthetic_simulator</code>, <code>is_synthetic=true</code> and <code>training_eligible_for_real_model=false</code>. Download these as demo artifacts, not human research results.</p><div class="study-actions">${["synthetic_responses.jsonl", "synthetic_responses.csv", "report.json", "model.json"].map((artifact) => `<a class="button button-small" href="/api/simulations/${r.id}/export?artifact=${artifact}">↓ SYNTHETIC ${artifact}</a>`).join("")}</div></div>`;
  }
  async function load(id, version = generation) {
    const r = await api(`/api/simulations/${id}`);
    if (version !== generation || !root.querySelector("#simulation-result"))
      return;
    selectedId = id;
    show(r);
  }
  async function render(container) {
    root = container;
    const version = ++generation;
    root.innerHTML = `<div class="simulation-banner"><strong>SYNTHETIC RESPONSES · SEPARATE FROM YOUR REAL EXPERIMENT</strong><p>A runnable demo of the feedback loop. No real participant records are created or changed. Synthetic improvement is conditional on assumed candidate differences.</p></div><div class="panel"><h3>Run a reproducible simulation</h3><form id="simulation-form" class="simulation-form"><label>Candidate source<select id="simulation-source"><option value="">Original public demo</option></select></label><label>Scenario<select id="simulation-scenario"><option value="stationary">Different candidate appeal</option><option value="no_signal">No signal · equal candidate appeal</option><option value="drift">Changing trends · appeal reverses</option></select></label><label>Random seed<input id="simulation-seed" type="number" min="0" max="2147483647" value="42" required></label><label>Simulated days<input id="simulation-days" type="number" min="2" max="30" value="14" required></label><button class="button button-accent" id="run-simulation">Generate synthetic responses + train ↗</button></form><p>400 random cold-start viewers · 200 held-out validation viewers · 150 viewers per arm per day · Beta-Bernoulli candidate model. Every viewer and outcome here is generated.</p></div><div id="simulation-error" class="alert error" role="alert" hidden></div><div class="section-bar"><h2>Saved synthetic runs</h2><select id="simulation-select" aria-label="Choose a synthetic run"></select></div><div id="simulation-result"><div class="empty-state"><h2>Ready to demonstrate the loop.</h2><p>Select a source and generate a labeled synthetic run.</p></div></div>`;
    root.querySelector("#simulation-form").onsubmit = async (e) => {
      e.preventDefault();
      const button = root.querySelector("#run-simulation");
      button.disabled = true;
      button.textContent = "Generating synthetic responses…";
      try {
        const result = await api("/api/simulations", {
          study_id: root.querySelector("#simulation-source").value || null,
          scenario: root.querySelector("#simulation-scenario").value,
          seed: Number(root.querySelector("#simulation-seed").value),
          days: Number(root.querySelector("#simulation-days").value),
        });
        selectedId = result.id;
        const select = root.querySelector("#simulation-select");
        const option = document.createElement("option");
        option.value = result.id;
        option.textContent = `SYNTHETIC · ${result.config.scenario} · seed ${result.config.seed} · ${result.source.name}`;
        select.prepend(option);
        select.disabled = false;
        select.value = result.id;
        show(result);
      } catch (e) {
        fail(e);
      } finally {
        if (root.querySelector("#run-simulation")) {
          root.querySelector("#run-simulation").disabled = false;
          root.querySelector("#run-simulation").textContent =
            "Generate synthetic responses + train ↗";
        }
      }
    };
    try {
      const [{ studies }, { simulations }] = await Promise.all([
        api("/api/experiments"),
        api("/api/simulations"),
      ]);
      if (version !== generation || !root.querySelector("#simulation-result"))
        return;
      const sources = studies.filter(
        (s) => !s.is_test && s.candidate_count >= 2,
      );
      root.querySelector("#simulation-source").innerHTML += sources
        .map(
          (s) =>
            `<option value="${s.id}">${esc(s.name)} · ${s.candidate_count} candidates</option>`,
        )
        .join("");
      if (sources.length)
        root.querySelector("#simulation-source").value = sources[0].id;
      const select = root.querySelector("#simulation-select");
      select.innerHTML = simulations
        .map(
          (s) =>
            `<option value="${s.id}">SYNTHETIC · ${esc(s.config.scenario)} · seed ${s.config.seed} · ${esc(s.source.name)}</option>`,
        )
        .join("");
      select.disabled = !simulations.length;
      if (!simulations.some((s) => s.id === selectedId))
        selectedId = simulations[0]?.id;
      select.value = selectedId || "";
      select.onchange = () => load(select.value).catch(fail);
      if (selectedId) await load(selectedId, version);
    } catch (e) {
      fail(e);
    }
  }
  return { render };
})();
