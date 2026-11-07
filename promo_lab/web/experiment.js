"use strict";
(() => {
  const $ = (s) => document.querySelector(s);
  const studyId = location.pathname.split("/")[2];
  const storageKey = `storybreak:v1:${studyId}`;
  const leaseKey = `${storageKey}:lease`;
  const tabId = crypto.randomUUID();
  let saved = {},
    data,
    current,
    running = false,
    sending = false,
    blocked = false;
  let baseElapsed = 0,
    baseClock = 0,
    seq = 0,
    lastTick = performance.now();
  let readerReady = false,
    movingReason = "next",
    lastHeartbeat = 0;
  const ratios = new Map();
  const readSaved = () => JSON.parse(localStorage.getItem(storageKey) || "{}");
  function persist() {
    localStorage.setItem(storageKey, JSON.stringify(saved));
  }
  function notice(message, welcome = false) {
    const node = $(welcome ? "#welcome-error" : "#feed-error");
    node.textContent = message;
    node.hidden = !message;
  }
  async function request(path, options = {}) {
    const response = await fetch(path, options);
    const body = await response.json();
    if (!response.ok)
      throw new Error(body.error || `Request failed (${response.status})`);
    return body;
  }
  function post(path, body) {
    return request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }
  const sessionPath = (suffix = "") =>
    `/api/experiment-sessions/${saved.sessionId}${suffix}`;
  const auth = () => ({ headers: { Authorization: `Bearer ${saved.token}` } });
  const elapsed = () => Math.floor(baseElapsed + performance.now() - baseClock);
  function lease() {
    const existing = JSON.parse(localStorage.getItem(leaseKey) || "null");
    if (existing && existing.tabId !== tabId && existing.expires > Date.now()) {
      throw new Error(
        "This study is already open in another tab. Close that tab, then try again in 15 seconds.",
      );
    }
    localStorage.setItem(
      leaseKey,
      JSON.stringify({ tabId, expires: Date.now() + 15000 }),
    );
  }
  function release() {
    try {
      if (JSON.parse(localStorage.getItem(leaseKey) || "null")?.tabId === tabId)
        localStorage.removeItem(leaseKey);
    } catch {
      /* Nothing to release. */
    }
  }
  function syncStatus() {
    const pending = saved.pending?.length || 0;
    $("#sync-status").textContent = pending
      ? `${pending} pending · stored on this browser`
      : "Synced";
    $("#finish-sync").textContent = pending
      ? `${pending} events waiting to sync. Keep this page open or reconnect to upload them.`
      : "All queued events are saved on this computer's study server.";
    $("#finish-copy").textContent = pending
      ? "Thank you. Some interactions are waiting to sync; their status is shown below."
      : "Thank you. Your anonymous reading interactions have been saved.";
  }
  function event(kind, extra = {}) {
    if (blocked) return;
    if (seq >= 3995 || (saved.pending || []).length >= 500) {
      blocked = true;
      running = false;
      notice(
        "Logging is paused because this session reached its event or offline storage limit. Keep the page open to sync; unobserved outcomes remain unknown.",
      );
      return;
    }
    const item = {
      event_id: crypto.randomUUID(),
      seq: ++seq,
      type: kind,
      elapsed_ms: elapsed(),
      ...extra,
    };
    saved.pending ||= [];
    saved.pending.push(item);
    saved.lastSequence = seq;
    try {
      persist();
    } catch {
      blocked = true;
      running = false;
      notice(
        "Your browser could not store this interaction. Reading has paused; keep this page open while pending events upload.",
      );
    }
    syncStatus();
    return item;
  }
  async function flush() {
    if (sending || !saved.sessionId || !saved.pending?.length) return;
    sending = true;
    try {
      while (saved.pending.length) {
        const batch = saved.pending.slice(0, 25);
        const result = await post(sessionPath("/events"), {
          session_token: saved.token,
          events: batch,
        });
        const ids = new Set(result.acknowledged);
        saved.pending = saved.pending.filter((e) => !ids.has(e.event_id));
        persist();
        syncStatus();
      }
      if (!blocked) notice("");
    } catch (e) {
      notice(
        `Interactions are queued on this browser. Sync will retry: ${e.message}`,
      );
    } finally {
      sending = false;
      syncStatus();
    }
  }
  const foreground = () =>
    document.visibilityState === "visible" && document.hasFocus();
  function visibleUnits(root, seen) {
    const bounds = root.getBoundingClientRect();
    root.querySelectorAll("[data-unit-id]").forEach((node) => {
      const r = node.getBoundingClientRect();
      const visible = Math.max(
        0,
        Math.min(r.bottom, bounds.bottom, innerHeight) -
          Math.max(r.top, bounds.top, 0),
      );
      // For a paragraph taller than the reading viewport, require half a viewport.
      if (visible >= Math.min(r.height, bounds.height) * 0.5 && visible > 0)
        seen.add(node.dataset.unitId);
    });
  }
  function tick() {
    const now = performance.now(),
      delta = Math.min(1000, Math.max(0, now - lastTick));
    lastTick = now;
    if (!running || !current || !foreground()) return;
    if ($("#reader").open) {
      if (readerReady) {
        current.follow += delta;
        visibleUnits($("#reader-body"), current.followSeen);
      }
    } else if ((ratios.get(current.index) || 0) >= 0.6) {
      current.active += delta;
      visibleUnits(current.node.querySelector(".story-scroll"), current.seen);
    }
  }
  function snapshot(exposure = current) {
    return {
      exposure_id: exposure.id,
      card_id: exposure.cardId,
      active_ms: Math.floor(exposure.active),
      seen_units: [...exposure.seen].sort(),
      continuation_ms: Math.floor(exposure.follow),
      continuation_seen_units: [...exposure.followSeen].sort(),
    };
  }
  function progress(reason = "heartbeat") {
    tick();
    if (current)
      event($("#reader").open ? "continuation_progress" : "progress", {
        ...snapshot(),
        reason,
      });
    flush();
  }
  function closeReader() {
    if (!$("#reader").open) return;
    tick();
    if (current)
      event("continuation_close", { ...snapshot(), reason: "reader_close" });
    readerReady = false;
    $("#reader").close();
    flush();
  }
  function endCurrent(reason) {
    if (!current) return;
    if ($("#reader").open) closeReader();
    tick();
    event("view_end", { ...snapshot(), reason });
    current = null;
    flush();
  }
  function selectVisible() {
    if (!running || !foreground() || $("#reader").open) return;
    const visible = [...ratios]
      .filter(([, ratio]) => ratio >= 0.6)
      .sort((a, b) => b[1] - a[1])[0];
    if (!visible) return;
    const index = visible[0];
    if (current?.index === index) return;
    if (current) endCurrent(index < current.index ? "back" : movingReason);
    if (!running) return;
    movingReason = "next";
    document.querySelectorAll(".story-card").forEach((node, i) => {
      node.inert = i !== index;
    });
    current = {
      id: crypto.randomUUID(),
      cardId: data.cards[index].id,
      index,
      node: document.querySelectorAll(".story-card")[index],
      active: 0,
      follow: 0,
      seen: new Set(),
      followSeen: new Set(),
    };
    lastTick = performance.now();
    event("view_start", {
      exposure_id: current.id,
      card_id: current.cardId,
      reason: "initial",
    });
    $("#position").textContent = `${index + 1} / ${data.cards.length}`;
    $("#previous").disabled = index === 0;
    $("#next").textContent =
      index === data.cards.length - 1 ? "Finish reading ✓" : "Next story ↓";
    flush();
  }
  function addUnits(root, units) {
    root.replaceChildren();
    for (const unit of units) {
      const p = document.createElement("p");
      p.className = "story-unit";
      p.dataset.unitId = unit.id;
      p.textContent = unit.text;
      root.append(p);
    }
  }
  async function openReader(index) {
    if (!running || !current || current.index !== index || $("#reader").open)
      return;
    tick();
    const exposureId = current.id;
    event("continue_open", { ...snapshot(), reason: "reader_open" });
    $("#reader-title").textContent = data.cards[index].title;
    $("#reader-body").textContent = "Loading the next part…";
    readerReady = false;
    $("#reader").showModal();
    flush();
    try {
      const next = await request(
        sessionPath(
          `/continuation?card_id=${encodeURIComponent(current.cardId)}`,
        ),
        auth(),
      );
      if (!$("#reader").open || current?.id !== exposureId) return;
      addUnits($("#reader-body"), next.units);
      $("#reader-body").scrollTop = 0;
      lastTick = performance.now();
      readerReady = true;
    } catch (e) {
      $("#reader-body").textContent =
        `Could not load continuation. Return to the feed and try again. ${e.message}`;
    }
  }
  function move(direction, reason = "next") {
    if (!running || !current) return;
    const next = current.index + direction;
    if (next >= data.cards.length) return finish("finished_feed");
    if (next < 0) return;
    movingReason = reason;
    document
      .querySelectorAll(".story-card")
      [next].scrollIntoView({ behavior: "instant", block: "start" });
  }
  function renderFeed(resumeIndex = 0) {
    const root = $("#feed");
    root.replaceChildren();
    data.cards.forEach((card, index) => {
      const article = document.createElement("article");
      article.className = "story-card";
      article.dataset.index = index;
      const top = document.createElement("div");
      top.className = "story-top";
      const genre = document.createElement("span");
      genre.textContent = card.genre;
      const label = document.createElement("span");
      label.textContent = "A SHORT STORY";
      top.append(genre, label);
      const title = document.createElement("h2");
      title.textContent = card.title;
      const story = document.createElement("div");
      story.className = "story-scroll";
      story.tabIndex = 0;
      addUnits(story, card.units);
      const footer = document.createElement("div");
      footer.className = "story-footer";
      const more = document.createElement("button");
      more.className = "continue-button";
      more.textContent = "Keep reading ↗";
      more.onclick = () => openReader(index);
      const skip = document.createElement("button");
      skip.className = "skip-card";
      skip.textContent = "Skip story ↓";
      skip.onclick = () => move(1, "skip");
      footer.append(more, skip);
      article.append(top, title, story, footer);
      root.append(article);
    });
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) =>
          ratios.set(
            Number(entry.target.dataset.index),
            entry.intersectionRatio,
          ),
        );
        selectVisible();
      },
      { root, threshold: [0, 0.6, 0.9, 1] },
    );
    root
      .querySelectorAll(".story-card")
      .forEach((card) => observer.observe(card));
    root.scrollTop = root.clientHeight * resumeIndex;
    root.focus({ preventScroll: true });
  }
  async function begin() {
    $("#begin").disabled = true;
    try {
      lease();
      saved = readSaved();
      saved.participantKey ||= crypto.randomUUID();
      saved.pending ||= [];
      persist();
      if (saved.sessionId && saved.token) {
        await flush();
        if (saved.pending.length)
          throw new Error(
            "Reconnect to sync this browser's pending interactions before resuming.",
          );
        data = await request(sessionPath(), auth());
      } else {
        data = await post(`/api/experiments/${studyId}/sessions`, {
          participant_key: saved.participantKey,
          consent: true,
        });
        saved.sessionId = data.id;
        saved.token = data.session_token;
        persist();
      }
      baseElapsed = data.elapsed_ms;
      baseClock = performance.now();
      seq = Math.max(data.last_seq, saved.lastSequence || 0);
      $("#welcome").hidden = true;
      if (data.status === "complete") {
        $("#finish").hidden = false;
        syncStatus();
        release();
        return;
      }
      // A crashed browser's exposure is censored, never silently turned into a skip.
      for (const old of data.prior_exposures.filter(
        (e) => e.state === "open",
      )) {
        event("view_end", {
          exposure_id: old.id,
          card_id: old.card_id,
          active_ms: old.active_ms,
          seen_units: JSON.parse(old.seen),
          continuation_ms: old.continuation_ms,
          continuation_seen_units: JSON.parse(old.continuation_seen),
          reason: "reload",
        });
      }
      const lastCard = data.prior_exposures.at(-1)?.card_id;
      const resumeIndex = Math.max(
        0,
        data.cards.findIndex((c) => c.id === lastCard),
      );
      running = true;
      $("#experience").hidden = false;
      renderFeed(resumeIndex);
      flush();
    } catch (e) {
      notice(e.message, true);
      release();
      $("#begin").disabled = !$("#consent").checked;
    }
  }
  function finish(reason = "exit") {
    if (!running) return;
    endCurrent(reason);
    event("session_finish");
    running = false;
    saved.finished = true;
    persist();
    $("#experience").hidden = true;
    $("#finish").hidden = false;
    flush();
    syncStatus();
    release();
  }
  async function withdraw() {
    if (
      !confirm(
        "Delete all of this session's events and outcomes from the study server?",
      )
    )
      return;
    try {
      // Serialize deletion after an existing upload; new uploads are stopped first.
      blocked = true;
      running = false;
      if ($("#reader").open) $("#reader").close();
      while (sending) await new Promise((resolve) => setTimeout(resolve, 50));
      await post(sessionPath("/withdraw"), { session_token: saved.token });
      saved = {};
      localStorage.removeItem(storageKey);
      current = null;
      release();
      $("#experience").hidden = true;
      $("#finish").hidden = false;
      $("#finish-title").textContent = "Your session was deleted.";
      $("#finish-copy").textContent =
        "Its events and exposure outcomes have been removed from the study server. Previously downloaded exports cannot be recalled automatically.";
      $("#finish-sync").textContent =
        "No session data remains on this browser.";
      $("#finish-withdraw").hidden = true;
    } catch (e) {
      notice(`Deletion has not completed: ${e.message}`);
      $("#finish-sync").textContent =
        `Deletion has not completed: ${e.message}. Please reconnect and retry.`;
    }
  }
  $("#begin").onclick = begin;
  $("#consent").onchange = () => {
    $("#begin").disabled = !$("#consent").checked;
  };
  $("#next").onclick = () => move(1);
  $("#previous").onclick = () => move(-1, "back");
  $("#exit").onclick = () => finish("exit");
  $("#withdraw").onclick = withdraw;
  $("#finish-withdraw").onclick = withdraw;
  $("#close-reader").onclick = closeReader;
  $("#reader").addEventListener("cancel", (e) => {
    e.preventDefault();
    closeReader();
  });
  $("#feed").addEventListener("keydown", (e) => {
    if (e.target !== $("#feed")) return;
    if (["ArrowDown", "ArrowUp"].includes(e.key)) {
      e.preventDefault();
      move(e.key === "ArrowDown" ? 1 : -1);
    }
  });
  document.addEventListener("visibilitychange", () => {
    lastTick = performance.now();
    if (running && current)
      progress(document.hidden ? "visibility_hidden" : "visibility_visible");
    if (!document.hidden) selectVisible();
  });
  window.addEventListener("blur", () => {
    lastTick = performance.now();
    if (running && current) progress("window_blur");
  });
  window.addEventListener("focus", () => {
    lastTick = performance.now();
    selectVisible();
  });
  window.addEventListener("online", flush);
  window.addEventListener("pagehide", () => {
    if (running) {
      endCurrent("unload");
      running = false;
    }
    if (saved.sessionId && saved.pending?.length)
      navigator.sendBeacon(
        sessionPath("/events"),
        new Blob(
          [
            JSON.stringify({
              session_token: saved.token,
              events: saved.pending.slice(0, 25),
            }),
          ],
          { type: "application/json" },
        ),
      );
    release();
  });
  window.addEventListener("pageshow", (e) => {
    if (e.persisted) location.reload();
  });
  setInterval(() => {
    tick();
    const now = performance.now();
    if (running && now - lastHeartbeat >= 5000) {
      lastHeartbeat = now;
      progress();
    }
  }, 250);
  setInterval(() => {
    if (running) {
      try {
        lease();
      } catch (e) {
        blocked = true;
        running = false;
        notice(e.message);
      }
    }
    flush();
  }, 5000);
  (async () => {
    try {
      const study = await request(`/api/experiments/${studyId}/public`);
      saved = readSaved();
      if (new URL(location.href).searchParams.get("fresh") === "1") {
        const owner = JSON.parse(localStorage.getItem(leaseKey) || "null");
        if (owner && owner.expires > Date.now())
          throw new Error(
            "Finish the active participant session before starting a new one on this browser.",
          );
        if (saved.pending?.length)
          throw new Error(
            "Resume the previous session to sync its pending events before starting a new participant.",
          );
        localStorage.removeItem(storageKey);
        saved = {};
        history.replaceState(null, "", location.pathname);
      }
      $("#study-name").textContent =
        study.name + (study.is_test ? " · SOFTWARE TEST" : "");
      $("#consent-text").textContent = study.consent_text;
      $("#begin").textContent = saved.sessionId
        ? "Resume session ↗"
        : "Start reading ↗";
      if (study.closed && !saved.sessionId) {
        $("#consent").disabled = true;
        notice("This study is closed to new participants.", true);
      }
    } catch (e) {
      $("#consent").disabled = true;
      notice(e.message, true);
    }
  })();
})();
