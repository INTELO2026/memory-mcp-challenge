import { useState } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { searchMemory, type SearchResult } from '../lib/api';

const SUGGESTIONS = [
  'Rappelle-moi mon numéro de contrat',
  "Quelle est mon adresse de livraison ?",
  'Quel code promo ai-je reçu ?',
  'Comment je m’appelle ?',
];

export function MemoryProbe() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SearchResult[] | null>(null);

  async function run(q: string) {
    const value = q.trim();
    if (!value || loading) return;
    setQuery(value);
    setLoading(true);
    try {
      const res = await searchMemory(value, 5);
      setResults(res.results ?? []);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card rise flex flex-col p-5" style={{ animationDelay: '160ms' }}>
      <h2 className="text-sm font-semibold">Interroger la mémoire</h2>
      <p className="mt-1 text-xs text-[var(--color-muted)]">
        L'agent ne relit pas l'historique : il récupère les souvenirs pertinents.
      </p>

      <form
        className="mt-3 flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          run(query);
        }}
      >
        <div className="flex flex-1 items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2.5 focus-within:border-[var(--color-accent)] transition-colors">
          <Search size={15} className="text-[var(--color-muted)]" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Pose une question…"
            className="w-full bg-transparent text-sm outline-none placeholder:text-[var(--color-muted)]"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="btn flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-[#06120c] disabled:opacity-60"
          style={{ background: 'var(--color-mem)' }}
        >
          {loading ? <Loader2 size={15} className="animate-spin" /> : 'Chercher'}
        </button>
      </form>

      <div className="mt-2.5 flex flex-wrap gap-1.5">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => run(s)}
            className="btn rounded-full border border-[var(--color-border)] bg-[var(--color-surface-2)]/50 px-2.5 py-1 text-[11px] text-[var(--color-muted)] hover:text-[var(--color-text)]"
          >
            {s}
          </button>
        ))}
      </div>

      <div className="mt-4 flex flex-col gap-2 overflow-y-auto pr-1" style={{ maxHeight: 240 }}>
        {results?.map((r, i) => (
          <div
            key={r.id}
            className="rise rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)]/40 px-3 py-2"
            style={{ animationDelay: `${i * 40}ms` }}
          >
            <div className="flex items-center justify-between text-[11px] text-[var(--color-muted)]">
              <span>tour {r.turn}</span>
              <span className="tabular-nums" style={{ color: 'var(--color-accent)' }}>
                {(r.score * 100).toFixed(0)} %
              </span>
            </div>
            <p className="mt-0.5 text-xs text-[var(--color-text)]">{r.content}</p>
          </div>
        ))}
        {results && results.length === 0 && !loading && (
          <p className="text-xs text-[var(--color-muted)]">Aucun souvenir trouvé.</p>
        )}
      </div>
    </div>
  );
}
