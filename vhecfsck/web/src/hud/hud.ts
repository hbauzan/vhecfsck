import { DecodedScenePayload } from '../codec/scene_decoder';

export interface MetricDetail {
  value: number | string | null;
  status: 'OK' | 'WARN' | 'FAIL' | 'UNAVAILABLE' | 'DISABLED';
  unit?: string;
  reason?: string;
  threshold?: {
    warn?: number;
    fail?: number;
  };
}

export interface ReportPayload {
  verdict: 'OK' | 'WARN' | 'FAIL' | 'INCONCLUSIVE';
  target: {
    uri: string;
    engine: string;
    engine_version: string;
  };
  metrics: Record<string, MetricDetail>;
  projection?: {
    explained_variance_ratio: number[];
    total_explained_variance: number;
    n_components: number;
    scale_factor: number;
  };
}

export interface HudCallbacks {
  onToggleLayer: (layer: 'healthy' | 'hubs' | 'antihubs' | 'tombstones' | 'queries') => void;
  onResetCamera: () => void;
}

export class ReportHud {
  private container: HTMLElement;
  private callbacks: HudCallbacks;

  constructor(container: HTMLElement, callbacks: HudCallbacks) {
    this.container = container;
    this.callbacks = callbacks;
    this.bindKeyboardShortcuts();
  }

  public renderReport(report: ReportPayload): void {
    this.updateVerdict(report.verdict);
    this.updateVarianceCaveat(report.projection);
    this.updateMetrics(report.metrics);
  }

  public updateLodBanner(scene: DecodedScenePayload): void {
    const banner = this.container.querySelector('#lod-banner');
    if (!banner) return;

    const lod = scene.lod;
    const actual = lod.actual_count.toLocaleString();
    const requested = lod.requested_budget.toLocaleString();
    const method = lod.decimation_method;

    if (lod.complete) {
      banner.innerHTML = `<strong>LOD:</strong> Complete dataset rendered (<strong>${actual}</strong> points).`;
    } else {
      banner.innerHTML = `<strong>LOD:</strong> Showing <strong>${actual}</strong> of <strong>${requested}</strong> points (<strong>${method}</strong>).`;
    }

    this.updateLegend(scene.legend);
  }

  private updateVerdict(verdict: 'OK' | 'WARN' | 'FAIL' | 'INCONCLUSIVE'): void {
    const badge = this.container.querySelector('#verdict-badge');
    if (!badge) return;

    badge.className = `verdict-badge verdict-${verdict.toLowerCase()}`;
    badge.textContent = verdict;
  }

  private updateVarianceCaveat(proj?: ReportPayload['projection']): void {
    const banner = this.container.querySelector('#variance-banner');
    if (!banner) return;

    if (!proj) {
      banner.innerHTML = '<strong>3D Projection:</strong> PCA 3D projection is a lossy sketch of high-dimensional space.';
      return;
    }

    const totalPct = (proj.total_explained_variance * 100).toFixed(1);
    banner.innerHTML = `<strong>3D Projection Caveat:</strong> Retains <strong>${totalPct}%</strong> of variance in 3D (lossy sketch of high-dim space).`;
  }

  private updateMetrics(metrics: Record<string, MetricDetail>): void {
    const listEl = this.container.querySelector('#metrics-list');
    if (!listEl) return;

    listEl.innerHTML = '';

    for (const [name, detail] of Object.entries(metrics)) {
      const card = document.createElement('div');
      card.className = 'metric-card';

      const top = document.createElement('div');
      top.className = 'metric-top';

      const nameEl = document.createElement('span');
      nameEl.className = 'metric-name';
      nameEl.textContent = this.formatMetricName(name);

      const statusEl = document.createElement('span');
      const statusClass = (detail.status || 'UNAVAILABLE').toLowerCase();
      statusEl.className = `metric-status verdict-${statusClass}`;
      statusEl.textContent = detail.status;

      top.appendChild(nameEl);
      top.appendChild(statusEl);

      const valEl = document.createElement('div');
      valEl.className = 'metric-value';

      if (detail.status === 'UNAVAILABLE') {
        valEl.textContent = 'UNAVAILABLE';
        valEl.style.color = 'var(--text-dim)';
      } else {
        const numVal = typeof detail.value === 'number' ? detail.value.toFixed(4) : String(detail.value);
        valEl.textContent = `${numVal} ${detail.unit || ''}`;
      }

      card.appendChild(top);
      card.appendChild(valEl);

      if (detail.reason) {
        const metaEl = document.createElement('div');
        metaEl.className = 'metric-meta';
        metaEl.textContent = `Reason: ${detail.reason}`;
        card.appendChild(metaEl);
      }

      listEl.appendChild(card);
    }
  }

  private updateLegend(legend: Record<string, string>): void {
    const grid = this.container.querySelector('#legend-grid');
    if (!grid) return;

    grid.innerHTML = '';

    const labelMap: Record<string, { label: string; key: 'healthy' | 'hubs' | 'antihubs' | 'tombstones' | 'queries' }> = {
      HEALTHY: { label: 'Healthy Points', key: 'healthy' },
      HUB: { label: 'Hub Anomalies', key: 'hubs' },
      ANTIHUB: { label: 'Anti-Hub Points', key: 'antihubs' },
      TOMBSTONE: { label: 'Tombstones', key: 'tombstones' },
      QUERY: { label: 'Query Probes', key: 'queries' }
    };

    for (const [clsKey, color] of Object.entries(legend)) {
      const meta = labelMap[clsKey];
      if (!meta) continue;

      const item = document.createElement('div');
      item.className = 'legend-item';
      item.dataset.layerKey = meta.key;

      const swatch = document.createElement('div');
      swatch.className = 'legend-swatch';
      swatch.style.backgroundColor = color;

      const text = document.createElement('span');
      text.textContent = meta.label;

      item.appendChild(swatch);
      item.appendChild(text);

      item.addEventListener('click', () => {
        item.classList.toggle('dimmed');
        this.callbacks.onToggleLayer(meta.key);
      });

      grid.appendChild(item);
    }
  }

  private formatMetricName(key: string): string {
    return key
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  private bindKeyboardShortcuts(): void {
    window.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      const key = e.key.toUpperCase();
      if (key === 'H') this.triggerLayerToggle('hubs');
      else if (key === 'A') this.triggerLayerToggle('antihubs');
      else if (key === 'T') this.triggerLayerToggle('tombstones');
      else if (key === 'G') this.triggerLayerToggle('healthy');
      else if (key === 'R') this.callbacks.onResetCamera();
    });
  }

  private triggerLayerToggle(key: 'healthy' | 'hubs' | 'antihubs' | 'tombstones' | 'queries'): void {
    const item = this.container.querySelector(`.legend-item[data-layer-key="${key}"]`);
    if (item) item.classList.toggle('dimmed');
    this.callbacks.onToggleLayer(key);
  }
}
