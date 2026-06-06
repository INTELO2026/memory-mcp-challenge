import { memo } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { Report } from '../lib/api';
import { fmt } from '../lib/format';
import type { Theme } from '../hooks/useTheme';

const PALETTE = {
  dark: {
    naive: '#ff5d5d',
    mem: '#34e3a0',
    grid: '#1f2430',
    axis: '#8b93a4',
    tipBg: '#0e1016',
    tipBorder: '#1f2430',
    tipText: '#eef1f6',
  },
  light: {
    naive: '#e5484d',
    mem: '#109a66',
    grid: '#e4e8ef',
    axis: '#5d6675',
    tipBg: '#ffffff',
    tipBorder: '#e4e8ef',
    tipText: '#0d1320',
  },
} as const;

function TokenChartImpl({ report, theme }: { report: Report; theme: Theme }) {
  const c = PALETTE[theme] ?? PALETTE.dark;
  const labels = report.labels ?? report.naive.cumulative.map((_, i) => i + 1);
  const data = labels.map((t, i) => ({
    turn: t,
    naive: report.naive.cumulative[i] ?? null,
    mem: report.memory.cumulative[i] ?? null,
  }));

  return (
    <div className="card rise p-5" style={{ animationDelay: '60ms' }}>
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">Tokens cumulés par tour</h2>
          <p className="text-xs text-[var(--color-muted)]">
            La courbe naïve explose, MemBridge reste plate.
          </p>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className="flex items-center gap-1.5 text-[var(--color-muted)]">
            <i className="h-2.5 w-2.5 rounded-full" style={{ background: 'var(--color-naive)' }} />
            Naïf
          </span>
          <span className="flex items-center gap-1.5 text-[var(--color-muted)]">
            <i className="h-2.5 w-2.5 rounded-full" style={{ background: 'var(--color-mem)' }} />
            MemBridge
          </span>
        </div>
      </div>

      <div style={{ width: '100%', height: 320 }}>
        <ResponsiveContainer>
          <AreaChart data={data} margin={{ top: 10, right: 12, bottom: 0, left: 4 }}>
            <defs>
              <linearGradient id="gNaive" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={c.naive} stopOpacity={0.32} />
                <stop offset="100%" stopColor={c.naive} stopOpacity={0} />
              </linearGradient>
              <linearGradient id="gMem" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={c.mem} stopOpacity={0.32} />
                <stop offset="100%" stopColor={c.mem} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={c.grid} vertical={false} />
            <XAxis
              dataKey="turn"
              tick={{ fill: c.axis, fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: c.grid }}
            />
            <YAxis
              tick={{ fill: c.axis, fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              width={54}
              tickFormatter={(v) => fmt(v as number)}
            />
            <Tooltip
              contentStyle={{
                background: c.tipBg,
                border: `1px solid ${c.tipBorder}`,
                borderRadius: 12,
                color: c.tipText,
              }}
              labelStyle={{ color: c.axis }}
              formatter={(v: number, name) => [fmt(v), name === 'naive' ? 'Naïf' : 'MemBridge']}
              labelFormatter={(l) => `Tour ${l}`}
            />
            <Area
              type="monotone"
              dataKey="naive"
              stroke={c.naive}
              strokeWidth={2.5}
              fill="url(#gNaive)"
              isAnimationActive={false}
              dot={false}
            />
            <Area
              type="monotone"
              dataKey="mem"
              stroke={c.mem}
              strokeWidth={2.5}
              fill="url(#gMem)"
              isAnimationActive={false}
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

const sig = (r: Report) => {
  const n = r.naive.cumulative;
  const m = r.memory.cumulative;
  return `${n.length}:${n[n.length - 1]}:${m[m.length - 1]}:${r.savings_pct}`;
};

export const TokenChart = memo(
  TokenChartImpl,
  (a, b) => sig(a.report) === sig(b.report) && a.theme === b.theme,
);
