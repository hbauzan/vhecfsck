import { concatScenes, decodeSceneBinary, DecodedScenePayload } from '../codec/scene_decoder';
import { DEFAULT_DISPLAY_BUDGET, resolveClientBudget } from './budget';

export interface LoadProgress {
  chunkIndex: number;
  chunkCount: number;
  points: number;
  complete: boolean;
  budgetRefused: string | null;
}

export async function fetchSceneChunk(
  budget: number,
  chunk: number,
  deviceMax: number,
  palette: string,
  fetcher: typeof fetch = fetch
): Promise<{ scene: DecodedScenePayload; headers: Headers }> {
  const url =
    `/api/scene?budget=${budget}&chunk=${chunk}&device_max=${deviceMax}` +
    `&palette=${encodeURIComponent(palette)}`;
  const res = await fetcher(url);
  if (!res.ok) {
    throw new Error(`scene chunk ${chunk} failed: ${res.status}`);
  }
  const buffer = await res.arrayBuffer();
  return { scene: decodeSceneBinary(buffer), headers: res.headers };
}

export async function loadProgressiveScene(
  options: {
    budget?: number;
    palette?: string;
    deviceMax?: number;
    fetcher?: typeof fetch;
    onChunk?: (scene: DecodedScenePayload, progress: LoadProgress) => void;
  } = {}
): Promise<DecodedScenePayload> {
  const decision = resolveClientBudget(options.budget ?? DEFAULT_DISPLAY_BUDGET, options.deviceMax);
  if (!decision.accepted && options.onChunk) {
    // Surface the refusal before any fetch so the HUD can say so.
    options.onChunk(
      {
        n_points: 0,
        legend: {},
        palette: options.palette ?? 'default',
        palettes: {},
        markers: {},
        size_scale: {},
        lod: {
          requested_budget: decision.requested,
          actual_count: 0,
          decimation_method: 'none',
          complete: false,
          has_tombstones: false
        },
        positions: new Float32Array(),
        classes: new Uint8Array(),
        ids: new BigInt64Array()
      },
      {
        chunkIndex: 0,
        chunkCount: 0,
        points: 0,
        complete: false,
        budgetRefused: decision.reason
      }
    );
  }

  const palette = options.palette ?? 'default';
  const fetcher = options.fetcher ?? fetch;
  const first = await fetchSceneChunk(decision.granted, 0, decision.deviceMax, palette, fetcher);
  const chunkCount = Number(first.headers.get('X-Vhecfsck-Chunk-Count') ?? '1');
  const refused = first.headers.get('X-Vhecfsck-Budget-Refused');
  let merged = first.scene;
  options.onChunk?.(merged, {
    chunkIndex: 0,
    chunkCount,
    points: merged.n_points,
    complete: chunkCount <= 1,
    budgetRefused: refused
  });

  for (let i = 1; i < chunkCount; i++) {
    const next = await fetchSceneChunk(decision.granted, i, decision.deviceMax, palette, fetcher);
    merged = concatScenes(merged, next.scene);
    options.onChunk?.(merged, {
      chunkIndex: i,
      chunkCount,
      points: merged.n_points,
      complete: i === chunkCount - 1,
      budgetRefused: refused
    });
  }
  return merged;
}
