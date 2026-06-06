const REPORT_PATHS = [
  "/benchmark/results/benchmark_results.json",
  "/benchmark/results/report.json",
];

let tokenChart = null;

export async function fetchReport() {
  for (const path of REPORT_PATHS) {
    try {
      const res = await fetch(`${path}?t=${Date.now()}`);
      if (!res.ok) continue;
      const data = await res.json();
      return { data, path };
    } catch {
      /* try next */
    }
  }
  return null;
}

export function formatNumber(value) {
  return Number(value || 0).toLocaleString("fr-FR");
}

export function normalizeQuality(data) {
  if (!data?.quality) return { memory: null, naive: null };
  if (data.quality.memory) return data.quality;
  return { memory: data.quality, naive: null };
}

export function renderTokenChart(canvasId, data) {
  const canvas = document.getElementById(canvasId);
  if (!canvas || !window.Chart) return;

  const labels = data.chart?.labels || [];
  const naive = data.chart?.naive_cumulative || [];
  const memory = data.chart?.memory_cumulative || [];

  if (tokenChart) tokenChart.destroy();
  tokenChart = new Chart(canvas.getContext("2d"), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Naïf — historique complet",
          data: naive,
          borderColor: "#e8624f",
          backgroundColor: "rgba(232, 98, 79, 0.08)",
          tension: 0.35,
          fill: true,
          pointRadius: 0,
        },
        {
          label: "MemBridge — résumé + search",
          data: memory,
          borderColor: "#6ee7b7",
          backgroundColor: "rgba(110, 231, 183, 0.08)",
          tension: 0.35,
          fill: true,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: "#f4f2ec", font: { family: "DM Sans" } } },
        tooltip: {
          backgroundColor: "rgba(8,8,10,0.9)",
          borderColor: "rgba(244,242,236,0.1)",
          borderWidth: 1,
          callbacks: {
            label: (ctx) =>
              `${ctx.dataset.label}: ${formatNumber(ctx.parsed.y)} tokens`,
          },
        },
      },
      scales: {
        x: {
          ticks: { color: "#8b8980", maxTicksLimit: 14 },
          grid: { color: "rgba(244,242,236,0.05)" },
        },
        y: {
          ticks: { color: "#8b8980" },
          grid: { color: "rgba(244,242,236,0.05)" },
        },
      },
    },
  });
}

export function renderTrapTable(containerId, quality) {
  const container = document.getElementById(containerId);
  if (!container || !quality?.details) {
    if (container) {
      container.innerHTML =
        '<p class="hint">Lancez le benchmark pour afficher les questions pièges.</p>';
    }
    return;
  }

  const rows = quality.details
    .map(
      (item) => `
      <tr>
        <td><span class="badge ${item.passed ? "ok" : "ko"}">${item.passed ? "OK" : "KO"}</span></td>
        <td>${escapeHtml(item.query)}</td>
        <td><code>${escapeHtml(item.expected)}</code></td>
        <td class="hint">${escapeHtml(truncate(item.top_content || "—", 120))}</td>
      </tr>`
    )
    .join("");

  container.innerHTML = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Statut</th>
            <th>Question piège</th>
            <th>Réponse attendue</th>
            <th>Top-1 memory_search</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

export function bindDashboard({ onUpdate } = {}) {
  async function refresh() {
    const result = await fetchReport();
    if (result) {
      onUpdate?.(result.data, result.path);
    } else {
      onUpdate?.(null, null);
    }
  }

  refresh();
  setInterval(refresh, 2000);
  return refresh;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function truncate(text, max) {
  const value = String(text);
  return value.length <= max ? value : `${value.slice(0, max)}…`;
}
