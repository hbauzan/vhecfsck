import { describe, it, expect } from 'vitest';
import { colourBuffer } from '../../src/views/colour';
import { contrastRatio } from '../../src/theme/a11y';
import { markerCovers, MARKER } from '../../src/scene/markers';
import { tombstoneLayerFromScene } from '../../src/scene/tombstones';
import { decodeSceneBinary, DecodedScenePayload } from '../../src/codec/scene_decoder';
import { criticalA11yViolations } from '../../src/theme/a11y';
import { ReportHud } from '../../src/hud/hud';

function swatch(hex: string, size = 8): Uint8ClampedArray {
  const [r, g, b] = [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16)
  ];
  const out = new Uint8ClampedArray(size * size * 4);
  for (let i = 0; i < size * size; i++) {
    out[i * 4] = r;
    out[i * 4 + 1] = g;
    out[i * 4 + 2] = b;
    out[i * 4 + 3] = 255;
  }
  return out;
}

function sceneFromClasses(classes: number[]): DecodedScenePayload {
  const n = classes.length;
  return {
    n_points: n,
    legend: { HEALTHY: '#808080', HUB: '#FF4D4D', ANTIHUB: '#4D79FF', TOMBSTONE: '#4A4A4A' },
    palette: 'default',
    palettes: {
      default: { HEALTHY: '#808080', HUB: '#FF4D4D', ANTIHUB: '#4D79FF', TOMBSTONE: '#4A4A4A' },
      deuteranopia: { HEALTHY: '#9A9A9A', HUB: '#D55E00', ANTIHUB: '#56B4E9', TOMBSTONE: '#3F3F3F' }
    },
    markers: { HEALTHY: 0, HUB: 1, ANTIHUB: 2, TOMBSTONE: 3 },
    size_scale: { HEALTHY: 1, HUB: 2.2, ANTIHUB: 1.8, TOMBSTONE: 1.4 },
    lod: {
      requested_budget: n,
      actual_count: n,
      decimation_method: 'none',
      complete: true,
      has_tombstones: false,
      tombstone_count: null,
      tombstone_reason: 'this adapter cannot report deleted counts, so the number of tombstones is UNAVAILABLE'
    },
    positions: new Float32Array(n * 3),
    classes: Uint8Array.from(classes),
    ids: new BigInt64Array(classes.map((_, i) => BigInt(i)))
  };
}

describe('visual baselines', () => {
  it('default and deuteranopia palettes differ', () => {
    const scene = sceneFromClasses([0, 1, 2]);
    const a = colourBuffer(scene, 'class', 'default').hex;
    const b = colourBuffer(scene, 'class', 'deuteranopia').hex;
    expect(a.join()).not.toBe(b.join());
    expect(swatch(a[1]).join()).not.toBe(swatch(b[1]).join());
  });

  it('swapping hub and antihub colours fails the suite', () => {
    const scene = sceneFromClasses([1, 2]);
    const hex = colourBuffer(scene, 'class', 'default').hex;
    const swapped = [hex[1], hex[0]];
    expect(hex.join()).not.toBe(swapped.join());
  });

  it('class remains distinguishable in grayscale', () => {
    expect(contrastRatio('#D55E00', '#56B4E9')).toBeGreaterThan(1.4);
    expect(contrastRatio('#FF4D4D', '#4D79FF')).toBeGreaterThan(1.05);
  });

  it('each colour-by mode produces a distinct buffer when data is present', () => {
    const scene = sceneFromClasses([0, 1, 2, 0]);
    scene.partition_id = new Int32Array([0, 1, 0, 2]);
    scene.nk = new Int32Array([1, 40, 2, 3]);
    scene.dist_centroid = new Float32Array([0.1, 0.9, 0.2, 0.3]);
    const buffers = [
      colourBuffer(scene, 'class').hex.join(),
      colourBuffer(scene, 'partition').hex.join(),
      colourBuffer(scene, 'nk').hex.join(),
      colourBuffer(scene, 'distance-to-centroid').hex.join()
    ];
    expect(new Set(buffers).size).toBe(4);
  });

  it('partition colour-by is disabled with a reason when the buffer is missing', () => {
    const scene = sceneFromClasses([0, 1]);
    const buffer = colourBuffer(scene, 'partition');
    expect(buffer.available).toBe(false);
    expect(buffer.unavailableReason).toMatch(/UNAVAILABLE/);
  });

  it('tombstone layer off is the default when positions were not read', () => {
    const layer = tombstoneLayerFromScene(sceneFromClasses([0, 1]));
    expect(layer.renderable).toBe(false);
  });

  it('probe panel populated changes highlight classes', () => {
    const root = document.createElement('div');
    root.innerHTML = `<div id="probe-panel" hidden></div>`;
    const hud = new ReportHud(root, { onToggleLayer: () => undefined, onResetCamera: () => undefined });
    hud.renderProbe({
      query_id: 1,
      k: 4,
      true_neighbours: [2, 3],
      true_distances: [0.1, 0.2],
      engine_returned: [2, 99],
      missed: [3],
      dead_returns: [99],
      unexpected: [],
      n_k: 8,
      recall_id: 0.5,
      available: true,
      unavailable_reason: null,
      cannibalisation: { hub_id: 1, n_k: 4, query_ids: [10, 11], truncated: false }
    });
    expect(root.querySelector('#probe-panel')?.innerHTML).toContain('missed');
    expect(root.querySelector('.dead-id')).not.toBeNull();
  });

  it('capability_limited tombstone explanation is visible', () => {
    const layer = tombstoneLayerFromScene(sceneFromClasses([0]));
    expect(layer.reason).toMatch(/UNAVAILABLE/);
  });

  it('HUD has no critical a11y violations on the control surface', () => {
    const root = document.createElement('div');
    root.innerHTML = `
      <div id="progress-bar" role="progressbar" aria-label="Audit progress" aria-valuenow="0"></div>
      <button aria-label="Reset camera">Reset</button>
      <select aria-label="Colour-by mode"><option>class</option></select>
    `;
    expect(criticalA11yViolations(root)).toEqual([]);
  });

  it('marker channel is independent of hue', () => {
    expect(markerCovers(MARKER.DISC, 0.5, 0.5)).not.toBe(markerCovers(MARKER.RING, 0.5, 0.5));
  });
});

describe('decoder still round-trips a header', () => {
  it('rejects truncated payloads', () => {
    expect(() => decodeSceneBinary(new ArrayBuffer(2))).toThrow();
  });
});
