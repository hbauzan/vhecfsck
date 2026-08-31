import { describe, it, expect, beforeEach } from 'vitest';
import { ReportHud, ReportPayload } from '../../src/hud/hud';

describe('ReportHud', () => {
  let container: HTMLElement;
  let hud: ReportHud;
  let layerToggles: string[] = [];
  let cameraResets = 0;

  beforeEach(() => {
    layerToggles = [];
    cameraResets = 0;

    container = document.createElement('div');
    container.innerHTML = `
      <span id="verdict-badge"></span>
      <div id="lod-banner"></div>
      <div id="variance-banner"></div>
      <div id="metrics-list"></div>
      <div id="legend-grid"></div>
    `;

    hud = new ReportHud(container, {
      onToggleLayer: (layer) => layerToggles.push(layer),
      onResetCamera: () => cameraResets++
    });
  });

  it('renders report verdict and metrics correctly', () => {
    const mockReport: ReportPayload = {
      verdict: 'FAIL',
      target: {
        uri: 'synthetic://scenarios/tombstoned',
        engine: 'synthetic',
        engine_version: '0.1.0'
      },
      metrics: {
        canary_recall: { value: 0.72, status: 'FAIL', unit: '%' },
        deletion_fragmentation_index: { value: null, status: 'UNAVAILABLE', reason: 'No tombstone support' }
      },
      projection: {
        explained_variance_ratio: [0.12, 0.05, 0.02],
        total_explained_variance: 0.19,
        n_components: 3,
        scale_factor: 1.5
      }
    };

    hud.renderReport(mockReport);

    const badge = container.querySelector('#verdict-badge');
    expect(badge?.textContent).toBe('FAIL');
    expect(badge?.className).toContain('verdict-fail');

    const varianceBanner = container.querySelector('#variance-banner');
    expect(varianceBanner?.textContent).toContain('19.0%');

    const metricsList = container.querySelectorAll('.metric-card');
    expect(metricsList.length).toBe(2);

    const firstCard = metricsList[0];
    expect(firstCard.textContent).toContain('Canary Recall');
    expect(firstCard.textContent).toContain('0.7200');

    const secondCard = metricsList[1];
    expect(secondCard.textContent).toContain('UNAVAILABLE');
    expect(secondCard.textContent).toContain('Reason: No tombstone support');
  });

  it('renders LOD banner correctly for complete dataset', () => {
    const mockScene = {
      n_points: 100,
      legend: { HEALTHY: '#808080' },
      palette: 'default',
      palettes: { default: { HEALTHY: '#808080' } },
      markers: { HEALTHY: 0 },
      size_scale: { HEALTHY: 1 },
      lod: {
        requested_budget: 200000,
        actual_count: 100,
        decimation_method: 'none',
        complete: true,
        has_tombstones: false
      },
      positions: new Float32Array(300),
      classes: new Uint8Array(100),
      ids: new BigInt64Array(100)
    };

    hud.updateLodBanner(mockScene);

    const banner = container.querySelector('#lod-banner');
    expect(banner?.textContent).toContain('Complete dataset rendered');
    expect(banner?.textContent).toContain('100');
  });
});
