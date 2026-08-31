export interface LodMetadata {
  requested_budget: number;
  actual_count: number;
  decimation_method: string;
  complete: boolean;
  has_tombstones: boolean;
  chunk_index?: number;
  chunk_count?: number;
  total_available?: number | null;
  tombstone_count?: number | null;
  tombstone_reason?: string | null;
}

export interface BufferInfo {
  offset: number;
  byte_length: number;
  dtype: string;
  shape: number[];
}

export interface SceneHeader {
  n_points: number;
  legend: Record<string, string>;
  palette?: string;
  palettes?: Record<string, Record<string, string>>;
  markers?: Record<string, number>;
  size_scale?: Record<string, number>;
  lod: LodMetadata;
  buffers: Record<string, BufferInfo>;
}

export interface DecodedScenePayload {
  n_points: number;
  legend: Record<string, string>;
  palette: string;
  palettes: Record<string, Record<string, string>>;
  markers: Record<string, number>;
  size_scale: Record<string, number>;
  lod: LodMetadata;
  positions: Float32Array;
  classes: Uint8Array;
  ids: BigInt64Array;
  partition_id?: Int32Array;
  nk?: Int32Array;
  dist_centroid?: Float32Array;
}

const CLASS_NAMES = [
  'HEALTHY',
  'HUB',
  'ANTIHUB',
  'TOMBSTONE',
  'QUERY',
  'TRUE_NEIGHBOUR',
  'RETURNED',
  'MISSED'
] as const;

export function className(cls: number): string {
  return CLASS_NAMES[cls] ?? 'HEALTHY';
}

function readTyped<T extends ArrayBufferView>(
  ctor: new (buffer: ArrayBuffer, byteOffset: number, length: number) => T,
  buffer: ArrayBuffer,
  bodyOffset: number,
  info: BufferInfo,
  bytesPer: number
): T {
  return new ctor(buffer, bodyOffset + info.offset, info.byte_length / bytesPer);
}

export function decodeSceneBinary(arrayBuffer: ArrayBuffer): DecodedScenePayload {
  if (arrayBuffer.byteLength < 4) {
    throw new Error('Binary scene payload too short (minimum 4 bytes required for header length)');
  }

  const view = new DataView(arrayBuffer);
  const headerLen = view.getUint32(0, true);

  const headerEnd = 4 + headerLen;
  if (arrayBuffer.byteLength < headerEnd) {
    throw new Error(
      `Truncated binary scene header: payload size ${arrayBuffer.byteLength} < ${headerEnd}`
    );
  }

  const decoder = new TextDecoder('utf-8');
  const headerBytes = new Uint8Array(arrayBuffer, 4, headerLen);
  const header: SceneHeader = JSON.parse(decoder.decode(headerBytes));

  const bodyOffset = headerEnd;
  const buffersInfo = header.buffers;

  const posInfo = buffersInfo.positions;
  if (!posInfo) throw new Error('Missing positions buffer in header');
  const positions = readTyped(Float32Array, arrayBuffer, bodyOffset, posInfo, 4);

  const clsInfo = buffersInfo.classes;
  if (!clsInfo) throw new Error('Missing classes buffer in header');
  const classes = readTyped(Uint8Array, arrayBuffer, bodyOffset, clsInfo, 1);

  const idsInfo = buffersInfo.ids;
  if (!idsInfo) throw new Error('Missing ids buffer in header');
  const ids = readTyped(BigInt64Array, arrayBuffer, bodyOffset, idsInfo, 8);

  let partition_id: Int32Array | undefined;
  if (buffersInfo.partition_id) {
    partition_id = readTyped(Int32Array, arrayBuffer, bodyOffset, buffersInfo.partition_id, 4);
  }

  let nk: Int32Array | undefined;
  if (buffersInfo.nk) {
    nk = readTyped(Int32Array, arrayBuffer, bodyOffset, buffersInfo.nk, 4);
  }

  let dist_centroid: Float32Array | undefined;
  if (buffersInfo.dist_centroid) {
    dist_centroid = readTyped(Float32Array, arrayBuffer, bodyOffset, buffersInfo.dist_centroid, 4);
  }

  return {
    n_points: header.n_points,
    legend: header.legend,
    palette: header.palette ?? 'default',
    palettes: header.palettes ?? { default: header.legend },
    markers: header.markers ?? {},
    size_scale: header.size_scale ?? {},
    lod: header.lod,
    positions,
    classes,
    ids,
    partition_id,
    nk,
    dist_centroid
  };
}

export function concatScenes(
  first: DecodedScenePayload,
  next: DecodedScenePayload
): DecodedScenePayload {
  const n = first.n_points + next.n_points;
  const positions = new Float32Array(n * 3);
  positions.set(first.positions);
  positions.set(next.positions, first.positions.length);
  const classes = new Uint8Array(n);
  classes.set(first.classes);
  classes.set(next.classes, first.classes.length);
  const ids = new BigInt64Array(n);
  ids.set(first.ids);
  ids.set(next.ids, first.ids.length);

  const mergeOptional = <T extends Float32Array | Int32Array>(
    Ctor: new (length: number) => T,
    a?: T,
    b?: T
  ): T | undefined => {
    if (!a && !b) return undefined;
    const out = new Ctor(n);
    if (a) out.set(a as unknown as ArrayLike<number>, 0);
    if (b) out.set(b as unknown as ArrayLike<number>, first.n_points);
    return out;
  };

  return {
    n_points: n,
    legend: next.legend,
    palette: next.palette,
    palettes: next.palettes,
    markers: next.markers,
    size_scale: next.size_scale,
    lod: {
      ...next.lod,
      actual_count: n
    },
    positions,
    classes,
    ids,
    partition_id: mergeOptional(Int32Array, first.partition_id, next.partition_id),
    nk: mergeOptional(Int32Array, first.nk, next.nk),
    dist_centroid: mergeOptional(
      Float32Array,
      first.dist_centroid,
      next.dist_centroid
    )
  };
}
