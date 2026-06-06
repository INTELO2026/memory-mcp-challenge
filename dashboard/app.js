"use strict";

const REPORT_URL = "results/report.json";
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const fmt = (n) => Math.round(n ?? 0).toLocaleString("fr-FR");
const fmtEur = (n) => (n ?? 0).toLocaleString("fr-FR", { minimumFractionDigits: 4, maximumFractionDigits: 6 });
const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);

let STATE = { naive: [], memory: [], progress: 1, hover: null };

async function load() {
  let data;
  try {
    const res = await fetch(REPORT_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    data = await res.json();
  } catch {
    document.getElementById("savings-pct").textContent = "—";
    document.getElementById("quality-note").textContent =
      "Aucun rapport. Lancez : python -m benchmark.harness";
    return;
  }
  render(data);
}

// --- Compteur anime (count-up) ---
function countUp(el, to, { decimals = 0, suffix = "", prefix = "", eur = false } = {}) {
  if (REDUCED) {
    el.textContent = prefix + (eur ? fmtEur(to) : to.toFixed(decimals)) + suffix;
    return;
  }
  const dur = 1100;
  const start = performance.now();
  function step(now) {
    const t = Math.min(1, (now - start) / dur);
    const v = to * easeOutCubic(t);
    el.textContent = prefix + (eur ? fmtEur(v) : (decimals ? v.toFixed(decimals) : fmt(v))) + suffix;
    if (t < 1) requestAnimationFrame(step);
    else el.textContent = prefix + (eur ? fmtEur(to) : (decimals ? to.toFixed(decimals) : fmt(to))) + suffix;
  }
  requestAnimationFrame(step);
}

function render(d) {
  document.getElementById("embedder-badge").textContent = "embedder: " + (d.embedder || "—");

  countUp(document.getElementById("savings-pct"), d.savings_pct, { decimals: 1, suffix: "%" });
  countUp(document.getElementById("savings-tokens"), d.savings_tokens || 0);
  countUp(document.getElementById("savings-eur"), d.pricing?.savings_eur || 0, { eur: true, suffix: " €" });
  countUp(document.getElementById("naive-tokens"), d.naive.total_tokens || 0);
  countUp(document.getElementById("memory-tokens"), d.memory.total_tokens || 0);
  document.getElementById("naive-eur").textContent = fmtEur(d.pricing?.naive_eur);
  document.getElementById("memory-eur").textContent = fmtEur(d.pricing?.memory_eur);

  document.getElementById("compression").textContent =
    Math.round((d.memory.compression_ratio ?? 0) * 100) + "%";
  document.getElementById("growth").textContent = "×" + (d.memory.growth_factor ?? 0).toFixed(2);

  const q = d.quality;
  if (q) {
    document.getElementById("quality-passed").textContent = q.passed;
    document.getElementById("quality-total").textContent = q.total;
    setTimeout(() => (document.getElementById("quality-bar").style.width = q.score_pct + "%"), 200);
    const list = document.getElementById("quality-list");
    list.innerHTML = "";
    (q.details || []).forEach((it, i) => {
      const li = document.createElement("li");
      li.style.animationDelay = i * 70 + "ms";
      li.innerHTML =
        `<span class="qmark ${it.memory_ok ? "ok" : "ko"}">${it.memory_ok ? "✓" : "✕"}</span>` +
        `<span>${it.question}</span>` +
        `<span class="exp">${it.expected}</span>`;
      list.appendChild(li);
    });
  }

  STATE.naive = d.naive.cumulative || [];
  STATE.memory = d.memory.cumulative || [];
  setupControls();
  revealCards();
  playAnimation();
}

// --- Geometrie partagee du graphe ---
function geom(canvas) {
  const pad = { l: 64, r: 22, t: 22, b: 38 };
  const n = Math.max(STATE.naive.length, STATE.memory.length, 2);
  const maxY = Math.max(1, ...STATE.naive, ...STATE.memory);
  return {
    pad,
    n,
    maxY,
    x: (i) => pad.l + (i / (n - 1)) * (canvas.width - pad.l - pad.r),
    y: (v) => canvas.height - pad.b - (v / maxY) * (canvas.height - pad.t - pad.b),
  };
}

function colors() {
  const css = getComputedStyle(document.documentElement);
  const get = (k, f) => css.getPropertyValue(k).trim() || f;
  return {
    red: get("--red", "#f4524d"),
    green: get("--green", "#2fd17a"),
    line: get("--line", "#2a3565"),
    muted: get("--muted", "#93a0c8"),
  };
}

// progress in [0..1] -> nombre de tours affiches (fractionnaire)
function drawChart(progress) {
  const canvas = document.getElementById("chart");
  const ctx = canvas.getContext("2d");
  const W = canvas.width;
  const H = canvas.height;
  const { pad, n, maxY, x, y } = geom(canvas);
  const c = colors();
  ctx.clearRect(0, 0, W, H);

  // Grille + axes Y
  ctx.font = "12px Inter, system-ui, sans-serif";
  ctx.lineWidth = 1;
  const steps = 4;
  for (let s = 0; s <= steps; s++) {
    const val = (maxY / steps) * s;
    const yy = y(val);
    ctx.strokeStyle = c.line;
    ctx.globalAlpha = 0.45;
    ctx.beginPath();
    ctx.moveTo(pad.l, yy);
    ctx.lineTo(W - pad.r, yy);
    ctx.stroke();
    ctx.globalAlpha = 1;
    ctx.fillStyle = c.muted;
    ctx.fillText(Math.round(val).toLocaleString("fr-FR"), 6, yy + 4);
  }
  ctx.fillStyle = c.muted;
  ctx.fillText("tour 1", pad.l, H - 12);
  ctx.fillText("tour " + n, W - pad.r - 44, H - 12);

  const head = Math.max(1, progress * (n - 1)); // index fractionnaire de la tete
  const lastIdx = Math.floor(head);
  const frac = head - lastIdx;

  // Construit la liste de points visibles jusqu'a la tete (avec interpolation)
  const visible = (series) => {
    const pts = [];
    for (let i = 0; i <= lastIdx && i < series.length; i++) pts.push([x(i), y(series[i])]);
    if (lastIdx + 1 < series.length && frac > 0) {
      const v = series[lastIdx] + (series[lastIdx + 1] - series[lastIdx]) * frac;
      pts.push([x(lastIdx + frac), y(v)]);
    }
    return pts;
  };

  const nv = visible(STATE.naive);
  const mv = visible(STATE.memory);

  // Zone de divergence (l'economie) entre les deux courbes
  if (nv.length && mv.length) {
    ctx.beginPath();
    nv.forEach((p, i) => (i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1])));
    for (let i = mv.length - 1; i >= 0; i--) ctx.lineTo(mv[i][0], mv[i][1]);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, pad.t, 0, H - pad.b);
    grad.addColorStop(0, c.green + "33");
    grad.addColorStop(1, c.green + "08");
    ctx.fillStyle = grad;
    ctx.fill();
  }

  const drawLine = (pts, color) => {
    if (!pts.length) return;
    // aire sous la courbe
    ctx.beginPath();
    pts.forEach((p, i) => (i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1])));
    ctx.lineTo(pts[pts.length - 1][0], y(0));
    ctx.lineTo(pts[0][0], y(0));
    ctx.closePath();
    const g = ctx.createLinearGradient(0, pad.t, 0, H - pad.b);
    g.addColorStop(0, color + "44");
    g.addColorStop(1, color + "04");
    ctx.fillStyle = g;
    ctx.fill();
    // trait
    ctx.beginPath();
    pts.forEach((p, i) => (i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1])));
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.lineJoin = "round";
    ctx.stroke();
    // tete lumineuse
    const hd = pts[pts.length - 1];
    ctx.beginPath();
    ctx.arc(hd[0], hd[1], 4.5, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = 12;
    ctx.fill();
    ctx.shadowBlur = 0;
  };

  drawLine(nv, c.red);
  drawLine(mv, c.green);

  // Curseur de survol
  if (STATE.hover != null) {
    const i = STATE.hover;
    const xx = x(i);
    ctx.strokeStyle = c.muted;
    ctx.globalAlpha = 0.5;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(xx, pad.t);
    ctx.lineTo(xx, H - pad.b);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
    [[STATE.naive, c.red], [STATE.memory, c.green]].forEach(([s, col]) => {
      if (s[i] == null) return;
      ctx.beginPath();
      ctx.arc(xx, y(s[i]), 4, 0, Math.PI * 2);
      ctx.fillStyle = col;
      ctx.fill();
    });
  }

  updateReadout(STATE.hover != null ? STATE.hover : Math.round(head));
}

function updateReadout(i) {
  const n = STATE.naive[i] ?? 0;
  const m = STATE.memory[i] ?? 0;
  document.getElementById("live-turn").textContent = i + 1;
  document.getElementById("live-naive").textContent = fmt(n);
  document.getElementById("live-memory").textContent = fmt(m);
  document.getElementById("live-gap").textContent = fmt(n - m);
}

function playAnimation() {
  const scrubber = document.getElementById("scrubber");
  if (REDUCED) {
    STATE.progress = 1;
    drawChart(1);
    scrubber.value = scrubber.max;
    return;
  }
  const dur = 1800;
  const start = performance.now();
  function step(now) {
    const t = Math.min(1, (now - start) / dur);
    STATE.progress = easeOutCubic(t);
    STATE.hover = null;
    drawChart(STATE.progress);
    scrubber.value = Math.round(STATE.progress * scrubber.max);
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

let controlsBound = false;
function setupControls() {
  const scrubber = document.getElementById("scrubber");
  const n = Math.max(STATE.naive.length, STATE.memory.length, 2);
  scrubber.max = String(n - 1);
  scrubber.value = String(n - 1);

  if (controlsBound) return;
  controlsBound = true;

  document.getElementById("play-btn").addEventListener("click", playAnimation);

  scrubber.addEventListener("input", () => {
    const idx = Number(scrubber.value);
    STATE.hover = null;
    STATE.progress = idx / (Number(scrubber.max) || 1);
    drawChart(STATE.progress);
  });

  const canvas = document.getElementById("chart");
  const tooltip = document.getElementById("tooltip");
  canvas.addEventListener("mousemove", (e) => {
    const rect = canvas.getBoundingClientRect();
    const { pad, n: nn } = geom(canvas);
    const scaleX = canvas.width / rect.width;
    const px = (e.clientX - rect.left) * scaleX;
    const ratio = (px - pad.l) / (canvas.width - pad.l - pad.r);
    const i = Math.round(Math.max(0, Math.min(1, ratio)) * (nn - 1));
    STATE.hover = i;
    drawChart(STATE.progress);
    const nv = STATE.naive[i] ?? 0;
    const mv = STATE.memory[i] ?? 0;
    tooltip.hidden = false;
    tooltip.style.left = (e.clientX - rect.left) + "px";
    tooltip.style.top = (e.clientY - rect.top) + "px";
    tooltip.innerHTML =
      `<strong>tour ${i + 1}</strong>` +
      `<span class="t-naive">naïf : ${fmt(nv)}</span>` +
      `<span class="t-memory">MemBridge : ${fmt(mv)}</span>` +
      `<span class="t-gap">écart : ${fmt(nv - mv)}</span>`;
  });
  canvas.addEventListener("mouseleave", () => {
    STATE.hover = null;
    tooltip.hidden = true;
    drawChart(STATE.progress);
  });
}

function revealCards() {
  const cards = document.querySelectorAll(".card, .savings-banner");
  if (REDUCED || !("IntersectionObserver" in window)) {
    cards.forEach((c) => c.classList.add("in"));
    return;
  }
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) {
          en.target.classList.add("in");
          io.unobserve(en.target);
        }
      });
    },
    { threshold: 0.12 }
  );
  cards.forEach((c, i) => {
    c.style.transitionDelay = Math.min(i * 60, 360) + "ms";
    io.observe(c);
  });
}

load();
