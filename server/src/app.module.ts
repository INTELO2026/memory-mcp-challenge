import { Module } from '@nestjs/common';
import { MemoryController } from './memory/memory.controller';
import { MemoryService } from './memory/memory.service';

@Module({
  controllers: [MemoryController],
  providers: [MemoryService],
})
export class AppModule {}
