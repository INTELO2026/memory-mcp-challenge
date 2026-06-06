import { Moon, Sun } from 'lucide-react';
import type { Theme } from '../hooks/useTheme';

export function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: () => void }) {
  const isDark = theme === 'dark';
  return (
    <button
      onClick={onToggle}
      aria-label={isDark ? 'Passer en mode clair' : 'Passer en mode sombre'}
      className="btn relative grid h-9 w-9 place-items-center overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]"
    >
      <Sun
        size={16}
        className="col-start-1 row-start-1 text-[var(--color-accent)]"
        style={{
          transition: 'transform 220ms var(--ease-out), opacity 180ms ease',
          transform: isDark ? 'scale(0.6) rotate(-40deg)' : 'scale(1) rotate(0)',
          opacity: isDark ? 0 : 1,
        }}
      />
      <Moon
        size={16}
        className="col-start-1 row-start-1 text-[var(--color-accent)]"
        style={{
          transition: 'transform 220ms var(--ease-out), opacity 180ms ease',
          transform: isDark ? 'scale(1) rotate(0)' : 'scale(0.6) rotate(40deg)',
          opacity: isDark ? 1 : 0,
        }}
      />
    </button>
  );
}
