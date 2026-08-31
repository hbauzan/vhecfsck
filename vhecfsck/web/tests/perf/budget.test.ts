import { describe, it, expect } from 'vitest';
import { resolveClientBudget, DEFAULT_DISPLAY_BUDGET } from '../../src/scene/budget';
import { PointCloudRenderer } from '../../src/scene/renderer';

describe('display-budget perf harness', () => {
  it('default budget is accepted on a capable device', () => {
    const decision = resolveClientBudget(DEFAULT_DISPLAY_BUDGET, 1_000_000);
    expect(decision.accepted).toBe(true);
    expect(decision.granted).toBe(DEFAULT_DISPLAY_BUDGET);
  });

  it('ten reloads dispose geometry rather than leaking it', () => {
    const host = document.createElement('div');
    Object.defineProperty(host, 'clientWidth', { value: 32 });
    Object.defineProperty(host, 'clientHeight', { value: 32 });
    const renderer = new PointCloudRenderer(host);
    const payload = {
      n_points: 8,
      legend: { HEALTHY: '#808080' },
      palette: 'default',
      palettes: { default: { HEALTHY: '#808080' } },
      markers: { HEALTHY: 0 },
      size_scale: { HEALTHY: 1 },
      lod: {
        requested_budget: 8,
        actual_count: 8,
        decimation_method: 'none',
        complete: true,
        has_tombstones: false
      },
      positions: new Float32Array(24),
      classes: new Uint8Array(8),
      ids: new BigInt64Array(8)
    };
    for (let i = 0; i < 10; i++) renderer.renderScene(payload);
    expect(renderer.geometriesDisposed).toBeGreaterThanOrEqual(9);
    renderer.dispose();
  });
});
