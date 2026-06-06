export interface TrapDetail {
  question: string;
  expected: string;
  passed: boolean;
  top_turn: number | null;
}

export interface Report {
  scenario?: string;
  turns?: number;
  live?: boolean;
  current_turn?: number;
  labels?: number[];
  naive: { total_tokens: number; cumulative: number[] };
  memory: {
    total_tokens: number;
    cumulative: number[];
    compression_ratio?: number;
    growth_factor?: number;
    stats?: Record<string, unknown>;
  };
  savings_pct: number;
  savings_tokens: number;
  cost: {
    naive_eur: number;
    memory_eur: number;
    savings_eur: number;
    price_eur_per_1m: number;
  };
  quality: { passed: number; total: number; score_pct: number; details?: TrapDetail[] };
  embedding_backend?: string;
  empty?: boolean;
}

export interface SearchResult {
  id: number;
  content: string;
  tags: string[];
  turn: number;
  importance: number;
  score: number;
}

export async function getReport(): Promise<Report> {
  const r = await fetch('/api/report');
  return r.json();
}

export async function runBenchmark(): Promise<Report> {
  const r = await fetch('/api/run', { method: 'POST' });
  return r.json();
}

export async function startLive(delay = 0.4) {
  const r = await fetch(`/api/live?delay=${delay}`, { method: 'POST' });
  return r.json();
}

export async function stopLive() {
  const r = await fetch('/api/live/stop', { method: 'POST' });
  return r.json();
}

export async function searchMemory(query: string, topK = 5) {
  const r = await fetch('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, topK }),
  });
  return r.json() as Promise<{ ok: boolean; results: SearchResult[]; backend?: string }>;
}

/** Abonnement SSE au flux temps réel du rapport. */
export function subscribeStream(onData: (r: Report) => void): () => void {
  const es = new EventSource('/api/stream');
  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (!data.empty) onData(data);
    } catch {
      /* ignore */
    }
  };
  return () => es.close();
}
