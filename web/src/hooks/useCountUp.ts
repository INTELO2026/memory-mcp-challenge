import { useEffect, useRef, useState } from 'react';

const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);

/** Anime une valeur numérique vers `value` (ease-out, court). */
export function useCountUp(value: number, duration = 650): number {
  const [display, setDisplay] = useState(value);
  const fromRef = useRef(value);
  const startRef = useRef<number | null>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    fromRef.current = display;
    startRef.current = null;
    const from = fromRef.current;
    const delta = value - from;

    const tick = (now: number) => {
      if (startRef.current === null) startRef.current = now;
      const elapsed = now - startRef.current;
      const t = Math.min(1, elapsed / duration);
      setDisplay(from + delta * easeOut(t));
      if (t < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, duration]);

  return display;
}
