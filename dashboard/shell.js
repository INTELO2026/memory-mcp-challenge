/** Fragment HTML commun pour le shell dashboard */

export const AMBIENT = `
  <div class="ambient" aria-hidden="true">
    <div class="grid-overlay"></div>
    <div class="orb orb-a"></div>
    <div class="orb orb-b"></div>
    <div class="orb orb-c"></div>
  </div>`;

export function sidebar(active, tagline = "INTELO2026 — Finale") {
  const links = [
    ["live.html", "Arena live"],
    ["index.html", "Benchmark"],
    ["bonus.html", "Bonus"],
    ["demo.html", "Atelier"],
  ];
  const nav = links
    .map(
      ([href, label]) =>
        `<a href="${href}"${href === active ? ' class="active"' : ""}>${label}</a>`
    )
    .join("\n        ");
  return `
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"></div>
        <div>
          <h1>MemBridge</h1>
          <p>${tagline}</p>
        </div>
      </div>
      <nav class="nav">
        ${nav}
      </nav>
      <div class="sidebar-footer">
        Mémoire MCP · tokens mesurés · qualité prouvée
      </div>
    </aside>`;
}
