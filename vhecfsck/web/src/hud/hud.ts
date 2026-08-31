import { DecodedScenePayload } from '../codec/scene_decoder';
import { ProbeResult } from '../interaction/probe';
import { ProgressEvent } from './progress';
import { ColourByMode } from '../views/colour';
import { ChartsPayload, drawHistogram } from '../views/charts';
import { tombstoneBadgeText, tombstoneLayerFromScene } from '../scene/tombstones';

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
    uri?: string;
    engine: string;
    engine_version: string;
    location?: string;
  };
  metrics: Record<string, MetricDetail> | MetricDetail[] | Array<MetricDetail & { id: string }>;
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
  onColourBy?: (mode: ColourByMode) => void;
  onPalette?: (name: string) => void;
  onPreset?: (name: string) => void;
  onTour?: () => void;
  onTourSkip?: () => void;
}

function asMetricEntries(
  metrics: ReportPayload['metrics']
): Array<[string, MetricDetail]> {
  if (Array.isArray(metrics)) {
    return metrics.map((m, i) => {
      const rec = m as MetricDetail & { id?: string };
      return [rec.id ?? `metric_${i}`, rec];
    });
  }
  return Object.entries(metrics);
}

export class ReportHud {
  private container: HTMLElement;
  private callbacks: HudCallbacks;

  constructor(container: HTMLElement, callbacks: HudCallbacks) {
    this.container = container;
    this.callbacks = callbacks;
    this.bindKeyboardShortcuts();
    this.bindControls();
  }

  public renderReport(report: ReportPayload): void {
    this.updateVerdict(report.verdict);
    this.updateVarianceCaveat(report.projection);
    this.updateMetrics(report.metrics);
  }

  public updateLodBanner(scene: DecodedScenePayload, budgetReason?: string | null): void {
    const banner = this.container.querySelector('#lod-banner');
    if (!banner) return;

    const lod = scene.lod;
    const actual = lod.actual_count.toLocaleString();
    const requested = lod.requested_budget.toLocaleString();
    const method = lod.decimation_method;
    const chunk = lod.chunk_index ?? 0;
    const chunks = lod.chunk_count ?? 1;

    if (lod.complete) {
      banner.innerHTML = `<strong>LOD:</strong> Complete dataset rendered (<strong>${actual}</strong> points).`;
    } else {
      banner.innerHTML = `<strong>LOD:</strong> Showing <strong>${actual}</strong> of <strong>${requested}</strong> points (<strong>${method}</strong>), chunk ${chunk + 1}/${chunks}.`;
    }
    if (budgetReason) {
      banner.innerHTML += ` <em>${budgetReason}</em>`;
    }

    this.updateLegend(scene);
    this.updateTombstoneBadge(scene);
  }

  public updateProgress(event: ProgressEvent): void {
    const bar = this.container.querySelector('#progress-bar');
    const label = this.container.querySelector('#progress-label');
    if (bar instanceof HTMLElement) {
      const pct = Math.round(event.fraction * 100);
      bar.setAttribute('aria-valuenow', String(pct));
      bar.style.setProperty('--progress', `${pct}%`);
      const fill = bar.querySelector('.progress-fill');
      if (fill instanceof HTMLElement) fill.style.width = `${pct}%`;
    }
    if (label) {
      const eta =
        event.eta_seconds === null ? '' : ` · eta ${event.eta_seconds.toFixed(0)}s`;
      label.textContent = `${event.stage} ${(event.fraction * 100).toFixed(0)}%${eta}`;
    }
    if (event.metrics.length) {
      const incremental: Record<string, MetricDetail> = {};
      for (const m of event.metrics) {
        incremental[m.id] = {
          value: m.value,
          status: (m.state as MetricDetail['status']) || 'UNAVAILABLE',
          unit: m.unit
        };
      }
      this.updateMetrics(incremental);
    }
  }

  public renderProbe(result: ProbeResult): void {
    const panel = this.container.querySelector('#probe-panel');
    if (!panel) return;
    panel.removeAttribute('hidden');
    if (!result.available) {
      panel.innerHTML = `<h3>Probe</h3><p>${result.unavailable_reason ?? 'unavailable'}</p>`;
      return;
    }
    const dead = new Set(result.dead_returns);
    const missed = result.missed.map((id) => `<span class="missed">${id}</span>`).join(', ');
    const returned = result.engine_returned
      .map((id) =>
        dead.has(id) ? `<s class="dead-id">${id}</s>` : `<span class="returned">${id}</span>`
      )
      .join(', ');
    const cannibal = result.cannibalisation
      ? `<p>Cannibalising ${result.cannibalisation.n_k} queries${result.cannibalisation.truncated ? ' (truncated)' : ''}.</p>`
      : '';
    panel.innerHTML = `
      <h3 id="probe-heading">Probe ${result.query_id}</h3>
      <p>recall@k ${result.recall_id.toFixed(3)} · N_k ${result.n_k ?? 'UNAVAILABLE'}</p>
      <p><strong>True neighbours:</strong> ${result.true_neighbours.join(', ')}</p>
      <p><strong>Engine returned:</strong> ${returned}</p>
      <p><strong>Missed:</strong> ${missed || 'none'}</p>
      ${cannibal}
    `;
  }

  public renderCharts(charts: ChartsPayload): void {
    const nk = this.container.querySelector('#nk-chart');
    const part = this.container.querySelector('#partition-chart');
    const reason = this.container.querySelector('#partition-unavailable');
    if (nk instanceof HTMLCanvasElement) {
      drawHistogram(nk, charts.nk_histogram, { logY: charts.nk_log_y, fill: '#56B4E9' });
    }
    if (part instanceof HTMLCanvasElement) {
      if (charts.partition_histogram) {
        drawHistogram(part, charts.partition_histogram, {
          mean: charts.partition_mean,
          fill: '#E69F00'
        });
        part.hidden = false;
        if (reason) reason.textContent = '';
      } else {
        part.hidden = true;
        if (reason) reason.textContent = charts.partition_unavailable_reason ?? '';
      }
    }
  }

  public setTourHandler(handler: () => void): void {
    this.callbacks.onTour = handler;
  }

  public setPaletteName(name: string): void {
    const legend = this.container.querySelector('#legend-palette');
    if (legend) legend.textContent = `Palette: ${name}`;
  }

  public setColourBy(mode: ColourByMode, unavailable?: string | null): void {
    const note = this.container.querySelector('#colourby-reason');
    if (note) note.textContent = unavailable ?? '';
    const select = this.container.querySelector('#colourby-select');
    if (select instanceof HTMLSelectElement) select.value = mode;
  }

  private updateTombstoneBadge(scene: DecodedScenePayload): void {
    const badge = this.container.querySelector('#tombstone-badge');
    if (!badge) return;
    const layer = tombstoneLayerFromScene(scene);
    badge.textContent = tombstoneBadgeText(layer);
    badge.setAttribute('title', layer.reason ?? '');
  }

  private updateVerdict(verdict: ReportPayload['verdict']): void {
    const badge = this.container.querySelector('#verdict-badge');
    if (!badge) return;
    badge.className = `verdict-badge verdict-${verdict.toLowerCase()}`;
    badge.textContent = verdict;
  }

  private updateVarianceCaveat(proj?: ReportPayload['projection']): void {
    const banner = this.container.querySelector('#variance-banner');
    if (!banner) return;
    if (!proj) {
      banner.innerHTML =
        '<strong>3D Projection:</strong> PCA 3D projection is a lossy sketch of high-dimensional space.';
      return;
    }
    const totalPct = (proj.total_explained_variance * 100).toFixed(1);
    banner.innerHTML = `<strong>3D Projection Caveat:</strong> Retains <strong>${totalPct}%</strong> of variance in 3D (lossy sketch of high-dim space).`;
  }

  private updateMetrics(metrics: ReportPayload['metrics']): void {
    const listEl = this.container.querySelector('#metrics-list');
    if (!listEl) return;
    listEl.innerHTML = '';
    for (const [name, detail] of asMetricEntries(metrics)) {
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
        const numVal =
          typeof detail.value === 'number' ? detail.value.toFixed(4) : String(detail.value);
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

  private updateLegend(scene: DecodedScenePayload): void {
    const grid = this.container.querySelector('#legend-grid');
    if (!grid) return;
    grid.innerHTML = '';
    this.setPaletteName(scene.palette);

    const labelMap: Record<
      string,
      { label: string; key: 'healthy' | 'hubs' | 'antihubs' | 'tombstones' | 'queries' }
    > = {
      HEALTHY: { label: 'Healthy Points', key: 'healthy' },
      HUB: { label: 'Hub Anomalies', key: 'hubs' },
      ANTIHUB: { label: 'Anti-Hub Points', key: 'antihubs' },
      TOMBSTONE: { label: 'Tombstones', key: 'tombstones' },
      QUERY: { label: 'Query Probes', key: 'queries' }
    };

    const palettes = scene.palettes ?? {};
    const active = palettes[scene.palette] ?? scene.legend;
    for (const [clsKey, color] of Object.entries(active)) {
      const meta = labelMap[clsKey];
      if (!meta) continue;
      const item = document.createElement('div');
      item.className = 'legend-item';
      item.dataset.layerKey = meta.key;
      item.tabIndex = 0;
      item.setAttribute('role', 'button');
      item.setAttribute('aria-label', `Toggle ${meta.label}`);
      const swatch = document.createElement('div');
      swatch.className = `legend-swatch marker-${(scene.markers ?? {})[clsKey] ?? 0}`;
      swatch.style.backgroundColor = color;
      const text = document.createElement('span');
      text.textContent = meta.label;
      item.appendChild(swatch);
      item.appendChild(text);
      const toggle = () => {
        item.classList.toggle('dimmed');
        this.callbacks.onToggleLayer(meta.key);
      };
      item.addEventListener('click', toggle);
      item.addEventListener('keydown', (e: KeyboardEvent) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          toggle();
        }
      });
      grid.appendChild(item);
    }
  }

  private formatMetricName(key: string): string {
    return key.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
  }

  private bindControls(): void {
    const colour = this.container.querySelector('#colourby-select');
    colour?.addEventListener('change', (e) => {
      const value = (e.target as HTMLSelectElement).value as ColourByMode;
      this.callbacks.onColourBy?.(value);
    });
    const palette = this.container.querySelector('#palette-select');
    palette?.addEventListener('change', (e) => {
      const value = (e.target as HTMLSelectElement).value;
      this.setPaletteName(value);
      this.callbacks.onPalette?.(value);
    });
    this.container.querySelectorAll('[data-preset]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const name = (btn as HTMLElement).dataset.preset;
        if (name) this.callbacks.onPreset?.(name);
      });
    });
    this.container.querySelector('#tour-btn')?.addEventListener('click', () => {
      this.callbacks.onTour?.();
    });
    this.container.querySelector('#tour-skip-btn')?.addEventListener('click', () => {
      this.callbacks.onTourSkip?.();
    });
  }

  private bindKeyboardShortcuts(): void {
    window.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.target instanceof HTMLSelectElement) return;
      const key = e.key.toUpperCase();
      if (key === 'H') this.triggerLayerToggle('hubs');
      else if (key === 'A') this.triggerLayerToggle('antihubs');
      else if (key === 'T') this.triggerLayerToggle('tombstones');
      else if (key === 'G') this.triggerLayerToggle('healthy');
      else if (key === 'R') this.callbacks.onResetCamera();
      else if (key === 'Escape') this.callbacks.onTourSkip?.();
    });
  }

  private triggerLayerToggle(
    key: 'healthy' | 'hubs' | 'antihubs' | 'tombstones' | 'queries'
  ): void {
    const item = this.container.querySelector(`.legend-item[data-layer-key="${key}"]`);
    if (item) item.classList.toggle('dimmed');
    this.callbacks.onToggleLayer(key);
  }
}
