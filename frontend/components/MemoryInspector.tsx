"use client";

import { Database, Layers, ListOrdered } from "lucide-react";
import { useEffect, useState } from "react";
import { api, Memory } from "@/lib/api";

export function MemoryInspector() {
  const [mode, setMode] = useState<"chrono" | "rank">("rank");
  const [entries, setEntries] = useState<Memory[]>([]);
  const [count, setCount] = useState(0);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        if (mode === "chrono") {
          const d = await api.memory();
          if (alive) {
            setEntries(d.entries);
            setCount(d.count);
          }
        } else {
          const d = await api.rank();
          if (alive) {
            setEntries(d.results);
            setCount(d.count);
          }
        }
      } catch {
        /* backend offline */
      }
    })();
    return () => {
      alive = false;
    };
  }, [mode]);

  return (
    <div className="glass p-6 md:p-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Database size={18} className="text-emerald-300" />
          <h2 className="text-xl font-semibold tracking-tight">Inspecteur de mémoire</h2>
          <span className="chip ml-1">{count} souvenirs</span>
        </div>
        <div className="flex rounded-xl border border-white/10 bg-black/20 p-1 text-xs">
          <button
            onClick={() => setMode("rank")}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 transition ${
              mode === "rank" ? "bg-white/10 text-white" : "text-white/50"
            }`}
          >
            <ListOrdered size={13} /> Pertinence
          </button>
          <button
            onClick={() => setMode("chrono")}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 transition ${
              mode === "chrono" ? "bg-white/10 text-white" : "text-white/50"
            }`}
          >
            <Layers size={13} /> Chronologie
          </button>
        </div>
      </div>

      <div className="mt-5 max-h-[420px] space-y-2 overflow-y-auto pr-1">
        {entries.map((m) => (
          <div key={m.id} className="rounded-xl border border-white/5 bg-black/20 p-3">
            <div className="flex items-center justify-between gap-3 text-xs text-white/40">
              <span className="font-mono">tour {m.turn}</span>
              <span>importance {(m.importance * 100).toFixed(0)}%</span>
            </div>
            <p className="mt-1.5 text-sm text-white/75">{m.content}</p>
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/5">
              <div
                className="h-full rounded-full bg-gradient-to-r from-emerald-400/60 to-emerald-300"
                style={{ width: `${Math.max(4, m.importance * 100)}%` }}
              />
            </div>
          </div>
        ))}
        {entries.length === 0 && (
          <p className="py-8 text-center text-sm text-white/40">
            Démarre le backend pour inspecter la mémoire.
          </p>
        )}
      </div>
    </div>
  );
}
