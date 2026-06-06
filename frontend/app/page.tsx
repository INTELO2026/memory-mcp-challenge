"use client";

import { motion } from "framer-motion";
import { Activity, BadgeCheck, Cpu, Github, Layers3, Wifi, WifiOff } from "lucide-react";
import { useEffect, useState } from "react";
import { BenchmarkLive } from "@/components/BenchmarkLive";
import { MemoryInspector } from "@/components/MemoryInspector";
import { TrapConsole } from "@/components/TrapConsole";
import { api, Health, Report, Scenario } from "@/lib/api";

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [h, s] = await Promise.all([api.health(), api.scenario()]);
        setHealth(h);
        setScenario(s);
        setOnline(true);
        api.report().then(setReport).catch(() => {});
      } catch {
        setOnline(false);
      }
    })();
  }, []);

  return (
    <main className="relative mx-auto min-h-screen max-w-6xl px-5 pb-24 pt-8">
      {/* Header */}
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-emerald-300 to-emerald-500 text-ink-950 shadow-glow">
            <Layers3 size={20} strokeWidth={2.4} />
          </div>
          <div>
            <div className="text-lg font-semibold leading-none tracking-tight">MemBridge</div>
            <div className="text-xs text-white/40">Mémoire partagée pour agents IA · MCP</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill online={online} />
          <a
            href="https://github.com/INTELO2026/memory-mcp-challenge"
            target="_blank"
            className="btn-ghost hidden sm:inline-flex"
          >
            <Github size={16} /> Dépôt
          </a>
        </div>
      </header>

      {/* Hero */}
      <section className="mt-14 grid-bg rounded-3xl border border-white/[0.06] p-8 md:p-12">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <div className="chip mb-5">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse-soft" />
            Hackathon INTELO2026 · Prototype + démo live
          </div>
          <h1 className="max-w-3xl text-4xl font-bold leading-[1.1] tracking-tight md:text-6xl">
            La mémoire qui rend vos agents{" "}
            <span className="bg-gradient-to-r from-emerald-200 to-emerald-400 bg-clip-text text-transparent">
              plus légers, pas amnésiques.
            </span>
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-white/55">
            Un serveur MCP qui stocke le contexte utile et ne restitue que l'essentiel. Résultat :
            une chute drastique des tokens, sans perdre une info.
          </p>
        </motion.div>

        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Metric
            label="Économie de tokens"
            value={report ? `−${report.savings.pct}%` : "—"}
            accent
            icon={<Activity size={16} />}
          />
          <Metric
            label="Qualité (questions pièges)"
            value={report ? `${report.quality.passed}/${report.quality.total}` : "—"}
            icon={<BadgeCheck size={16} />}
          />
          <Metric
            label="Embeddings"
            value={health ? short(health.embedder) : "—"}
            icon={<Cpu size={16} />}
          />
          <Metric
            label="Agent"
            value={health ? health.agent_backend : "—"}
            icon={<Layers3 size={16} />}
          />
        </div>
      </section>

      {online === false && (
        <div className="mt-6 rounded-2xl border border-amber-400/20 bg-amber-400/[0.06] p-4 text-sm text-amber-200/90">
          Backend hors-ligne. Lance&nbsp;:{" "}
          <code className="rounded bg-black/30 px-1.5 py-0.5 font-mono">
            uvicorn webapp.server:app --port 8000
          </code>
        </div>
      )}

      <div className="mt-10 space-y-8">
        <BenchmarkLive />
        <div className="grid gap-8 lg:grid-cols-2">
          <TrapConsole traps={scenario?.trap_questions ?? []} />
          <MemoryInspector />
        </div>
        {report && <ScaleStrip report={report} />}
      </div>

      <footer className="mt-16 text-center text-xs text-white/30">
        MemBridge · serveur MCP de mémoire · {report ? `rapport ${report.generated_at}` : "—"}
      </footer>
    </main>
  );
}

function StatusPill({ online }: { online: boolean | null }) {
  if (online === null) return <span className="chip">connexion…</span>;
  return online ? (
    <span className="chip border-emerald-400/20 text-emerald-300">
      <Wifi size={13} /> backend en ligne
    </span>
  ) : (
    <span className="chip border-red-400/20 text-red-300">
      <WifiOff size={13} /> hors-ligne
    </span>
  );
}

function Metric({
  label,
  value,
  icon,
  accent,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  accent?: boolean;
}) {
  return (
    <div className="glass p-5">
      <div className="flex items-center gap-2 text-xs text-white/40">
        {icon} {label}
      </div>
      <div
        className={`mt-2 text-2xl font-bold tracking-tight ${
          accent ? "text-emerald-300" : "text-white"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

function ScaleStrip({ report }: { report: Report }) {
  return (
    <div className="glass flex flex-wrap items-center justify-between gap-6 p-6">
      <div>
        <div className="text-xs uppercase tracking-wide text-white/40">Projection de coût</div>
        <div className="mt-1 text-sm text-white/60">
          À {report.savings.price_per_mtok} €/M tokens · {report.scenario.turns} tours
        </div>
      </div>
      <div className="flex flex-wrap gap-8">
        <ScaleItem label="par conversation" value={`${report.savings.euros.toFixed(4)} €`} />
        <ScaleItem
          label="pour 1 000 conv."
          value={`${report.savings.euros_per_1k_conversations.toFixed(2)} €`}
        />
        <ScaleItem
          label="pour 100 000 conv."
          value={`${report.savings.euros_per_100k_conversations.toFixed(0)} €`}
          accent
        />
      </div>
    </div>
  );
}

function ScaleItem({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <div className={`text-2xl font-bold ${accent ? "text-emerald-300" : "text-white"}`}>
        {value}
      </div>
      <div className="text-xs text-white/40">{label}</div>
    </div>
  );
}

function short(name: string) {
  if (name.startsWith("gemini:")) return "Gemini";
  if (name.startsWith("local:")) return "Local";
  return name;
}
