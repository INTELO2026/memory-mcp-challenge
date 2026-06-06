/** UI shell partagé — animations, compteurs, reveals */

const LOGO_SVG = `<svg class="logo-svg" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <path d="M4 18 Q14 8 24 18" stroke="#6ee7b7" stroke-width="2" stroke-linecap="round"/>
  <path d="M8 18 L8 22 M20 18 L20 22" stroke="#e8624f" stroke-width="2" stroke-linecap="round"/>
  <circle cx="14" cy="12" r="2.5" fill="#d4af5f"/>
</svg>`;

const BRIDGE_DECO = `<svg class="bridge-deco" viewBox="0 0 600 120" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <path d="M0 80 Q150 20 300 80 T600 80" stroke="currentColor" stroke-width="1"/>
  <path d="M80 80 L80 110 M220 80 L220 110 M380 80 L380 110 M520 80 L520 110" stroke="currentColor" stroke-width="1"/>
</svg>`;

export function bootUi() {
  requestAnimationFrame(() => document.body.classList.add("ui-ready"));
  injectLogo();
  observeReveals();
}

function injectLogo() {
  document.querySelectorAll(".brand-mark").forEach((el) => {
    if (!el.querySelector(".logo-svg")) {
      el.innerHTML = LOGO_SVG;
    }
  });
  if (!document.querySelector(".bridge-deco") && document.querySelector(".ambient")) {
    document.querySelector(".ambient").insertAdjacentHTML("beforeend", BRIDGE_DECO);
  }
}

export function observeReveals() {
  const nodes = document.querySelectorAll(".reveal");
  if (!nodes.length) return;

  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          e.target.classList.add("visible");
          io.unobserve(e.target);
        }
      });
    },
    { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
  );

  nodes.forEach((n) => io.observe(n));
}

export function tickCounter(wrapperEl) {
  if (!wrapperEl) return;
  wrapperEl.classList.add("active", "tick");
  setTimeout(() => wrapperEl.classList.remove("tick"), 280);
}

export function animateMetric(el, targetValue, formatter) {
  if (!el) return;
  const start = parseInt(String(el.textContent).replace(/\D/g, ""), 10) || 0;
  const end = Number(targetValue) || 0;
  if (start === end) {
    el.textContent = formatter(end);
    return;
  }
  const duration = 600;
  const t0 = performance.now();
  const step = (now) => {
    const p = Math.min(1, (now - t0) / duration);
    const eased = 1 - (1 - p) ** 3;
    el.textContent = formatter(Math.round(start + (end - start) * eased));
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

export const CHART_THEME = {
  naive: "#e8624f",
  memory: "#6ee7b7",
  grid: "rgba(244, 242, 236, 0.06)",
  text: "#8b8980",
};

bootUi();
