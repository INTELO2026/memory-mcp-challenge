"use client";

import { motion } from "framer-motion";
import { Brain, CornerDownLeft, Sparkles } from "lucide-react";
import { useState } from "react";
import { api, AskResponse, TrapQuestion } from "@/lib/api";

export function TrapConsole({ traps }: { traps: TrapQuestion[] }) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ask = async (q: string) => {
    const query = q.trim();
    if (!query) return;
    setQuestion(query);
    setLoading(true);
    setError(null);
    try {
      setRes(await api.ask(query));
    } catch (e) {
      setError("Le backend ne répond pas. Lance le serveur (port 8000).");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass p-6 md:p-8">
      <div className="flex items-center gap-2">
        <Sparkles size={18} className="text-emerald-300" />
        <h2 className="text-xl font-semibold tracking-tight">Console de questions pièges</h2>
      </div>
      <p className="mt-1 text-sm text-white/50">
        L'agent répond uniquement grâce aux souvenirs récupérés — pas à l'historique complet.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
        className="mt-5 flex gap-2"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Pose une question dont la réponse a été donnée plus tôt…"
          className="flex-1 rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm outline-none transition focus:border-emerald-400/40"
        />
        <button type="submit" disabled={loading} className="btn-primary">
          {loading ? "…" : <>Demander <CornerDownLeft size={15} /></>}
        </button>
      </form>

      <div className="mt-3 flex flex-wrap gap-2">
        {traps.slice(0, 6).map((t) => (
          <button
            key={t.id}
            onClick={() => ask(t.question)}
            className="chip transition hover:border-emerald-400/30 hover:text-white"
          >
            {t.question}
          </button>
        ))}
      </div>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      {res && !error && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-6 space-y-4"
        >
          <div className="rounded-2xl border border-emerald-400/20 bg-emerald-400/[0.05] p-5">
            <div className="mb-1 flex items-center gap-2 text-xs text-white/40">
              <Brain size={14} className="text-emerald-300" /> Réponse de l'agent ({res.agent_backend})
            </div>
            <p className="text-[15px] leading-relaxed text-white/90">{res.answer}</p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <span className="chip border-emerald-400/20 text-emerald-300">
                {res.tokens.memory} tokens (MemBridge)
              </span>
              <span className="chip border-red-400/20 text-red-300">
                {res.tokens.naive} tokens (naïf)
              </span>
              <span className="chip border-emerald-400/30 text-emerald-200">
                −{res.tokens.saved_pct}% de contexte
              </span>
            </div>
          </div>

          <div>
            <div className="mb-2 text-xs uppercase tracking-wide text-white/40">
              Souvenirs récupérés (similarité)
            </div>
            <div className="space-y-2">
              {res.memories.slice(0, 4).map((m) => (
                <div
                  key={m.id}
                  className="flex items-start gap-3 rounded-xl border border-white/5 bg-black/20 p-3"
                >
                  <span className="mt-0.5 shrink-0 rounded-md bg-emerald-400/10 px-2 py-0.5 font-mono text-xs text-emerald-300">
                    {((m.score ?? 0) * 100).toFixed(0)}%
                  </span>
                  <span className="text-sm text-white/70">{m.content}</span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}
