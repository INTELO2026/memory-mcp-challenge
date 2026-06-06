const REPORT_URL = "../benchmark/results/report.json";
const LIVE_URL = "live.json";
const LIVE_POLL_MS = 2000;

const PANEL_META = {
  overview: { eyebrow: "Benchmark", title: "Vue d'ensemble", desc: "KPIs, courbes et comparaison naïf vs MemBridge" },
  live: { eyebrow: "Temps réel", title: "Live MCP", desc: "Métriques publiées par le serveur à chaque appel outil" },
  performance: { eyebrow: "Analyse", title: "Performance", desc: "Compression, croissance et courbe détaillée sur 50 tours" },
  quality: { eyebrow: "Validation", title: "Qualité", desc: "Questions pièges et rétention des faits critiques" },
  raw: { eyebrow: "Export", title: "Données brutes", desc: "Rapport JSON complet du benchmark" },
};

const CHART = {
  naive: "#ff6b7a",
  memory: "#3dffb8",
  accent: "#8b7dff",
  naiveFill: "rgba(255, 107, 122, 0.22)",
  memoryFill: "rgba(61, 255, 184, 0.2)",
  accentFill: "rgba(139, 125, 255, 0.22)",
};

const state = {
  data: null,
  live: null,
  theme: localStorage.getItem("membridge-theme") || "dark",
  activePanel: "overview",
  chartPoints: { naive: [], memory: [] },
  chartSizes: {},
  simRunning: false,
  livePollId: null,
  resizeTimer: null,
  importSource: null,
};

function debounce(fn, ms = 150) {
  return (...args) => {
    clearTimeout(state.resizeTimer);
    state.resizeTimer = setTimeout(() => fn(...args), ms);
  };
}

function setupCanvas(canvas, rect, dpr) {
  const w = Math.floor(rect.width);
  const h = Math.floor(rect.height);
  const key = canvas.id || "chart";
  const prev = state.chartSizes[key];
  if (prev && prev.w === w && prev.h === h) {
    return { w, h, skip: true };
  }
  state.chartSizes[key] = { w, h };
  canvas.width = Math.max(1, Math.floor(w * dpr));
  canvas.height = Math.max(1, Math.floor(h * dpr));
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { w, h, skip: false };
}

const euro = (v) => `${Number(v || 0).toFixed(4)} €`;
const pct = (v) => `${Number(v || 0).toFixed(1)}%`;
const fmt = (v) => Number(v || 0).toLocaleString("fr-FR");

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2400);
}

function chartTheme() {
  const light = state.theme === "light";
  return {
    bg: light ? "#f4f7fc" : "#0c1322",
    grid: light ? "rgba(15, 23, 42, 0.1)" : "rgba(168, 184, 208, 0.16)",
    label: light ? "#64748b" : "#a8b8d0",
    font: "600 11px DM Sans, sans-serif",
    fontSm: "500 11px DM Sans, sans-serif",
  };
}

function drawChartGrid(ctx, w, h, pad, maxVal, steps = 4) {
  const theme = chartTheme();
  ctx.fillStyle = theme.bg;
  ctx.fillRect(pad.left, pad.top, w - pad.left - pad.right, h - pad.top - pad.bottom);

  ctx.strokeStyle = theme.grid;
  ctx.lineWidth = 1;
  ctx.font = theme.font;
  ctx.fillStyle = theme.label;

  for (let i = 0; i <= steps; i++) {
    const y = pad.top + (h - pad.top - pad.bottom) * (i / steps);
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(w - pad.right, y);
    ctx.stroke();
    const val = Math.round(maxVal * (1 - i / steps));
    ctx.fillText(String(val), 12, y + 4);
  }
}

function updateTopbar(id) {
  const meta = PANEL_META[id] || PANEL_META.overview;
  const eyebrow = document.getElementById("topbar-eyebrow");
  const title = document.getElementById("topbar-title");
  const desc = document.getElementById("topbar-desc");
  if (eyebrow) eyebrow.textContent = meta.eyebrow;
  if (title) title.textContent = meta.title;
  if (desc) desc.textContent = meta.desc;
}

function setTheme(theme) {
  state.theme = theme;
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("membridge-theme", theme);
  document.getElementById("theme-toggle").textContent = theme === "dark" ? "Mode clair" : "Mode sombre";
  redrawChartsForPanel(state.activePanel);
}

function redrawChartsForPanel(id) {
  requestAnimationFrame(() => {
    if (id === "overview" && state.data) {
      drawChart(state.data.naive.per_turn_tokens || [], state.data.memory.per_turn_tokens || []);
    }
    if (id === "live" && state.live) {
      const savings = state.live.savings || {};
      drawLiveChart(state.live.per_call_tokens || []);
      drawDualChart(
        "chart-live-compare",
        savings.per_turn_naive || [],
        savings.per_turn_memory || [],
        "Stockez des tours via memory_store..."
      );
    }
    if (id === "performance" && state.data) {
      drawChart(
        state.data.naive.per_turn_tokens || [],
        state.data.memory.per_turn_tokens || [],
        "chart-performance"
      );
    }
  });
}

function switchPanel(id) {
  state.activePanel = id;
  document.querySelectorAll(".panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `panel-${id}`);
  });
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.panel === id);
  });
  updateTopbar(id);
  redrawChartsForPanel(id);
}

function animateValue(el, end, duration = 900, suffix = "") {
  const start = 0;
  const startTime = performance.now();
  function frame(now) {
    const progress = Math.min((now - startTime) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const value = Math.round(start + (end - start) * eased);
    el.textContent = `${fmt(value)}${suffix}`;
    if (progress < 1) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function updateHero(data, animate = false) {
  const q = data.quality || data.memory?.quality || {};
  const map = [
    ["kpi-savings", data.savings_pct, "%"],
    ["kpi-tokens", data.tokens_saved, ""],
    ["kpi-cost", data.cost_saved_eur, " €"],
    ["kpi-quality", q.passed, ` / ${q.total || 10}`],
  ];

  map.forEach(([id, value, suffix]) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (animate && typeof value === "number") {
      if (suffix.includes("/")) {
        animateValue(el, value, 900, suffix);
      } else if (suffix === "%") {
        animateValue(el, value, 900, suffix);
      } else if (suffix === " €") {
        const start = performance.now();
        const end = Number(value || 0);
        const tick = (now) => {
          const p = Math.min((now - start) / 900, 1);
          const eased = 1 - Math.pow(1 - p, 3);
          el.textContent = euro(end * eased);
          if (p < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      } else {
        animateValue(el, value, 900, suffix);
      }
    } else if (suffix.includes("/")) {
      el.textContent = `${value ?? "—"}${suffix}`;
    } else if (suffix === "%") {
      el.textContent = `${value ?? "—"}%`;
    } else if (suffix === " €") {
      el.textContent = euro(value);
    } else {
      el.textContent = fmt(value);
    }
  });

  document.getElementById("naive-tokens").textContent = fmt(data.naive.total_tokens);
  document.getElementById("memory-tokens").textContent = fmt(data.memory.total_tokens);
  document.getElementById("naive-cost").textContent = euro(data.naive.cost_eur);
  document.getElementById("memory-cost").textContent = euro(data.memory.cost_eur);
  document.getElementById("savings-label").textContent = `-${data.savings_pct}%`;
  document.getElementById("tokens-saved-label").textContent = `${fmt(data.tokens_saved)} tokens économisés`;
  document.getElementById("cost-saved-label").textContent = `${euro(data.cost_saved_eur)} économisés`;
  updateCubeSavings(data.savings_pct);

  const maxTokens = Math.max(data.naive.total_tokens, 1);
  document.getElementById("bar-naive").style.width = "100%";
  document.getElementById("bar-memory").style.width = `${(data.memory.total_tokens / maxTokens) * 100}%`;

  document.getElementById("compression-ratio").textContent = pct((data.memory.compression_ratio || 0) * 100);
  document.getElementById("growth-factor").textContent = Number(data.memory.growth_factor || 0).toFixed(2);
  document.getElementById("turn-count").textContent = fmt(data.memory.turns || 0);

  const stats = data.memory.stats || {};
  document.getElementById("stat-store").textContent = fmt(stats.store_calls || 0);
  document.getElementById("stat-search").textContent = fmt(stats.search_calls || 0);
  document.getElementById("stat-summarize").textContent = fmt(stats.summarize_calls || 0);
  document.getElementById("stat-mcp-tokens").textContent = fmt(stats.total_tokens || 0);

  drawGauge(q.score_pct || 0);
  renderTraps(q.details || []);
  document.getElementById("raw-json").textContent = JSON.stringify(data, null, 2);
  if (!state.importSource) {
    setStatusPill(`Rapport chargé · ${new Date().toLocaleTimeString("fr-FR")}`);
  }

  if (state.activePanel === "overview" || state.activePanel === "performance") {
    redrawChartsForPanel(state.activePanel);
  }
}

function drawGauge(score) {
  const circle = document.getElementById("gauge-progress");
  const value = document.getElementById("gauge-value");
  const radius = 72;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  circle.style.strokeDasharray = `${circumference}`;
  circle.style.strokeDashoffset = `${offset}`;
  circle.style.stroke = score >= 50 ? "url(#gauge-gradient)" : CHART.naive;
  value.textContent = `${Math.round(score)}%`;
}

function updateCubeSavings(pctValue) {
  const el = document.getElementById("cube-savings");
  if (!el) return;
  const v = Number(pctValue || 0);
  el.textContent = v > 0 ? `-${v}%` : "—";
}

function initPlatform3D() {
  const scene = document.getElementById("platform-3d");
  const tilt = document.getElementById("platform-3d-tilt");
  if (!scene || !tilt) return;

  let dragging = false;

  const applyTilt = (clientX, clientY) => {
    const rect = scene.getBoundingClientRect();
    const nx = (clientX - rect.left) / rect.width - 0.5;
    const ny = (clientY - rect.top) / rect.height - 0.5;
    const rotY = 18 + nx * 42;
    const rotX = -12 - ny * 36;
    tilt.style.setProperty("--tilt-y", `${rotY}deg`);
    tilt.style.setProperty("--tilt-x", `${rotX}deg`);
  };

  const resetTilt = () => {
    tilt.style.setProperty("--tilt-y", "18deg");
    tilt.style.setProperty("--tilt-x", "-12deg");
  };

  scene.addEventListener("pointerdown", (e) => {
    dragging = true;
    scene.classList.add("is-active");
    scene.setPointerCapture(e.pointerId);
    applyTilt(e.clientX, e.clientY);
  });

  scene.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    applyTilt(e.clientX, e.clientY);
  });

  const endDrag = (e) => {
    if (!dragging) return;
    dragging = false;
    scene.classList.remove("is-active");
    if (scene.hasPointerCapture(e.pointerId)) {
      scene.releasePointerCapture(e.pointerId);
    }
    resetTilt();
  };

  scene.addEventListener("pointerup", endDrag);
  scene.addEventListener("pointercancel", endDrag);
  scene.addEventListener("pointerleave", () => {
    if (!dragging) return;
    dragging = false;
    scene.classList.remove("is-active");
    resetTilt();
  });

  scene.addEventListener(
    "touchstart",
    (e) => {
      if (e.touches.length === 1) applyTilt(e.touches[0].clientX, e.touches[0].clientY);
    },
    { passive: true }
  );
}

function drawChart(naive, memory, canvasId = "chart") {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const tooltip = canvasId === "chart" ? document.getElementById("chart-tooltip") : null;
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.parentElement.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2) return;
  const { w, h } = setupCanvas(canvas, rect, dpr);
  const ctx = canvas.getContext("2d");
  const pad = { top: 24, right: 20, bottom: 34, left: 52 };
  const maxLen = Math.max(naive.length, memory.length, 1);
  const all = [...naive, ...memory];
  const maxVal = Math.max(...all, 1);
  const theme = chartTheme();

  state.chartPoints = { naive: [], memory: [] };

  ctx.clearRect(0, 0, w, h);
  drawChartGrid(ctx, w, h, pad, maxVal);

  function plot(data, color, key, fillColor) {
    if (!data.length) return;
    const points = [];
    const plotW = w - pad.left - pad.right;
    const plotH = h - pad.top - pad.bottom;

    data.forEach((v, i) => {
      const x = pad.left + (i / (maxLen - 1 || 1)) * plotW;
      const y = pad.top + (1 - v / maxVal) * plotH;
      points.push({ x, y, v, i });
    });
    state.chartPoints[key] = points;

    ctx.beginPath();
    points.forEach((p, i) => {
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.lineTo(points[points.length - 1].x, h - pad.bottom);
    ctx.lineTo(points[0].x, h - pad.bottom);
    ctx.closePath();
    const gradient = ctx.createLinearGradient(0, pad.top, 0, h - pad.bottom);
    gradient.addColorStop(0, fillColor);
    gradient.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = gradient;
    ctx.fill();

    ctx.beginPath();
    points.forEach((p, i) => {
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.save();
    ctx.lineWidth = 2.5;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.strokeStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = 14;
    ctx.stroke();
    ctx.restore();

    const step = Math.max(1, Math.floor(points.length / 12));
    points.forEach((p, i) => {
      if (i % step !== 0 && i !== points.length - 1) return;
      ctx.beginPath();
      ctx.fillStyle = color;
      ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.fillStyle = "rgba(255,255,255,0.9)";
      ctx.arc(p.x, p.y, 1.2, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  plot(naive, CHART.naive, "naive", CHART.naiveFill);
  plot(memory, CHART.memory, "memory", CHART.memoryFill);

  ctx.font = theme.fontSm;
  ctx.fillStyle = theme.label;
  ctx.fillText("Tour 1", pad.left, h - 10);
  ctx.fillText(`Tour ${maxLen}`, w - pad.right - 48, h - 10);

  if (tooltip) {
    canvas.onmousemove = (event) => {
      const bounds = canvas.getBoundingClientRect();
      const x = event.clientX - bounds.left;
      const y = event.clientY - bounds.top;
      let hit = null;

      ["naive", "memory"].forEach((key) => {
        state.chartPoints[key].forEach((p) => {
          const dx = p.x - x;
          const dy = p.y - y;
          if (Math.hypot(dx, dy) < 10) hit = { ...p, key };
        });
      });

      if (!hit) {
        tooltip.style.opacity = 0;
        return;
      }

      tooltip.style.opacity = 1;
      tooltip.style.left = `${hit.x + 12}px`;
      tooltip.style.top = `${hit.y - 10}px`;
      tooltip.innerHTML = `<strong>${hit.key === "naive" ? "Naïf" : "MemBridge"}</strong><br>Tour ${hit.i + 1} · ${fmt(hit.v)} tokens`;
    };

    canvas.onmouseleave = () => {
      tooltip.style.opacity = 0;
    };
  }
}

function renderTraps(details) {
  const list = document.getElementById("trap-list");
  const filter = document.getElementById("trap-filter").value.trim().toLowerCase();
  const status = document.getElementById("trap-status").value;
  list.innerHTML = "";

  const filtered = details.filter((item) => {
    const matchesText = !filter || item.query.toLowerCase().includes(filter) || item.expected.toLowerCase().includes(filter);
    const matchesStatus =
      status === "all" ||
      (status === "passed" && item.passed) ||
      (status === "failed" && !item.passed);
    return matchesText && matchesStatus;
  });

  if (!filtered.length) {
    list.innerHTML = `<div class="empty-state">Aucune question ne correspond au filtre.</div>`;
    return;
  }

  filtered.forEach((item, index) => {
    const node = document.createElement("div");
    node.className = "trap-item";
    node.innerHTML = `
      <button class="trap-head" type="button">
        <span>${item.query}</span>
        <span class="trap-badge ${item.passed ? "ok" : "fail"}">${item.passed ? "Réussi" : "Échoué"}</span>
      </button>
      <div class="trap-body">
        <p><strong>Attendu :</strong> ${item.expected}</p>
        <p><strong>Résultat :</strong> ${item.top_result || "Aucun"}</p>
      </div>
    `;
    node.querySelector(".trap-head").addEventListener("click", () => node.classList.toggle("open"));
    if (index === 0) node.classList.add("open");
    list.appendChild(node);
  });
}

function drawDualChart(canvasId, naive, memory, emptyLabel) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.parentElement.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2) return;
  const { w, h } = setupCanvas(canvas, rect, dpr);
  const ctx = canvas.getContext("2d");
  const pad = { top: 16, right: 12, bottom: 24, left: 40 };
  const maxLen = Math.max(naive.length, memory.length, 1);
  const all = [...naive, ...memory];
  const maxVal = Math.max(...all, 1);
  const theme = chartTheme();

  ctx.clearRect(0, 0, w, h);

  if (!naive.length && !memory.length) {
    drawChartGrid(ctx, w, h, pad, 100, 3);
    ctx.fillStyle = theme.label;
    ctx.font = theme.fontSm;
    ctx.fillText(emptyLabel, pad.left + 8, h / 2);
    return;
  }

  drawChartGrid(ctx, w, h, pad, maxVal, 3);

  const plot = (data, color, fillColor) => {
    if (!data.length) return;
    const points = [];
    const plotW = w - pad.left - pad.right;
    const plotH = h - pad.top - pad.bottom;

    data.forEach((v, i) => {
      const x = pad.left + (i / (maxLen - 1 || 1)) * plotW;
      const y = pad.top + (1 - v / maxVal) * plotH;
      points.push({ x, y });
    });

    ctx.beginPath();
    points.forEach((p, i) => {
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.lineTo(points[points.length - 1].x, h - pad.bottom);
    ctx.lineTo(points[0].x, h - pad.bottom);
    ctx.closePath();
    const gradient = ctx.createLinearGradient(0, pad.top, 0, h - pad.bottom);
    gradient.addColorStop(0, fillColor);
    gradient.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = gradient;
    ctx.fill();

    ctx.beginPath();
    points.forEach((p, i) => {
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.lineJoin = "round";
    ctx.shadowColor = color;
    ctx.shadowBlur = 10;
    ctx.stroke();
    ctx.restore();
  };

  plot(naive, CHART.naive, CHART.naiveFill);
  plot(memory, CHART.memory, CHART.memoryFill);

  ctx.font = theme.fontSm;
  ctx.fillStyle = theme.label;
  ctx.fillText("Tour 1", pad.left, h - 8);
  ctx.fillText(`Tour ${maxLen}`, w - pad.right - 48, h - 8);
}

function drawLiveChart(series) {
  const canvas = document.getElementById("chart-live");
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.parentElement.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2) return;
  const { w, h } = setupCanvas(canvas, rect, dpr);
  const ctx = canvas.getContext("2d");
  const pad = { top: 16, right: 12, bottom: 24, left: 40 };
  const data = series || [];
  const maxVal = Math.max(...data, 1);
  const theme = chartTheme();

  ctx.clearRect(0, 0, w, h);

  if (!data.length) {
    drawChartGrid(ctx, w, h, pad, 100, 3);
    ctx.fillStyle = theme.label;
    ctx.font = theme.fontSm;
    ctx.fillText("En attente d'appels MCP...", pad.left + 8, h / 2);
    return;
  }

  drawChartGrid(ctx, w, h, pad, maxVal, 3);

  const plotW = w - pad.left - pad.right;
  const plotH = h - pad.top - pad.bottom;
  const points = data.map((v, i) => ({
    x: pad.left + (i / Math.max(data.length - 1, 1)) * plotW,
    y: pad.top + (1 - v / maxVal) * plotH,
  }));

  ctx.beginPath();
  points.forEach((p, i) => {
    if (i === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  });
  ctx.lineTo(points[points.length - 1].x, h - pad.bottom);
  ctx.lineTo(points[0].x, h - pad.bottom);
  ctx.closePath();
  const gradient = ctx.createLinearGradient(0, pad.top, 0, h - pad.bottom);
  gradient.addColorStop(0, CHART.accentFill);
  gradient.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = gradient;
  ctx.fill();

  ctx.beginPath();
  points.forEach((p, i) => {
    if (i === 0) ctx.moveTo(p.x, p.y);
    else ctx.lineTo(p.x, p.y);
  });
  ctx.save();
  ctx.strokeStyle = CHART.accent;
  ctx.lineWidth = 2.5;
  ctx.lineJoin = "round";
  ctx.shadowColor = CHART.accent;
  ctx.shadowBlur = 12;
  ctx.stroke();
  ctx.restore();
}

function renderActivityFeed(items) {
  const feed = document.getElementById("activity-feed");
  if (!feed) return;
  if (!items || !items.length) {
    feed.innerHTML = `<li class="empty-state">Aucune activité — utilisez les outils MCP dans Cursor</li>`;
    return;
  }
  feed.innerHTML = items
    .map(
      (item) => `
      <li>
        <div class="tool">${item.tool}</div>
        <div>${item.detail || "—"} · ${fmt(item.tokens || 0)} tokens</div>
        <div class="meta">session: ${item.session || "default"} · ${new Date(item.at).toLocaleTimeString("fr-FR")}</div>
      </li>`
    )
    .join("");
}

function updateLivePanel(live) {
  if (!live) return;
  state.live = live;
  const stats = live.stats || {};
  const statusEl = document.getElementById("live-status");
  const pill = document.getElementById("status-pill");

  if (statusEl) statusEl.textContent = live.status === "online" ? "En ligne" : live.status || "—";
  if (document.getElementById("live-updated")) {
    document.getElementById("live-updated").textContent = live.updated_at
      ? `MAJ ${new Date(live.updated_at).toLocaleTimeString("fr-FR")}`
      : "—";
  }
  if (document.getElementById("live-tokens")) {
    document.getElementById("live-tokens").textContent = fmt(stats.total_tokens || 0);
  }
  if (document.getElementById("live-memories")) {
    document.getElementById("live-memories").textContent = `${fmt(live.memories_count || 0)} souvenirs`;
  }
  if (document.getElementById("live-store")) {
    document.getElementById("live-store").textContent = fmt(stats.store_calls || 0);
  }
  if (document.getElementById("live-search")) {
    document.getElementById("live-search").textContent = fmt(stats.search_calls || 0);
  }

  if (document.getElementById("stat-store")) {
    document.getElementById("stat-store").textContent = fmt(stats.store_calls || 0);
  }
  if (document.getElementById("stat-search")) {
    document.getElementById("stat-search").textContent = fmt(stats.search_calls || 0);
  }
  if (document.getElementById("stat-summarize")) {
    document.getElementById("stat-summarize").textContent = fmt(stats.summarize_calls || 0);
  }
  if (document.getElementById("stat-mcp-tokens")) {
    document.getElementById("stat-mcp-tokens").textContent = fmt(stats.total_tokens || 0);
  }

  const savings = live.savings || {};
  const pctEl = document.getElementById("live-savings-pct");
  const hintEl = document.getElementById("live-savings-hint");
  if (pctEl) {
    if (!savings.turns) {
      pctEl.textContent = "—";
      pctEl.style.color = "";
    } else {
      const pct = Number(savings.savings_pct || 0);
      const positive = pct >= 0;
      pctEl.textContent = positive ? `-${pct}%` : `+${Math.abs(pct)}%`;
      pctEl.style.color = positive ? "var(--memory)" : "var(--naive)";
    }
  }
  if (hintEl) {
    const turns = savings.turns || 0;
    if (turns < 5) {
      hintEl.textContent = "L'économie augmente après quelques tours";
    } else if ((savings.savings_pct || 0) < 0) {
      hintEl.textContent = "Contexte encore court — continuez à stocker";
    } else {
      hintEl.textContent = "MemBridge sous le mode naïf";
    }
  }
  if ((savings.savings_pct || 0) > 0) {
    updateCubeSavings(savings.savings_pct);
  }
  if (document.getElementById("live-tokens-saved")) {
    document.getElementById("live-tokens-saved").textContent =
      `${fmt(savings.tokens_saved || 0)} tokens économisés`;
  }
  if (document.getElementById("live-turns-count")) {
    document.getElementById("live-turns-count").textContent = `${fmt(savings.turns || 0)} tours`;
  }
  if (document.getElementById("live-naive-tokens")) {
    document.getElementById("live-naive-tokens").textContent = fmt(savings.naive_tokens || 0);
  }
  if (document.getElementById("live-memory-tokens")) {
    document.getElementById("live-memory-tokens").textContent = fmt(savings.memory_tokens || 0);
  }
  const naiveMax = Math.max(savings.naive_tokens || 0, 1);
  if (document.getElementById("live-bar-naive")) {
    document.getElementById("live-bar-naive").style.width = "100%";
  }
  if (document.getElementById("live-bar-memory")) {
    document.getElementById("live-bar-memory").style.width =
      `${((savings.memory_tokens || 0) / naiveMax) * 100}%`;
  }

  if (state.activePanel === "live") {
    drawLiveChart(live.per_call_tokens || []);
    drawDualChart(
      "chart-live-compare",
      savings.per_turn_naive || [],
      savings.per_turn_memory || [],
      "Stockez des tours via memory_store..."
    );
  }
  renderActivityFeed(live.recent_activity || []);

  if (pill) {
    pill.classList.toggle("offline", live.status !== "online");
    pill.innerHTML = `<span class="status-dot"></span> MCP live · ${new Date(live.updated_at).toLocaleTimeString("fr-FR")}`;
  }
}

async function loadLive() {
  try {
    const res = await fetch(`${LIVE_URL}?t=${Date.now()}`);
    const live = await res.json();
    updateLivePanel(live);
  } catch {
    const pill = document.getElementById("status-pill");
    if (pill) {
      pill.classList.add("offline");
      pill.innerHTML = `<span class="status-dot"></span> MCP hors ligne`;
    }
  }
}

function startLivePolling() {
  if (state.livePollId) clearInterval(state.livePollId);
  loadLive();
  state.livePollId = setInterval(loadLive, LIVE_POLL_MS);
}

async function loadReport(animate = false) {
  try {
    const res = await fetch(`${REPORT_URL}?t=${Date.now()}`);
    const data = await res.json();
    state.data = data;
    if (!state.importSource) {
      clearImportDemoBanner();
    }
    updateHero(data, animate);
    if (!state.importSource) {
      setStatusPill(`Rapport chargé · ${new Date().toLocaleTimeString("fr-FR")}`);
    }
    showToast(state.importSource ? "Rapport local actualisé" : "Rapport benchmark chargé");
  } catch {
    document.getElementById("raw-json").textContent =
      "Aucun rapport trouvé. Exécutez : python -m benchmark.harness";
    document.getElementById("status-pill").textContent = "Rapport introuvable";
    showToast("Impossible de charger le rapport");
  }
}

function exportReport() {
  if (!state.data) return showToast("Aucun rapport à exporter");
  const blob = new Blob([JSON.stringify(state.data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "membridge-report.json";
  link.click();
  URL.revokeObjectURL(url);
  showToast("Export JSON téléchargé");
}

const IMPORT_MAX_BYTES = 5 * 1024 * 1024;

function detectImportType(payload) {
  if (!payload || typeof payload !== "object") return null;
  if (
    payload.naive &&
    payload.memory &&
    typeof payload.naive.total_tokens === "number" &&
    typeof payload.memory.total_tokens === "number"
  ) {
    return "benchmark";
  }
  if (payload.savings && (payload.stats || payload.recent_activity)) {
    return "live";
  }
  return null;
}

function normalizeBenchmarkReport(raw) {
  const naive = raw.naive || {};
  const memory = raw.memory || {};
  const naiveTotal = Number(naive.total_tokens || 0);
  const memoryTotal = Number(memory.total_tokens || 0);
  const tokensSaved = Number(raw.tokens_saved ?? naiveTotal - memoryTotal);
  let savingsPct = raw.savings_pct;
  if (savingsPct == null && naiveTotal > 0) {
    savingsPct = Math.round(100 * (1 - memoryTotal / naiveTotal) * 10) / 10;
  }

  return {
    ...raw,
    naive: {
      cost_eur: 0,
      ...naive,
      per_turn_tokens: naive.per_turn_tokens || naive.tokens_per_turn || [],
    },
    memory: {
      compression_ratio: 0,
      growth_factor: 0,
      turns: naive.turns || memory.turns || 0,
      stats: {},
      ...memory,
      per_turn_tokens: memory.per_turn_tokens || [],
    },
    savings_pct: Number(savingsPct || 0),
    tokens_saved: tokensSaved,
    cost_saved_eur: Number(raw.cost_saved_eur || 0),
    quality: raw.quality ||
      memory.quality || { passed: 0, total: 10, score_pct: 0, details: [] },
  };
}

function setStatusPill(message, online = true) {
  const pill = document.getElementById("status-pill");
  if (!pill) return;
  pill.classList.toggle("offline", !online);
  pill.innerHTML = `<span class="status-dot"></span> ${message}`;
}

function showImportDemoBanner(type, fileName, meta = "") {
  state.importSource = { type, fileName };
  const banner = document.getElementById("import-demo-banner");
  const badge = document.getElementById("import-demo-badge");
  const title = document.getElementById("import-demo-title");
  const metaEl = document.getElementById("import-demo-meta");
  const eyebrow = document.getElementById("topbar-eyebrow");

  if (banner) banner.hidden = false;
  if (badge) {
    badge.textContent = type === "live" ? "Démo live importée" : "Démo benchmark importée";
    badge.style.background = type === "live" ? "var(--memory)" : "var(--accent)";
  }
  if (title) title.textContent = fileName;
  if (metaEl) {
    metaEl.textContent =
      meta ||
      (type === "live"
        ? "Mode démonstration : métriques live et courbes issues de ce fichier JSON."
        : "Mode démonstration : KPIs, graphiques et pièges issus de ce fichier JSON.");
  }
  if (eyebrow) {
    eyebrow.textContent = type === "live" ? "Démo · Live importé" : "Démo · Benchmark importé";
  }
}

function clearImportDemoBanner() {
  state.importSource = null;
  const banner = document.getElementById("import-demo-banner");
  if (banner) banner.hidden = true;
  updateTopbar(state.activePanel);
}

async function restoreLocalReport() {
  clearImportDemoBanner();
  await loadReport(true);
  showToast("Rapport local rechargé");
}

function importBenchmarkReport(raw, fileName) {
  state.data = normalizeBenchmarkReport(raw);
  state.chartSizes = {};
  updateHero(state.data, true);
  const pct = state.data.savings_pct;
  const turns = state.data.memory?.turns || state.data.naive?.turns || 0;
  showImportDemoBanner(
    "benchmark",
    fileName,
    `Démo benchmark · ${pct}% économie · ${fmt(turns)} tours simulés.`
  );
  setStatusPill(`Démo · ${fileName}`);
  redrawChartsForPanel(state.activePanel);
  showToast(`Démo benchmark — ${fileName}`);
}

function importLiveReport(raw, fileName) {
  state.live = raw;
  updateLivePanel(raw);
  const pct = raw.savings?.savings_pct;
  const turns = raw.savings?.turns || 0;
  showImportDemoBanner(
    "live",
    fileName,
    pct != null
      ? `Démo live · ${pct}% économie · ${fmt(turns)} tours enregistrés.`
      : "Démo live : données MCP importées depuis ce fichier."
  );
  setStatusPill(`Démo live · ${fileName}`);
  switchPanel("live");
  showToast(`Démo live — ${fileName}`);
}

function importReport(file) {
  const input = document.getElementById("import-json");
  if (!file) return;

  const name = file.name.toLowerCase();
  if (!name.endsWith(".json")) {
    showToast("Sélectionnez un fichier .json");
    if (input) input.value = "";
    return;
  }

  if (file.size > IMPORT_MAX_BYTES) {
    showToast("Fichier trop volumineux (max 5 Mo)");
    if (input) input.value = "";
    return;
  }

  const reader = new FileReader();

  reader.onerror = () => {
    showToast("Impossible de lire le fichier");
    if (input) input.value = "";
  };

  reader.onload = () => {
    try {
      const raw = JSON.parse(reader.result);
      const kind = detectImportType(raw);

      if (kind === "benchmark") {
        importBenchmarkReport(raw, file.name);
      } else if (kind === "live") {
        importLiveReport(raw, file.name);
      } else {
        showToast("Format non reconnu — utilisez report.json ou live.json");
      }
    } catch {
      showToast("JSON invalide — vérifiez le fichier");
    } finally {
      if (input) input.value = "";
    }
  };

  reader.readAsText(file, "utf-8");
}

async function runLiveSimulation() {
  if (state.simRunning || !state.data) return;
  state.simRunning = true;
  showToast("Simulation live en cours");
  const naive = state.data.naive.per_turn_tokens || [];
  const memory = state.data.memory.per_turn_tokens || [];
  let n = 0;
  const max = Math.max(naive.length, memory.length);

  const step = () => {
    n += 1;
    drawChart(naive.slice(0, n), memory.slice(0, n));
    const naiveTotal = naive.slice(0, n).reduce((a, b) => a + b, 0);
    const memoryTotal = memory.slice(0, n).reduce((a, b) => a + b, 0);
    document.getElementById("naive-tokens").textContent = fmt(naiveTotal);
    document.getElementById("memory-tokens").textContent = fmt(memoryTotal);
    if (n < max) {
      requestAnimationFrame(step);
    } else {
      updateHero(state.data, true);
      state.simRunning = false;
      showToast("Simulation terminée");
    }
  };
  requestAnimationFrame(step);
}

function bindEvents() {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchPanel(btn.dataset.panel));
  });

  document.getElementById("reload").addEventListener("click", restoreLocalReport);
  document.getElementById("theme-toggle").addEventListener("click", () => {
    setTheme(state.theme === "dark" ? "light" : "dark");
  });
  document.getElementById("export-json").addEventListener("click", exportReport);
  document.getElementById("live-demo").addEventListener("click", runLiveSimulation);
  document.getElementById("import-json").addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (file) importReport(file);
  });
  document.getElementById("import-demo-clear").addEventListener("click", restoreLocalReport);
  document.getElementById("trap-filter").addEventListener("input", () => {
    if (state.data) renderTraps(state.data.quality?.details || state.data.memory?.quality?.details || []);
  });
  document.getElementById("trap-status").addEventListener("change", () => {
    if (state.data) renderTraps(state.data.quality?.details || state.data.memory?.quality?.details || []);
  });

  window.addEventListener(
    "resize",
    debounce(() => {
      state.chartSizes = {};
      redrawChartsForPanel(state.activePanel);
    }, 160)
  );
}

document.addEventListener("DOMContentLoaded", async () => {
  setTheme(state.theme);
  initPlatform3D();
  bindEvents();
  updateTopbar("overview");
  switchPanel("overview");
  startLivePolling();
  await loadReport(true);
});
