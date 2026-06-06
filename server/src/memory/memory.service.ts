import { Injectable, Logger } from '@nestjs/common';
import { spawn } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

@Injectable()
export class MemoryService {
  private readonly logger = new Logger('MemoryService');
  private readonly repoRoot = path.resolve(__dirname, '..', '..', '..');
  private readonly reportPath = path.join(
    this.repoRoot,
    'benchmark',
    'results',
    'report.json',
  );

  // État du "replay" live (rejoue le rapport déjà calculé, sans appel Gemini).
  private replayActive = false;
  private replayStart = 0;
  private replayStepMs = 250;
  private replayTotal = 0;

  private pythonExe(): string {
    const isWin = process.platform === 'win32';
    return path.join(
      this.repoRoot,
      '.venv',
      isWin ? 'Scripts' : 'bin',
      isWin ? 'python.exe' : 'python',
    );
  }

  /** Lance un module Python et renvoie le dernier objet JSON imprimé sur stdout. */
  private runPython(args: string[], timeoutMs = 240_000): Promise<any> {
    return new Promise((resolve, reject) => {
      const proc = spawn(this.pythonExe(), args, { cwd: this.repoRoot });
      let stdout = '';
      let stderr = '';
      const timer = setTimeout(() => {
        proc.kill();
        reject(new Error('python timeout'));
      }, timeoutMs);

      proc.stdout.on('data', (d) => (stdout += d.toString()));
      proc.stderr.on('data', (d) => (stderr += d.toString()));
      proc.on('error', (err) => {
        clearTimeout(timer);
        reject(err);
      });
      proc.on('close', () => {
        clearTimeout(timer);
        const lines = stdout.trim().split('\n').filter(Boolean);
        const last = lines[lines.length - 1] ?? '';
        try {
          resolve(JSON.parse(last));
        } catch {
          // Renvoie une erreur lisible sans casser le serveur.
          const tail = stderr.trim().split('\n').slice(-2).join(' ');
          resolve({ ok: false, error: tail || 'sortie non-JSON', results: [] });
        }
      });
    });
  }

  readReport(): any | null {
    try {
      return JSON.parse(fs.readFileSync(this.reportPath, 'utf-8'));
    } catch {
      return null;
    }
  }

  private labelsOf(report: any): number[] {
    return report.labels ?? report.naive.cumulative.map((_: number, i: number) => i + 1);
  }

  /** Trame courante : rapport complet au repos, tranche progressive pendant le replay. */
  frame(): any {
    const base = this.readReport();
    if (!base || base.empty) return { empty: true };
    if (!this.replayActive) return base;

    const total = this.replayTotal;
    const elapsed = Date.now() - this.replayStart;
    const cursor = Math.min(total, Math.floor(elapsed / this.replayStepMs) + 1);

    // Animation terminée → on révèle le rapport complet (qualité incluse).
    if (cursor >= total) {
      this.replayActive = false;
      return base;
    }

    const labels = this.labelsOf(base);
    const nCum = base.naive.cumulative.slice(0, cursor);
    const mCum = base.memory.cumulative.slice(0, cursor);
    const nLast = nCum[cursor - 1] ?? 0;
    const mLast = mCum[cursor - 1] ?? 0;
    const price = base.cost?.price_eur_per_1m ?? 0;
    const savingsPct = nLast ? Math.round((1000 * (nLast - mLast)) / nLast) / 10 : 0;

    return {
      ...base,
      live: true,
      current_turn: labels[cursor - 1],
      turns: total,
      labels: labels.slice(0, cursor),
      naive: { ...base.naive, cumulative: nCum, total_tokens: nLast },
      memory: { ...base.memory, cumulative: mCum, total_tokens: mLast },
      savings_pct: savingsPct,
      savings_tokens: nLast - mLast,
      cost: {
        ...base.cost,
        naive_eur: (nLast / 1e6) * price,
        memory_eur: (mLast / 1e6) * price,
        savings_eur: ((nLast - mLast) / 1e6) * price,
      },
      quality: { passed: 0, total: base.quality?.total ?? 0, score_pct: 0 },
    };
  }

  async search(query: string, topK = 5): Promise<any> {
    return this.runPython(['-m', 'benchmark.bridge', 'search', query, String(topK)]);
  }

  /** Recalcule tout via Gemini (coûteux, soumis au quota). N'écrase rien si échec. */
  async runBenchmark(): Promise<any> {
    const res = await this.runPython(['-m', 'benchmark.harness']);
    return this.readReport() ?? res;
  }

  startLive(delaySec = 0.25): { started: boolean; turns?: number; error?: string } {
    const base = this.readReport();
    if (!base || base.empty) return { started: false, error: 'aucun rapport à rejouer' };
    this.replayTotal = this.labelsOf(base).length;
    this.replayStepMs = Math.max(120, Math.round(delaySec * 1000));
    this.replayStart = Date.now();
    this.replayActive = true;
    return { started: true, turns: this.replayTotal };
  }

  stopLive(): { stopped: boolean } {
    const was = this.replayActive;
    this.replayActive = false;
    return { stopped: was };
  }
}
