export interface ProgressEvent {
  stage: string;
  stage_index: number;
  stage_count: number;
  stage_fraction: number;
  fraction: number;
  elapsed_seconds: number;
  eta_seconds: number | null;
  metrics: Array<{ id: string; state: string; value: number | null; unit: string }>;
  detail: Record<string, unknown>;
  terminal: boolean;
}

export interface ProgressCallbacks {
  onEvent: (event: ProgressEvent) => void;
  onSceneReady?: () => void;
  onTerminal?: (event: ProgressEvent) => void;
}

function isProgressEvent(value: unknown): value is ProgressEvent {
  if (!value || typeof value !== 'object') return false;
  const v = value as ProgressEvent;
  return typeof v.stage === 'string' && typeof v.fraction === 'number';
}

export class ProgressClient {
  private socket: WebSocket | null = null;
  private pollTimer: number | null = null;
  private backoffMs = 500;
  private lastFraction = -1;
  private sceneReady = false;
  private closed = false;
  private readonly callbacks: ProgressCallbacks;

  constructor(callbacks: ProgressCallbacks) {
    this.callbacks = callbacks;
  }

  connect(): void {
    this.closed = false;
    this.openSocket();
  }

  disconnect(): void {
    this.closed = true;
    this.socket?.close();
    this.socket = null;
    if (this.pollTimer !== null) {
      window.clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  private openSocket(): void {
    if (this.closed) return;
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    try {
      this.socket = new WebSocket(`${proto}://${window.location.host}/api/progress`);
    } catch {
      this.fallbackToPolling();
      return;
    }
    this.socket.addEventListener('message', (ev) => {
      try {
        const data: unknown = JSON.parse(String(ev.data));
        if (isProgressEvent(data)) this.handle(data);
      } catch {
        // drop malformed frames rather than crashing the HUD
      }
    });
    this.socket.addEventListener('close', () => {
      if (!this.closed) this.reconnectOrPoll();
    });
    this.socket.addEventListener('error', () => {
      this.socket?.close();
    });
  }

  private reconnectOrPoll(): void {
    this.backoffMs = Math.min(this.backoffMs * 2, 8000);
    window.setTimeout(() => {
      if (this.closed) return;
      try {
        this.openSocket();
      } catch {
        this.fallbackToPolling();
      }
    }, this.backoffMs);
  }

  fallbackToPolling(): void {
    if (this.pollTimer !== null) return;
    this.pollTimer = window.setInterval(() => {
      void this.pollOnce();
    }, 1000);
    void this.pollOnce();
  }

  async pollOnce(): Promise<void> {
    try {
      const progressRes = await fetch('/api/progress');
      if (progressRes.ok) {
        const data: unknown = await progressRes.json();
        if (isProgressEvent(data)) this.handle(data);
      }
      if (this.sceneReady) return;
      const reportRes = await fetch('/api/report');
      if (reportRes.ok && !this.sceneReady) {
        // Report existing is enough to start painting while WS is down.
        this.callbacks.onSceneReady?.();
        this.sceneReady = true;
      }
    } catch {
      // keep polling
    }
  }

  private handle(event: ProgressEvent): void {
    if (event.fraction + 1e-9 < this.lastFraction) return;
    this.lastFraction = event.fraction;
    this.callbacks.onEvent(event);
    if (!this.sceneReady && (event.stage === 'projection' || event.fraction >= 0.3)) {
      this.sceneReady = true;
      this.callbacks.onSceneReady?.();
    }
    if (event.terminal) {
      this.callbacks.onTerminal?.(event);
      this.disconnect();
    }
  }
}
