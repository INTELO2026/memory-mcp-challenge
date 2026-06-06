const API = "";

export async function createLiveSession(turns = 50, offline = true) {
  const res = await fetch(`${API}/api/live/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ turns, offline }),
  });
  if (!res.ok) throw new Error("Impossible de creer la session live");
  return res.json();
}

export async function stepLiveSession(sessionId) {
  const res = await fetch(`${API}/api/live/sessions/${sessionId}/step`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!res.ok) throw new Error("Erreur step live");
  return res.json();
}

export async function trapLiveSession(sessionId, query) {
  const res = await fetch(`${API}/api/live/sessions/${sessionId}/trap`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error("Erreur trap live");
  return res.json();
}

export async function fetchTraps() {
  const res = await fetch(`${API}/api/live/traps`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.traps || [];
}

export function appendChatMessage(container, message) {
  const div = document.createElement("div");
  div.className = `bubble ${message.role}`;
  div.innerHTML = `
    <div class="bubble-meta">Tour ${message.turn} · ${message.role} · ${message.source || "live"}</div>
    ${escapeHtml(message.content)}`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

export function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

export function formatNumber(value) {
  return Number(value || 0).toLocaleString("fr-FR");
}
