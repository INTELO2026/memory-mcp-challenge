import type { ReactNode } from 'react';
import { useCountUp } from '../hooks/useCountUp';
import { fmt } from '../lib/format';

interface Props {
  label: string;
  value: number;
  suffix?: string;
  accent?: 'naive' | 'mem' | 'accent' | 'text';
  icon?: ReactNode;
  hint?: string;
  delay?: number;
}

const accentColor: Record<string, string> = {
  naive: 'var(--color-naive)',
  mem: 'var(--color-mem)',
  accent: 'var(--color-accent)',
  text: 'var(--color-text)',
};

export function StatCard({ label, value, suffix, accent = 'text', icon, hint, delay = 0 }: Props) {
  const animated = useCountUp(value);
  return (
    <div className="card rise p-5 flex flex-col gap-3" style={{ animationDelay: `${delay}ms` }}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-[0.12em] text-[var(--color-muted)]">
          {label}
        </span>
        <span style={{ color: accentColor[accent] }} className="opacity-80">
          {icon}
        </span>
      </div>
      <div className="flex items-baseline gap-1.5">
        <span
          className="text-[2rem] font-extrabold leading-none tabular-nums"
          style={{ color: accentColor[accent] }}
        >
          {fmt(animated)}
        </span>
        {suffix && <span className="text-sm text-[var(--color-muted)]">{suffix}</span>}
      </div>
      {hint && <span className="text-xs text-[var(--color-muted)]">{hint}</span>}
    </div>
  );
}
