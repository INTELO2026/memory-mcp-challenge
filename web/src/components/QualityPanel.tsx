import { Check, X } from 'lucide-react';
import type { Report } from '../lib/api';

export function QualityPanel({ report }: { report: Report }) {
  const q = report.quality;
  const details = q.details ?? [];
  return (
    <div className="card rise flex flex-col p-5" style={{ animationDelay: '120ms' }}>
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Questions pièges</h2>
        <span className="text-sm font-bold tabular-nums" style={{ color: 'var(--color-mem)' }}>
          {q.passed}/{q.total}
        </span>
      </div>
      <p className="mt-1 text-xs text-[var(--color-muted)]">
        Réponses retrouvées par recherche sémantique uniquement.
      </p>

      <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-[var(--color-surface-2)]">
        <div
          className="h-full rounded-full"
          style={{
            width: `${q.score_pct}%`,
            background: 'var(--color-mem)',
            transition: 'width 500ms var(--ease-out)',
          }}
        />
      </div>

      <div className="mt-4 flex flex-col gap-1.5 overflow-y-auto pr-1" style={{ maxHeight: 280 }}>
        {details.length === 0 && (
          <p className="text-xs text-[var(--color-muted)]">
            Lance le benchmark pour évaluer les questions pièges.
          </p>
        )}
        {details.map((d, i) => (
          <div
            key={i}
            className="rise flex items-start gap-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)]/40 px-3 py-2"
            style={{ animationDelay: `${i * 35}ms` }}
          >
            <span
              className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full"
              style={{ background: d.passed ? 'var(--color-mem)' : 'var(--color-naive)' }}
            >
              {d.passed ? <Check size={11} color="#06120c" /> : <X size={11} color="#1a0606" />}
            </span>
            <div className="min-w-0">
              <p className="truncate text-xs text-[var(--color-text)]">{d.question}</p>
              <p className="text-[11px] text-[var(--color-muted)]">
                attendu : <span className="text-[var(--color-text)]">{d.expected}</span>
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
