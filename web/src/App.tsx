import { useEffect, useState } from 'react';
import { Activity, Cpu, Play, Radio, Square, TrendingDown } from 'lucide-react';
import {
  getReport,
  runBenchmark,
  startLive,
  stopLive,
  subscribeStream,
  type Report,
} from './lib/api';
import { useTheme } from './hooks/useTheme';
import { ThemeToggle } from './components/ThemeToggle';
import { Landing } from './components/Landing';
import { SavingsHero } from './components/SavingsHero';
import { StatCard } from './components/StatCard';
import { TokenChart } from './components/TokenChart';
import { QualityPanel } from './components/QualityPanel';
import { MemoryProbe } from './components/MemoryProbe';
import { fmt } from './lib/format';

export default function App() {
  const { theme, toggle } = useTheme();
  const [report, setReport] = useState<Report | null>(null);
  const [running, setRunning] = useState(false);
  const [liveOn, setLiveOn] = useState(false);

  useEffect(() => {
    getReport().then((r) => !r.empty && setReport(r));
    const unsub = subscribeStream((r) => setReport(r));
    return unsub;
  }, []);

  async function handleRun() {
    if (running) return;
    setRunning(true);
    try {
      const r = await runBenchmark();
      if (r && !r.empty) setReport(r);
    } finally {
      setRunning(false);
    }
  }

  async function handleLive() {
    if (liveOn) {
      await stopLive();
      setLiveOn(false);
    } else {
      await startLive(0.25);
      setLiveOn(true);
    }
  }

  const backend = report?.embedding_backend ?? '…';
  const isLive = report?.live === true;

  return (
    <div className="min-h-full">
      {/* NAV */}
      <nav
        className="sticky top-0 z-50 border-b border-[var(--color-border)]"
        style={{
          background: 'color-mix(in srgb, var(--color-bg) 72%, transparent)',
          backdropFilter: 'blur(12px)',
        }}
      >
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <a href="#top" className="flex items-center gap-2.5">
            <span
              className="grid h-8 w-8 place-items-center rounded-lg"
              style={{ background: 'linear-gradient(135deg,#34e3a0,#6ea8ff)' }}
            >
              <Activity size={16} color="#06120c" />
            </span>
            <span className="font-display text-lg font-extrabold tracking-tight">MemBridge</span>
          </a>
          <div className="flex items-center gap-2.5">
            <span className="hidden items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[11px] text-[var(--color-muted)] sm:flex">
              <Cpu size={12} className="text-[var(--color-accent)]" />
              {backend}
            </span>
            <a
              href="#dashboard"
              className="btn hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2 text-sm font-semibold sm:block"
            >
              Dashboard
            </a>
            <ThemeToggle theme={theme} onToggle={toggle} />
          </div>
        </div>
      </nav>

      <main id="top" className="mx-auto flex max-w-6xl flex-col gap-12 px-6 pb-16">
        <Landing report={report} />

        {/* DASHBOARD */}
        <section id="dashboard" className="scroll-mt-20">
          <div className="mb-5 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <div className="flex items-center gap-2.5">
                <h2 className="font-display text-xl font-bold tracking-tight">
                  Tableau de bord en direct
                </h2>
                {isLive && (
                  <span
                    className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold"
                    style={{
                      background: 'color-mix(in srgb, var(--color-accent) 16%, transparent)',
                      color: 'var(--color-accent)',
                    }}
                  >
                    <i className="h-2 w-2 animate-pulse rounded-full bg-[var(--color-accent)]" />
                    LIVE{report?.current_turn ? ` · tour ${report.current_turn}` : ''}
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm text-[var(--color-muted)]">
                Même conversation rejouée en mode naïf et MemBridge.
              </p>
            </div>

            <div className="flex items-center gap-2.5">
              <button
                onClick={handleRun}
                disabled={running}
                className="btn flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2.5 text-sm font-semibold disabled:opacity-60"
              >
                <Play size={15} className="text-[var(--color-accent)]" />
                {running ? 'Calcul…' : 'Benchmark complet'}
              </button>
              <button
                onClick={handleLive}
                className="btn flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-[#06120c]"
                style={{ background: liveOn ? 'var(--color-naive)' : 'var(--color-mem)' }}
              >
                {liveOn ? <Square size={15} /> : <Radio size={15} />}
                {liveOn ? 'Arrêter' : 'Démo live'}
              </button>
            </div>
          </div>

          {!report ? (
            <div className="card grid place-items-center p-16 text-[var(--color-muted)]">
              <p>En attente du rapport…</p>
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
                <div className="lg:col-span-2">
                  <SavingsHero
                    savingsPct={report.savings_pct}
                    savingsTokens={report.savings_tokens}
                    savingsEur={report.cost.savings_eur}
                    turns={report.turns ?? report.naive.cumulative.length}
                  />
                </div>
                <StatCard
                  label="Mode naïf"
                  value={report.naive.total_tokens}
                  suffix="tokens"
                  accent="naive"
                  icon={<TrendingDown size={16} />}
                  hint="historique complet à chaque tour"
                  delay={40}
                />
                <StatCard
                  label="Mode MemBridge"
                  value={report.memory.total_tokens}
                  suffix="tokens"
                  accent="mem"
                  icon={<Activity size={16} />}
                  hint="résumé + souvenirs pertinents"
                  delay={80}
                />
              </div>

              <TokenChart report={report} theme={theme} />

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <QualityPanel report={report} />
                <MemoryProbe />
              </div>
            </div>
          )}
        </section>

        <footer className="border-t border-[var(--color-border)] pt-6 text-center text-xs text-[var(--color-muted)]">
          MemBridge · serveur MCP de mémoire · embeddings {backend}
          {report && (
            <>
              {' '}· tarif {report.cost.price_eur_per_1m} €/M tokens · {fmt(report.savings_tokens)}{' '}
              tokens économisés
            </>
          )}
        </footer>
      </main>
    </div>
  );
}
