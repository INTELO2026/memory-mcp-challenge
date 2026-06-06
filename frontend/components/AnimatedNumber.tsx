"use client";

import { useEffect, useRef, useState } from "react";

export function AnimatedNumber({
  value,
  duration = 500,
  className = "",
}: {
  value: number;
  duration?: number;
  className?: string;
}) {
  const [display, setDisplay] = useState(value);
  const from = useRef(value);
  const raf = useRef<number>();

  useEffect(() => {
    const start = performance.now();
    const initial = from.current;
    const delta = value - initial;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplay(Math.round(initial + delta * eased));
      if (t < 1) raf.current = requestAnimationFrame(tick);
      else from.current = value;
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
      from.current = value;
    };
  }, [value, duration]);

  return <span className={`tabular ${className}`}>{display.toLocaleString("fr-FR")}</span>;
}
