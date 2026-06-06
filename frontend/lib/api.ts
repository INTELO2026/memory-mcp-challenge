export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://127.0.0.1:8000";

export const WS_BASE = API_BASE.replace(/^http/, "ws");

export type Health = {
  status: string;
  embedder: string;
  agent_backend: string;
  scenario_turns: number;
  trap_questions: number;
};

export type TrapQuestion = { id: string; question: string; expected: string };

export type Turn = { turn: number; role: string; content: string };

export type Scenario = {
  title: string;
  persona: string;
  session: string;
  turns: Turn[];
  trap_questions: TrapQuestion[];
};

export type Memory = {
  id: number;
  content: string;
  turn: number;
  score?: number;
  importance: number;
  access_count?: number;
  tags?: string[];
};

export type AskResponse = {
  question: string;
  answer: string;
  agent_backend: string;
  memories: Memory[];
  tokens: { memory: number; naive: number; saved_pct: number };
};

export type Report = {
  scenario: { title: string; persona: string; turns: number; session: string };
  embedder: string;
  modes: {
    naive: { total_tokens: number; per_turn: number[]; cumulative: number[] };
    memory: {
      total_tokens: number;
      per_turn: number[];
      cumulative: number[];
      compression_ratio: number;
    };
  };
  savings: {
    tokens: number;
    pct: number;
    euros: number;
    price_per_mtok: number;
    euros_per_1k_conversations: number;
    euros_per_100k_conversations: number;
  };
  quality: {
    passed: number;
    total: number;
    score_pct: number;
    naive_passed: number;
    details: { id: string; question: string; expected: string; hit: boolean; top_score: number; retrieved: string }[];
  };
  generated_at: string;
};

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return res.json();
}

export const api = {
  health: () => getJSON<Health>("/api/health"),
  scenario: () => getJSON<Scenario>("/api/scenario"),
  report: () => getJSON<Report>("/api/report"),
  memory: () => getJSON<{ count: number; entries: Memory[] }>("/api/memory"),
  rank: () => getJSON<{ results: Memory[]; count: number }>("/api/memory/rank"),
  ask: async (question: string): Promise<AskResponse> => {
    const res = await fetch(`${API_BASE}/api/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!res.ok) throw new Error(`ask → ${res.status}`);
    return res.json();
  },
};

export type BenchEvent =
  | { type: "start"; total: number; embedder: string }
  | {
      type: "turn";
      turn: number;
      role: string;
      content: string;
      naive_turn: number;
      memory_turn: number;
      naive_cumulative: number;
      memory_cumulative: number;
    }
  | {
      type: "done";
      naive_total: number;
      memory_total: number;
      saved_tokens: number;
      savings_pct: number;
    };

export function streamBenchmark(
  onEvent: (e: BenchEvent) => void,
  opts: { delayMs?: number; onClose?: () => void } = {},
): () => void {
  const ws = new WebSocket(`${WS_BASE}/ws/benchmark`);
  ws.onopen = () => ws.send(JSON.stringify({ delay_ms: opts.delayMs ?? 170 }));
  ws.onmessage = (ev) => onEvent(JSON.parse(ev.data));
  ws.onclose = () => opts.onClose?.();
  return () => ws.close();
}
