import { useCountUp } from '../hooks/useCountUp';
import { fmt, fmtEur } from '../lib/format';

interface Props {
  savingsPct: number;
  savingsTokens: number;
  savingsEur: number;
  turns: number;
}

export function SavingsHero({ savingsPct, savingsTokens, savingsEur, turns }: Props) {
  const pct = useCountUp(savingsPct, 900);
  return (
    <div className="card rise relative overflow-hidden p-7">
      <div
        className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full blur-3xl"
        style={{ background: 'radial-gradient(circle, rgba(52,227,160,0.22), transparent 70%)' }}
      />
      <span className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-muted)]">
        Économie de tokens · {turns} tours
      </span>
      <div className="mt-3 flex items-end gap-3">
        <span
          className="text-[5rem] font-black leading-[0.9] tabular-nums"
          style={{ color: 'var(--color-mem)' }}
        >
          {pct.toFixed(1)}
        </span>
        <span className="mb-3 text-2xl font-bold text-[var(--color-mem)]">%</span>
      </div>
      <p className="mt-2 text-sm text-[var(--color-muted)]">
        <span className="font-semibold text-[var(--color-text)]">{fmt(savingsTokens)}</span> tokens
        économisés · <span className="font-semibold text-[var(--color-text)]">{fmtEur(savingsEur)} €</span>
      </p>
    </div>
  );
}
