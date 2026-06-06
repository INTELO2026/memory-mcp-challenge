/* MemBridge — inline DNA helix synced to chat history */
const SESSION = "live-demo";
let helixPlaying = true;
let helixGroup, helixRenderer, helixScene, helixCamera;
let helixStrands = [];
let pulseNodes = [];
let fragmentSprites = [];
let chatHistory = [];
let lastActionTime = performance.now();

const TOOLS = [
  { name: "memory_store", sub: "Store facts", tool: "memory_store" },
  { name: "memory_search", sub: "Semantic retrieve", tool: "memory_search" },
  { name: "memory_summarize", sub: "Compress session", tool: "memory_summarize" },
  { name: "memory_stats", sub: "Token counter", tool: "memory_stats" },
];

const TOOL_PATHS = {
  memory_store: "/membridge/mcp/memory_store",
  memory_search: "/membridge/mcp/memory_search",
  memory_summarize: "/membridge/mcp/memory_summarize",
  memory_stats: "/membridge/mcp/memory_stats",
};

const STOP_WORDS = new Set([
  "user", "assistant", "the", "and", "for", "with", "that", "this", "from", "have", "has",
  "are", "was", "were", "been", "will", "would", "could", "should", "about", "into", "your",
  "you", "they", "them", "their", "what", "when", "where", "which", "while", "just", "like",
  "want", "need", "said", "also", "very", "some", "then", "than", "over", "after", "before",
  "does", "did", "not", "but", "can", "all", "any", "how", "our", "out", "type", "message",
  "watch", "keywords", "orbit", "send", "waiting", "session", "reset", "cleared", "memory",
]);

document.getElementById("nav").innerHTML =
  `<div class="nav-link on"><span>Live Chat</span><span>›</span></div>`;

document.getElementById("tools").innerHTML = TOOLS.map((t, i) =>
  `<div class="tool-card${i === 0 ? " on" : ""}" data-tool="${t.tool}">` +
  `<div class="tool-name">${t.name}</div><div class="tool-sub">${t.sub}</div></div>`
).join("");

/* ── Brain status ── */
function setBrainStatus(brain) {
  const el = document.getElementById("brain-status");
  const groqLbl = document.getElementById("agent-groq-lbl");
  if (!el || !brain) return;
  el.textContent = brain.on ? `${brain.provider} ON` : "brain OFF";
  el.style.color = brain.on ? "#4ade80" : "#f87171";
  if (groqLbl) groqLbl.textContent = brain.on ? brain.provider : "offline";
  document.getElementById("agent-groq")?.classList.toggle("agent-active", brain.on);
}

async function loadBrainStatus() {
  try {
    setBrainStatus(await fetch("/api/status").then((r) => r.json()));
  } catch {
    setBrainStatus({ on: false, provider: "none" });
  }
}

/* ── Keywords from chat history only ── */
function extractKeywords(texts) {
  const found = new Set();
  for (const raw of texts) {
    if (!raw) continue;
    const clean = String(raw).replace(/user:|assistant:|summary:/gi, " ");
    for (const w of clean.match(/[a-zA-ZÀ-ÿ]{3,}/g) || []) {
      const k = w.toLowerCase();
      if (!STOP_WORDS.has(k)) found.add(k);
    }
  }
  return [...found].slice(0, 14);
}

function keywordsFromHistory() {
  return extractKeywords(chatHistory);
}

/* ── 3D helix ── */
const HELIX = { H: 18, TURNS: 4.5, R: 1.35 };

function helixAnchor(idx, total) {
  const t = (idx / Math.max(total, 1)) * Math.PI * 2 * HELIX.TURNS + idx * 0.4;
  const y = ((idx % 12) / 12 - 0.5) * HELIX.H * 0.92;
  return { t, y, x: HELIX.R * Math.cos(t), z: HELIX.R * Math.sin(t) };
}

function makeSmallLabelSprite(num, word, colorHex) {
  const text = `${num}. ${word.toUpperCase()}`;
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  const fontSize = 11;
  ctx.font = `400 ${fontSize}px "Share Tech Mono", monospace`;
  canvas.width = Math.ceil(ctx.measureText(text).width + 6);
  canvas.height = 16;
  ctx.font = `400 ${fontSize}px "Share Tech Mono", monospace`;
  ctx.fillStyle = `#${colorHex.toString(16).padStart(6, "0")}`;
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.shadowColor = ctx.fillStyle;
  ctx.shadowBlur = 6;
  ctx.fillText(text, 3, 8);
  const tex = new THREE.CanvasTexture(canvas);
  const mat = new THREE.SpriteMaterial({
    map: tex, transparent: true, depthWrite: false,
    opacity: 0.88, blending: THREE.AdditiveBlending,
  });
  const sprite = new THREE.Sprite(mat);
  sprite.userData.aspect = canvas.width / canvas.height;
  return sprite;
}

function createFragmentGroup(idx, word, colorHex, total) {
  const { t, y, x, z } = helixAnchor(idx, total);
  const side = idx % 2 === 0 ? 1 : -1;
  const reach = 0.38 + (idx % 3) * 0.1;
  const labelOff = new THREE.Vector3(
    Math.cos(t) * reach * side,
    (idx % 5 - 2) * 0.08,
    Math.sin(t) * reach * side,
  );
  const group = new THREE.Group();
  group.position.set(x, y, z);

  const dot = new THREE.Mesh(
    new THREE.SphereGeometry(0.035, 6, 6),
    new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.95 }),
  );
  const glow = new THREE.Mesh(
    new THREE.SphereGeometry(0.07, 6, 6),
    new THREE.MeshBasicMaterial({ color: colorHex, transparent: true, opacity: 0.25, blending: THREE.AdditiveBlending }),
  );
  const label = makeSmallLabelSprite(idx + 1, word, colorHex);
  label.position.copy(labelOff);
  label.scale.set(0.22 * label.userData.aspect, 0.22, 1);
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 0), labelOff.clone()]),
    new THREE.LineBasicMaterial({ color: 0x67e8f9, transparent: true, opacity: 0.35 }),
  );
  group.add(dot, glow, label, line);
  return { group, label, line, labelOff, dot, glow, phase: idx * 0.9 };
}

function setHelixAlive(alive) {
  const empty = document.getElementById("helix-empty");
  const panel = document.getElementById("memory-panel");
  if (empty) empty.classList.toggle("hidden", alive);
  if (panel) panel.classList.toggle("has-data", alive);
  helixStrands.forEach((s) => { s.material.opacity = alive ? 0.9 : 0.12; });
}

function clearFragments() {
  const fragGroup = helixGroup?.getObjectByName("fragments");
  if (!fragGroup) return;
  fragmentSprites.forEach((f) => {
    fragGroup.remove(f.group);
    f.label.material.map?.dispose();
    f.label.material.dispose();
    f.line.geometry.dispose();
    f.line.material.dispose();
    f.dot.geometry.dispose();
    f.dot.material.dispose();
    f.glow.geometry.dispose();
    f.glow.material.dispose();
  });
  fragmentSprites = [];
}

function rebuildHelixFromHistory() {
  clearFragments();
  const keywords = keywordsFromHistory();
  const fragGroup = helixGroup?.getObjectByName("fragments");
  if (!fragGroup) return;

  const alive = chatHistory.length > 0 && keywords.length > 0;
  setHelixAlive(alive);
  document.getElementById("frag-count").textContent = keywords.length;

  if (!alive) {
    document.getElementById("callout-live").textContent = "Helix empty — send a message";
    return;
  }

  const colors = [0x7dd3fc, 0x67e8f9, 0x94a3b8, 0xf472b6, 0x4ade80];
  keywords.forEach((word, idx) => {
    const frag = createFragmentGroup(idx, word, colors[idx % colors.length], keywords.length);
    fragmentSprites.push(frag);
    fragGroup.add(frag.group);
  });
  document.getElementById("callout-live").textContent =
    `${keywords.length} fragments from chat: ${keywords.slice(0, 4).join(", ")}…`;
}

function initHelix() {
  const mount = document.getElementById("helix-mount");
  const panel = document.getElementById("memory-panel");
  const w = panel.clientWidth || 400;
  const h = panel.clientHeight || 300;

  helixRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  helixRenderer.setSize(w, h);
  helixRenderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  helixRenderer.setClearColor(0x000000, 0);
  mount.appendChild(helixRenderer.domElement);

  helixScene = new THREE.Scene();
  helixCamera = new THREE.PerspectiveCamera(42, w / h, 0.1, 100);
  helixCamera.position.set(0, 0, 9);

  helixGroup = new THREE.Group();
  helixScene.add(helixGroup);

  const cyanPalette = [0x22d3ee, 0x38bdf8, 0x67e8f9, 0x06b6d4, 0x7dd3fc];
  const pinkAccent = 0xf472b6;

  function buildStrand(phase, count) {
    const pos = new Float32Array(count * 3);
    const col = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const t = (i / count) * Math.PI * 2 * HELIX.TURNS;
      const y = (i / count - 0.5) * HELIX.H;
      const r = HELIX.R + (Math.random() - 0.5) * 0.12;
      pos[i * 3] = r * Math.cos(t + phase);
      pos[i * 3 + 1] = y;
      pos[i * 3 + 2] = r * Math.sin(t + phase);
      const c = new THREE.Color(i % 19 === 0 ? pinkAccent : cyanPalette[i % cyanPalette.length]);
      col[i * 3] = c.r; col[i * 3 + 1] = c.g; col[i * 3 + 2] = c.b;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
    const strand = new THREE.Points(geo, new THREE.PointsMaterial({
      size: 0.07, vertexColors: true, transparent: true, opacity: 0.12,
      blending: THREE.AdditiveBlending, depthWrite: false, sizeAttenuation: true,
    }));
    helixStrands.push(strand);
    return strand;
  }

  helixGroup.add(buildStrand(0, 2800));
  helixGroup.add(buildStrand(Math.PI, 2800));

  for (let i = 0; i < 8; i++) {
    const t = (i / 8) * Math.PI * 2 * HELIX.TURNS;
    const y = (i / 8 - 0.5) * HELIX.H;
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(0.2, 0.02, 8, 24),
      new THREE.MeshBasicMaterial({ color: 0x22d3ee, transparent: true, opacity: 0.1 }),
    );
    ring.position.set(HELIX.R * Math.cos(t), y, HELIX.R * Math.sin(t));
    ring.rotation.y = t;
    ring.userData.baseOpacity = 0.1;
    pulseNodes.push(ring);
    helixGroup.add(ring);
  }

  const fragGroup = new THREE.Group();
  fragGroup.name = "fragments";
  helixGroup.add(fragGroup);
  helixGroup.rotation.z = 0.28;

  setHelixAlive(false);

  const t0 = performance.now();
  function tick(now) {
    requestAnimationFrame(tick);
    const e = (now - t0) / 1000;
    if (helixPlaying) {
      helixGroup.rotation.y = e * 0.35;
      helixGroup.rotation.x = Math.sin(e * 0.3) * 0.1;
    }
    pulseNodes.forEach((ring, i) => {
      ring.material.opacity = ring.userData.baseOpacity + Math.sin(e * 2.2 + i) * 0.05;
    });
    fragmentSprites.forEach((f) => {
      const drift = Math.sin(e * 0.6 + f.phase) * 0.04;
      f.label.position.set(
        f.labelOff.x + drift,
        f.labelOff.y + Math.sin(e * 0.9 + f.phase) * 0.03,
        f.labelOff.z + drift * 0.5,
      );
      f.line.geometry.setFromPoints([new THREE.Vector3(0, 0, 0), f.label.position]);
      f.glow.material.opacity = 0.18 + Math.sin(e * 2 + f.phase) * 0.1;
      f.label.material.opacity = 0.7 + Math.sin(e * 1.2 + f.phase) * 0.2;
    });
    helixRenderer.render(helixScene, helixCamera);
  }
  requestAnimationFrame(tick);
  window.addEventListener("resize", resizeHelix);
}

function resizeHelix() {
  if (!helixRenderer) return;
  const panel = document.getElementById("memory-panel");
  const w = panel?.clientWidth || 400;
  const h = panel?.clientHeight || 300;
  helixCamera.aspect = w / h;
  helixCamera.updateProjectionMatrix();
  helixRenderer.setSize(w, h);
}

function flashHelix() {
  helixStrands.forEach((s) => { s.material.opacity = 0.95; });
  setTimeout(() => {
    if (chatHistory.length > 0) helixStrands.forEach((s) => { s.material.opacity = 0.9; });
  }, 500);
  fragmentSprites.slice(-2).forEach((f) => {
    f.glow.material.opacity = 0.7;
    f.dot.material.color.setHex(0xf472b6);
    setTimeout(() => {
      f.glow.material.opacity = 0.25;
      f.dot.material.color.setHex(0xffffff);
    }, 500);
  });
}

/* ── HUD ── */
function setActiveTool(toolName) {
  document.querySelectorAll(".tool-card").forEach((el) => {
    el.classList.toggle("on", el.dataset.tool === toolName);
  });
}

function highlightCallout(n) {
  document.querySelectorAll(".callout").forEach((el) => {
    el.classList.toggle("active", el.dataset.n === String(n));
  });
}

function updateHud(action, summary, searchResults) {
  const tool = action?.tool || "idle";
  const detail = action?.detail || "waiting…";
  document.getElementById("hud-path").textContent = TOOL_PATHS[tool] || "/membridge/mcp/server";
  document.getElementById("hud-last-tool").textContent = `${tool} — ${detail.slice(0, 50)}`;
  document.getElementById("hud-latency").innerHTML =
    `${((performance.now() - lastActionTime) / 1000).toFixed(2)}<span>s</span>`;
  lastActionTime = performance.now();

  const codeMap = {
    memory_store: `memory_store("${detail.slice(0, 40)}…")`,
    memory_search: `memory_search("…") → ${searchResults?.length || 0} hits`,
    memory_summarize: `memory_summarize() → "${(summary || "").slice(0, 40)}…"`,
    memory_stats: `memory_stats() → live`,
  };
  document.getElementById("code-preview").textContent = codeMap[tool] || `# ${tool}`;

  const calloutMap = { memory_store: "1", memory_search: "2", memory_summarize: "3", memory_stats: "4" };
  highlightCallout(calloutMap[tool] || "5");
  if (tool === "memory_store") flashHelix();
}

function drawPulse(n) {
  const c = document.getElementById("pulse");
  const ctx = c.getContext("2d");
  const w = c.width, h = c.height;
  ctx.clearRect(0, 0, w, h);
  ctx.beginPath();
  for (let i = 0; i <= 50; i++) {
    const x = (i / 50) * w;
    const y = h / 2 + Math.sin(i * 0.45 + n * 0.4) * h * 0.38;
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  }
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, "rgba(34,211,238,0.35)");
  g.addColorStop(1, "rgba(34,211,238,0)");
  ctx.lineTo(w, h); ctx.lineTo(0, h); ctx.closePath();
  ctx.fillStyle = g; ctx.fill();
  ctx.strokeStyle = "#22d3ee"; ctx.lineWidth = 2; ctx.stroke();
}

function addBubble(role, text) {
  const d = document.createElement("div");
  d.className = `bubble ${role}`;
  d.textContent = text;
  const box = document.getElementById("messages");
  box.appendChild(d);
  box.scrollTop = box.scrollHeight;
  if (role === "user" || role === "bot") chatHistory.push(text);
}

function applyMetrics(m) {
  document.getElementById("tokens-consumed").textContent = m.tokens_consumed.toLocaleString();
  document.getElementById("retrieves").textContent = m.retrieves;
  document.getElementById("savings-pct").textContent = m.savings_pct;
  document.getElementById("tokens-saved").textContent = m.tokens_saved.toLocaleString();
  document.getElementById("euros-saved").textContent = m.euros_saved;
  document.getElementById("amount-spent").textContent = m.amount_spent_eur;
  document.getElementById("turn-num").textContent = m.turns;
  document.getElementById("hud-turn").textContent = m.turns;
  const max = Math.max(m.stores, m.retrieves, m.summaries, 1);
  document.getElementById("bar-store").style.width = Math.max(m.stores / max * 100, 8) + "%";
  document.getElementById("bar-search").style.width = Math.max(m.retrieves / max * 100, 8) + "%";
  document.getElementById("bar-sum").style.width = Math.max(m.summaries / max * 100, 8) + "%";
  drawPulse(m.retrieves);
}

async function send() {
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  addBubble("user", text);
  highlightCallout("1");
  document.getElementById("agent-you")?.classList.add("agent-active");

  const t0 = performance.now();
  try {
    const data = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text, session: SESSION }),
    }).then((r) => r.json());

    addBubble("bot", data.reply);
    if (data.brain) setBrainStatus(data.brain);
    rebuildHelixFromHistory();
    applyMetrics(data.metrics);

    if (data.actions?.length) {
      document.getElementById("feed").innerHTML = data.actions.slice(0, 5).map((a) =>
        `<div class="mini-line"><b>${a.tool}</b> ${a.detail}</div>`
      ).join("");
      data.actions.slice(0, 4).reverse().forEach((a, i) => {
        setTimeout(() => {
          updateHud(a, data.summary, data.search_results);
          setActiveTool(a.tool);
        }, i * 180);
      });
    }

    document.getElementById("agent-mcp")?.classList.add("agent-active");
    document.getElementById("hud-latency").innerHTML =
      `${((performance.now() - t0) / 1000).toFixed(2)}<span>s</span>`;
  } catch {
    addBubble("sys", "Server offline — run: python dashboard/server.py");
  }
}

async function resetSession() {
  await fetch("/api/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session: SESSION }),
  });
  chatHistory = [];
  document.getElementById("messages").innerHTML =
    '<div class="bubble sys">Session reset — helix cleared</div>';
  document.getElementById("feed").innerHTML =
    '<div class="mini-line muted">Waiting for MCP actions…</div>';
  document.getElementById("hud-last-tool").textContent = "idle — no chat yet";
  document.getElementById("hud-latency").innerHTML = `—<span>s</span>`;
  document.getElementById("code-preview").textContent = "# waiting for chat…";
  document.getElementById("turn-num").textContent = "0";
  document.getElementById("hud-turn").textContent = "0";
  document.getElementById("frag-count").textContent = "0";
  applyMetrics({
    tokens_consumed: 0, retrieves: 0, savings_pct: 0, tokens_saved: 0,
    euros_saved: 0, amount_spent_eur: 0, turns: 0, stores: 0, summaries: 0,
  });
  rebuildHelixFromHistory();
  document.querySelectorAll(".agent").forEach((a) => a.classList.remove("agent-active"));
}

function bindChat() {
  const input = document.getElementById("chat-input");
  document.getElementById("send-btn").onclick = send;
  document.getElementById("reset-btn").onclick = resetSession;
  document.getElementById("play-btn").onclick = () => {
    helixPlaying = !helixPlaying;
    document.getElementById("play-btn").textContent = helixPlaying ? "⏸" : "▶";
  };
  input.onkeydown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };
  setTimeout(() => input.focus(), 200);
}

function initChatResizer() {
  const resizer = document.getElementById("chat-resizer");
  const wrap = document.getElementById("viz-wrap");
  if (!resizer || !wrap) return;
  let startY = 0, startH = 0;
  const onMove = (e) => {
    const next = Math.min(window.innerHeight * 0.55, Math.max(120, startH + (startY - e.clientY)));
    wrap.style.setProperty("--chat-h", `${next}px`);
    resizeHelix();
  };
  const onUp = () => {
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  };
  resizer.addEventListener("mousedown", (e) => {
    e.preventDefault();
    startY = e.clientY;
    startH = document.getElementById("chat-dock").offsetHeight;
    document.body.style.cursor = "ns-resize";
    document.body.style.userSelect = "none";
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  });
}

async function loadSession() {
  try {
    const data = await fetch(`/api/stats?session=${SESSION}`).then((r) => r.json());
    if (data.metrics?.turns > 0) {
      applyMetrics(data.metrics);
      if (data.actions?.length) {
        document.getElementById("feed").innerHTML = data.actions.slice(0, 5).map((a) =>
          `<div class="mini-line"><b>${a.tool}</b> ${a.detail}</div>`
        ).join("");
        for (const a of data.actions) {
          const m = a.detail.match(/user: (.+)/i) || a.detail.match(/assistant: (.+)/i);
          if (m) chatHistory.push(m[1]);
        }
        rebuildHelixFromHistory();
      }
    }
  } catch { /* fresh session */ }
}

window.addEventListener("load", () => {
  bindChat();
  initChatResizer();
  loadBrainStatus();
  setTimeout(() => { initHelix(); loadSession(); }, 80);
  drawPulse(0);
});
