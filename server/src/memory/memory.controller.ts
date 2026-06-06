import { Body, Controller, Get, Post, Query, Sse } from '@nestjs/common';
import { interval, map, Observable } from 'rxjs';
import { MemoryService } from './memory.service';

interface MessageEvent {
  data: string;
}

@Controller()
export class MemoryController {
  constructor(private readonly memory: MemoryService) {}

  @Get('health')
  health() {
    return { ok: true, service: 'membridge-api' };
  }

  @Get('report')
  report() {
    return this.memory.readReport() ?? { empty: true };
  }

  /** Flux temps réel : trame complète au repos, tranche animée pendant le replay. */
  @Sse('stream')
  stream(): Observable<MessageEvent> {
    return interval(250).pipe(
      map(() => ({ data: JSON.stringify(this.memory.frame()) })),
    );
  }

  @Post('run')
  async run() {
    return this.memory.runBenchmark();
  }

  @Post('live')
  live(@Query('delay') delay?: string) {
    return this.memory.startLive(delay ? Number(delay) : 0.4);
  }

  @Post('live/stop')
  stopLive() {
    return this.memory.stopLive();
  }

  @Post('search')
  async search(@Body() body: { query: string; topK?: number }) {
    const q = (body?.query ?? '').trim();
    if (!q) return { ok: false, error: 'query vide', results: [] };
    return this.memory.search(q, body.topK ?? 5);
  }
}
