import {
  ArrowRight,
  BarChart3,
  Database,
  FileText,
  Search,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import type { Report } from '../lib/api';

const TOOLS = [
  {
    icon: Database,
    name: 'memory_store',
    desc: "Embedding du message puis stockage SQLite avec session, date et importance estimée.",
  },
  {
    icon: Search,
    name: 'memory_search',
    desc: 'Recherche sémantique (cosine) : les k souvenirs les plus proches, classés par pertinence.',
  },
  {
    icon: FileText,
    name: 'memory_summarize',
    desc: 'Résumé extractif des faits clés (noms, numéros, décisions) pour un contexte compact.',
  },
  {
    icon: BarChart3,
    name: 'memory_stats',
    desc: 'Tokens stockés et économisés, nombre d’entrées, backend d’embedding utilisé.',
  },
];

export function Landing({ report }: { report: Report | null }) {
  const savings = report ? `${report.savings_pct.toFixed(1)} %` : '—';
  const quality = report ? `${report.quality.passed}/${report.quality.total}` : '—';
  const backend = report?.embedding_backend ?? 'gemini';

  return (
    <>
      {/* HERO */}
      <section className="relative pt-16 pb-12 sm:pt-24 sm:pb-16">
        <div className="rise mx-auto max-w-3xl text-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-1 text-xs text-[var(--color-muted)]">
            <Sparkles size={13} className="text-[var(--color-accent)]" />
            Model Context Protocol · mémoire pour agents IA
          </span>

          <h1
            className="font-display mt-6 font-black leading-[1.05] tracking-tight"
            style={{ fontSize: 'clamp(2.1rem, 5.2vw, 3.9rem)' }}
          >
            La mémoire externe qui rend vos agents IA{' '}
            <span style={{ color: 'var(--color-mem)' }}>4× moins chers</span>
          </h1>

          <p className="mx-auto mt-5 max-w-2xl text-base text-[var(--color-muted)] sm:text-lg">
            Les agents conversationnels renvoient tout l’historique à chaque tour : le coût en
            tokens croît de façon quadratique. MemBridge ne transmet au modèle que les souvenirs
            pertinents — résumé compact et recherche sémantique. Moins de tokens, qualité intacte.
          </p>

          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <a
              href="#dashboard"
              className="btn inline-flex items-center gap-2 rounded-xl px-5 py-3 text-sm font-semibold text-[#06120c]"
              style={{ background: 'var(--color-mem)' }}
            >
              Voir la démo live <ArrowRight size={16} />
            </a>
            <a
              href="#how"
              className="btn inline-flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-3 text-sm font-semibold"
            >
              Comment ça marche
            </a>
          </div>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-x-8 gap-y-3 text-sm">
            <Metric value={savings} label="tokens économisés" accent="mem" />
            <span className="h-4 w-px bg-[var(--color-border)]" />
            <Metric value={quality} label="questions pièges" accent="text" />
            <span className="h-4 w-px bg-[var(--color-border)]" />
            <Metric value={backend} label="embeddings" accent="accent" />
          </div>
        </div>
      </section>

      {/* PROBLÈME / SOLUTION */}
      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="card rise p-6" style={{ animationDelay: '40ms' }}>
          <div className="flex items-center gap-2.5">
            <span
              className="grid h-9 w-9 place-items-center rounded-lg"
              style={{ background: 'color-mix(in srgb, var(--color-naive) 16%, transparent)' }}
            >
              <TrendingUp size={17} style={{ color: 'var(--color-naive)' }} />
            </span>
            <h3 className="text-base font-bold">Le problème : coût quadratique</h3>
          </div>
          <p className="mt-3 text-sm text-[var(--color-muted)]">
            À 50 tours, l’historique complet est renvoyé 50 fois. La facture et la latence
            explosent, et la fenêtre de contexte finit par saturer — pour répéter sans cesse les
            mêmes informations.
          </p>
        </div>

        <div className="card rise p-6" style={{ animationDelay: '80ms' }}>
          <div className="flex items-center gap-2.5">
            <span
              className="grid h-9 w-9 place-items-center rounded-lg"
              style={{ background: 'color-mix(in srgb, var(--color-mem) 16%, transparent)' }}
            >
              <Sparkles size={17} style={{ color: 'var(--color-mem)' }} />
            </span>
            <h3 className="text-base font-bold">La solution : mémoire sélective</h3>
          </div>
          <p className="mt-3 text-sm text-[var(--color-muted)]">
            MemBridge stocke chaque tour, puis ne remonte que les faits utiles via recherche
            sémantique et un résumé compact. L’agent reçoit ~700 tokens au lieu de 15 000, sans
            perdre les détails importants.
          </p>
        </div>
      </section>

      {/* COMMENT ÇA MARCHE */}
      <section id="how" className="scroll-mt-24">
        <div className="rise mb-5">
          <h2 className="font-display text-xl font-bold tracking-tight">Quatre outils MCP</h2>
          <p className="mt-1 text-sm text-[var(--color-muted)]">
            Un agent externe se connecte au serveur et appelle ces outils à chaque tour.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {TOOLS.map((t, i) => (
            <div
              key={t.name}
              className="card rise p-5"
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <span
                className="grid h-9 w-9 place-items-center rounded-lg"
                style={{ background: 'color-mix(in srgb, var(--color-accent) 14%, transparent)' }}
              >
                <t.icon size={17} style={{ color: 'var(--color-accent)' }} />
              </span>
              <p className="mt-3 font-mono text-sm font-semibold">{t.name}</p>
              <p className="mt-1.5 text-xs leading-relaxed text-[var(--color-muted)]">{t.desc}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

function Metric({
  value,
  label,
  accent,
}: {
  value: string;
  label: string;
  accent: 'mem' | 'accent' | 'text';
}) {
  const color =
    accent === 'mem'
      ? 'var(--color-mem)'
      : accent === 'accent'
        ? 'var(--color-accent)'
        : 'var(--color-text)';
  return (
    <span className="flex items-baseline gap-2">
      <span className="text-lg font-extrabold tabular-nums" style={{ color }}>
        {value}
      </span>
      <span className="text-[var(--color-muted)]">{label}</span>
    </span>
  );
}
