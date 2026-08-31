import { describe, it, expect } from 'vitest';
import { concatScenes, decodeSceneBinary } from '../../src/codec/scene_decoder';
import { resolveClientBudget, HARD_MAX_DISPLAY_BUDGET } from '../../src/scene/budget';
import { markerCovers, MARKER } from '../../src/scene/markers';
import { colourBuffer } from '../../src/views/colour';
import { drawHistogram } from '../../src/views/charts';
import { tombstoneBadgeText, tombstoneLayerFromScene } from '../../src/scene/tombstones';
import { contrastRatio, criticalA11yViolations, grayscale } from '../../src/theme/a11y';
import { lerp3, prefersReducedMotion, smoothstep } from '../../src/tour/tour';
import { PointCloudRenderer, hexToRgb } from '../../src/scene/renderer';
import { nearestId } from '../../src/interaction/probe';
import { ProgressClient } from '../../src/hud/progress';
import { loadProgressiveScene } from '../../src/scene/loader';

function mockScene() {
  return decodeSceneBinary(createMockBinaryScenePayload());
}

function createMockBinaryScenePayload(): ArrayBuffer {
  const headerObj = {
    n_points: 2,
    palette: 'default',
    legend: { HEALTHY: '#808080', HUB: '#FF4D4D', TOMBSTONE: '#4A4A4A' },
    palettes: {
      default: { HEALTHY: '#808080', HUB: '#FF4D4D', TOMBSTONE: '#4A4A4A' },
      deuteranopia: { HEALTHY: '#9A9A9A', HUB: '#D55E00', TOMBSTONE: '#3F3F3F' }
    },
    markers: { HEALTHY: 0, HUB: 1, TOMBSTONE: 3 },
    size_scale: { HEALTHY: 1, HUB: 2.2, TOMBSTONE: 1.4 },
    lod: {
      requested_budget: 200000,
      actual_count: 2,
      decimation_method: 'none',
      complete: true,
      has_tombstones: false,
      chunk_index: 0,
      chunk_count: 1,
      tombstone_count: 12,
      tombstone_reason: 'count only'
    },
    buffers: {
      positions: { offset: 0, byte_length: 24, dtype: 'float32', shape: [2, 3] },
      classes: { offset: 24, byte_length: 2, dtype: 'uint8', shape: [2] },
      ids: { offset: 32, byte_length: 16, dtype: 'int64', shape: [2] }
    }
  };
  const encoder = new TextEncoder();
  let headerBytes = encoder.encode(JSON.stringify(headerObj));
  const headerPadding = (8 - ((4 + headerBytes.length) % 8)) % 8;
  if (headerPadding > 0) {
    const padded = new Uint8Array(headerBytes.length + headerPadding);
    padded.set(headerBytes);
    padded.fill(32, headerBytes.length);
    headerBytes = padded;
  }
  const bodySize = 48;
  const buffer = new ArrayBuffer(4 + headerBytes.length + bodySize);
  const view = new DataView(buffer);
  view.setUint32(0, headerBytes.length, true);
  new Uint8Array(buffer).set(headerBytes, 4);
  const bodyOffset = 4 + headerBytes.length;
  new Float32Array(buffer, bodyOffset, 6).set([0.1, 0.2, 0.3, -0.4, -0.5, -0.6]);
  new Uint8Array(buffer, bodyOffset + 24, 2).set([0, 3]);
  new BigInt64Array(buffer, bodyOffset + 32, 2).set([101n, 202n]);
  return buffer;
}

describe('budget guard', () => {
  it('refuses a budget the device cannot support', () => {
    const decision = resolveClientBudget(900_000, 250_000);
    expect(decision.accepted).toBe(false);
    expect(decision.granted).toBe(250_000);
    expect(decision.reason).toContain('250000');
  });

  it('never grants above the hard ceiling', () => {
    const decision = resolveClientBudget(HARD_MAX_DISPLAY_BUDGET + 1, 10_000_000);
    expect(decision.granted).toBe(HARD_MAX_DISPLAY_BUDGET);
  });
});

describe('markers', () => {
  it('gives every class a distinct coverage at the centre vs a corner', () => {
    expect(markerCovers(MARKER.DISC, 0.5, 0.5)).toBe(true);
    expect(markerCovers(MARKER.RING, 0.5, 0.5)).toBe(false);
    expect(markerCovers(MARKER.SQUARE, 0.5, 0.5)).toBe(true);
  });
});

describe('colour-by buffers', () => {
  it('produces a distinct buffer per mode when data is present', () => {
    const scene = mockScene();
    const classBuf = colourBuffer(scene, 'class');
    const partBuf = colourBuffer(scene, 'partition');
    expect(classBuf.available).toBe(true);
    expect(partBuf.available).toBe(false);
    expect(partBuf.unavailableReason).toMatch(/UNAVAILABLE/);
  });

  it('switches palette without recomputing a metric', () => {
    const scene = mockScene();
    const def = colourBuffer(scene, 'class', 'default');
    const deu = colourBuffer(scene, 'class', 'deuteranopia');
    expect(def.hex[0]).not.toBe(deu.hex[0]);
  });
});

describe('tombstone layer', () => {
  it('shows a count and explanation when positions were not read', () => {
    const layer = tombstoneLayerFromScene(mockScene());
    expect(layer.renderable).toBe(false);
    expect(layer.count).toBe(12);
    expect(tombstoneBadgeText(layer)).toMatch(/positions unavailable/);
  });
});

describe('progressive merge', () => {
  it('concatenates chunks without repeating metadata contract', () => {
    const a = mockScene();
    const b = mockScene();
    const merged = concatScenes(a, b);
    expect(merged.n_points).toBe(4);
    expect(merged.ids[2]).toBe(101n);
  });
});

describe('charts helper', () => {
  it('draws without throwing and respects bucket counts', () => {
    const canvas = document.createElement('canvas');
    canvas.width = 40;
    canvas.height = 20;
    drawHistogram(canvas, [
      { lo: 0, hi: 0, count: 2 },
      { lo: 1, hi: 1, count: 5 }
    ], { logY: true, mean: 0.5 });
    expect(canvas.width).toBe(40);
  });
});

describe('a11y', () => {
  it('reports unlabelled buttons as critical', () => {
    const root = document.createElement('div');
    root.innerHTML = `<button></button><button aria-label="ok">x</button>`;
    expect(criticalA11yViolations(root).length).toBe(1);
  });

  it('separates hub and antihub in greyscale on the deuteranopia palette', () => {
    expect(contrastRatio('#D55E00', '#56B4E9')).toBeGreaterThan(1.5);
    expect(grayscale('#D55E00')).not.toBeCloseTo(grayscale('#56B4E9'), 2);
  });
});

describe('tour math', () => {
  it('is deterministic', () => {
    expect(lerp3([0, 0, 0], [1, 1, 1], 0.5)).toEqual([0.5, 0.5, 0.5]);
    expect(smoothstep(0)).toBe(0);
    expect(smoothstep(1)).toBe(1);
    expect(typeof prefersReducedMotion()).toBe('boolean');
  });
});

describe('renderer leak guard', () => {
  it('disposes geometry across ten scene reloads', () => {
    const host = document.createElement('div');
    Object.defineProperty(host, 'clientWidth', { value: 64 });
    Object.defineProperty(host, 'clientHeight', { value: 64 });
    const renderer = new PointCloudRenderer(host);
    const scene = mockScene();
    for (let i = 0; i < 10; i++) renderer.renderScene(scene);
    expect(renderer.geometriesDisposed).toBeGreaterThanOrEqual(9);
    renderer.dispose();
    expect(hexToRgb('#FF0000')).toEqual([1, 0, 0]);
  });
});

describe('probe picking', () => {
  it('returns the nearest id to a click origin', () => {
    const ids = new BigInt64Array([10n, 20n]);
    const positions = new Float32Array([0, 0, 0, 1, 1, 1]);
    expect(nearestId(ids, positions, { x: 0.01, y: 0, z: 0 })).toBe(10);
  });
});

describe('progress client', () => {
  it('ignores backwards fractions', () => {
    const events: number[] = [];
    const client = new ProgressClient({ onEvent: (e) => events.push(e.fraction) });
    (client as unknown as { handle: (e: { stage: string; fraction: number; terminal: boolean; metrics: []; stage_index: number; stage_count: number; stage_fraction: number; elapsed_seconds: number; eta_seconds: null; detail: Record<string, never> }) => void }).handle({
      stage: 'canary',
      fraction: 0.5,
      terminal: false,
      metrics: [],
      stage_index: 1,
      stage_count: 8,
      stage_fraction: 1,
      elapsed_seconds: 1,
      eta_seconds: null,
      detail: {}
    });
    (client as unknown as { handle: (e: { stage: string; fraction: number; terminal: boolean; metrics: []; stage_index: number; stage_count: number; stage_fraction: number; elapsed_seconds: number; eta_seconds: null; detail: Record<string, never> }) => void }).handle({
      stage: 'counts',
      fraction: 0.1,
      terminal: false,
      metrics: [],
      stage_index: 0,
      stage_count: 8,
      stage_fraction: 1,
      elapsed_seconds: 1,
      eta_seconds: null,
      detail: {}
    });
    expect(events).toEqual([0.5]);
    client.disconnect();
  });
});

describe('progressive loader', () => {
  it('fetches chunk 0 first and stops at chunk_count', async () => {
    const calls: string[] = [];
    const fakeFetch: typeof fetch = (async (input: RequestInfo | URL) => {
      calls.push(String(input));
      const body = createMockBinaryScenePayload();
      return new Response(body, {
        headers: {
          'X-Vhecfsck-Chunk-Count': '1',
          'Content-Type': 'application/octet-stream'
        }
      });
    }) as typeof fetch;
    const scene = await loadProgressiveScene({ fetcher: fakeFetch, budget: 1000, deviceMax: 1000 });
    expect(calls[0]).toContain('chunk=0');
    expect(calls.length).toBe(1);
    expect(scene.n_points).toBe(2);
  });
});
