import { Injectable, signal, computed } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class SessionService {
  readonly sessionId = signal<string | null>(null);
  readonly fps = signal<number>(30);
  readonly totalFrames = signal<number>(0);
  readonly videoWidth = signal<number>(0);
  readonly videoHeight = signal<number>(0);
  readonly currentFrameIdx = signal<number>(0);
  readonly frameStep = signal<number>(1);
  readonly pointType = signal<'positive' | 'negative'>('positive');
  readonly targets = signal<string[]>([]);
  readonly currentTargetId = signal<number>(1);
  readonly annotationFrameIdx = signal<number | null>(null);
  readonly rangeStart = signal<number>(0);
  readonly rangeEnd = signal<number>(0);

  readonly hasSession = computed(() => this.sessionId() !== null);
  readonly effectiveFrames = computed(() => {
    const rangeFrames = this.rangeEnd() - this.rangeStart();
    return Math.max(1, Math.ceil(rangeFrames / this.frameStep()));
  });

  reset() {
    this.sessionId.set(null);
    this.fps.set(30);
    this.totalFrames.set(0);
    this.videoWidth.set(0);
    this.videoHeight.set(0);
    this.currentFrameIdx.set(0);
    this.frameStep.set(1);
    this.pointType.set('positive');
    this.targets.set([]);
    this.currentTargetId.set(1);
    this.annotationFrameIdx.set(null);
    this.rangeStart.set(0);
    this.rangeEnd.set(0);
  }
}
