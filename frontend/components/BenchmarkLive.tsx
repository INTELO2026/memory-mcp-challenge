"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Play, RotateCcw, TrendingDown, Zap } from "lucide-react";
import { useRef, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { BenchEvent, streamBenchmark } from "@/lib/api";
import { AnimatedNumber } from "./AnimatedNumber";

type Point = { turn: number; naif: number; membridge: number };

export function BenchmarkLive() {
  const [points, setPoints] = useState<Point[]>([]);
  const [naive, setNaive] = useState(0);
  const [memory, setMemory] = useState(0);
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState<null | { saved: number; pct: number }>(null);
  const [last, setLast] = useState<{ role: string; content: string; turn: number } | null>(null);
  const closeRef = useRef<() => void>();

  const start = () => {
    setPoints([]);
    setNaive(0);
    setMemory(0);
    setDone(null);
    setLast(null);
    setRunning(true);
    closeRef.current = streamBenchmark(
      (e: BenchEvent) => {
        if (e.type === "turn") {
          setNaive(e.naive_cumulative);
          setMemory(e.memory_cumulative);
          setLast({ role: e.role, content: e.content, turn: e.turn });
          setPoints((p) => [
            ...p,
            { turn: e.turn, naif: e.naive_cumulative, membridge: e.memory_cumulative },
          ]);
        } else if (e.type === "done") {
          setDone({ saved: e.saved_tokens, pct: e.savings_pct });
          setRunning(false);
        }
      },
      { delayMs: 170, onClose: () => setRunning(false) },
    );
  };

  const reset = () => {
    closeRef.current?.();
    setPoints([]);
    setNaive(0);
    setMemory(0);
    setDone(null);
    setLast(null);
    setRunning(false);
  };

  return (
    <div className="glass p-6 md:p-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Benchmark live — naïf vs MemBridge</h2>
          <p className="mt-1 text-sm text-white/50">
            Rejoue la même conversation. Le compteur rouge explose, le vert reste plat.
          </p>
        </div>
        <div className="flex gap-3">
          <button onClick={start} disabled={running} className="btn-primary">
            <Play size={16} /> {running ? "En cours…" : "Lancer la démo"}
          </button>
          <button onClick={reset} className="btn-ghost">
            <RotateCcw size={16} /> Reset
          </button>
        </div>
      </div>

      <div className="mt-7 grid gap-4 md:grid-cols-2">
        <Counter label="Mode naïf — historique complet" value={naive} color="naive" />
        <Counter label="Mode MemBridge — résumé + souvenirs" value={memory} color="memory" />
      </div>

      <div className="mt-6 h-[280px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id="gN" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#f87171" stopOpacity={0.5} />
                <stop offset="100%" stopColor="#f87171" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gM" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#34d399" stopOpacity={0.5} />
                <stop offset="100%" stopColor="#34d399" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
            <XAxis
              dataKey="turn"
              tick={{ fill: "rgba(255,255,255,0.4)", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              label={{ value: "tour", fill: "rgba(255,255,255,0.3)", fontSize: 11, dy: 14 }}
            />
            <YAxis
              tick={{ fill: "rgba(255,255,255,0.4)", fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={56}
              tickFormatter={(v) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${v}`)}
            />
            <Tooltip
              contentStyle={{
                background: "#0b1020",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: 12,
                fontSize: 12,
              }}
              labelStyle={{ color: "rgba(255,255,255,0.6)" }}
              formatter={(v: number, n) => [v.toLocaleString("fr-FR") + " tokens", n]}
            />
            <Area
              type="monotone"
              dataKey="naif"
              name="Naïf"
              stroke="#f87171"
              strokeWidth={2.5}
              fill="url(#gN)"
              isAnimationActive={false}
              dot={false}
            />
            <Area
              type="monotone"
              dataKey="membridge"
              name="MemBridge"
              stroke="#34d399"
              strokeWidth={2.5}
              fill="url(#gM)"
              isAnimationActive={false}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <AnimatePresence>
        {last && running && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="mt-3 truncate rounded-lg border border-white/5 bg-black/20 px-4 py-2 text-xs text-white/50"
          >
            <span className="text-white/40">tour {last.turn} · {last.role} →</span> {last.content}
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {done && (
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-emerald-400/20 bg-emerald-400/[0.06] p-5 shadow-glow"
          >
            <div className="flex items-center gap-3">
              <div className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-400/15 text-emerald-300">
                <TrendingDown size={22} />
              </div>
              <div>
                <div className="text-sm text-white/50">Économie totale</div>
                <div className="text-2xl font-bold text-emerald-300">
                  −<AnimatedNumber value={done.pct} /> % de tokens
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm text-white/70">
              <Zap size={16} className="text-emerald-300" />
              <AnimatedNumber value={done.saved} className="font-semibold text-white" /> tokens
              épargnés sur la conversation
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function Counter({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: "naive" | "memory";
}) {
  const isNaive = color === "naive";
  return (
    <div
      className={`relative overflow-hidden rounded-2xl border p-5 ${
        isNaive ? "border-red-400/20 bg-red-500/[0.05]" : "border-emerald-400/20 bg-emerald-500/[0.05]"
      }`}
    >
      <div className="text-xs font-medium uppercase tracking-wide text-white/40">{label}</div>
      <div
        className={`mt-2 text-4xl font-bold tracking-tight ${
          isNaive ? "text-red-400" : "text-emerald-300"
        }`}
      >
        <AnimatedNumber value={value} />
        <span className="ml-2 text-sm font-normal text-white/30">tokens</span>
      </div>
    </div>
  );
}
