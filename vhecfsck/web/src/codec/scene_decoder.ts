export interface LodMetadata {
  requested_budget: number;
  actual_count: number;
  decimation_method: string;
  complete: boolean;
  has_tombstones: boolean;
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
  lod: LodMetadata;
  buffers: Record<string, BufferInfo>;
}

export interface DecodedScenePayload {
  n_points: number;
  legend: Record<string, string>;
  lod: LodMetadata;
  positions: Float32Array;
  classes: Uint8Array;
  ids: BigInt64Array;
  partition_id?: Int32Array;
  nk?: Int32Array;
}

export function decodeSceneBinary(arrayBuffer: ArrayBuffer): DecodedScenePayload {
  if (arrayBuffer.byteLength < 4) {
    throw new Error('Binary scene payload too short (minimum 4 bytes required for header length)');
  }

  const view = new DataView(arrayBuffer);
  const headerLen = view.getUint32(0, true); // Little-endian

  const headerEnd = 4 + headerLen;
  if (arrayBuffer.byteLength < headerEnd) {
    throw new Error(`Truncated binary scene header: payload size ${arrayBuffer.byteLength} < ${headerEnd}`);
  }

  const decoder = new TextDecoder('utf-8');
  const headerBytes = new Uint8Array(arrayBuffer, 4, headerLen);
  const headerJsonStr = decoder.decode(headerBytes);
  const header: SceneHeader = JSON.parse(headerJsonStr);

  const bodyOffset = headerEnd;
  const buffersInfo = header.buffers;

  const posInfo = buffersInfo.positions;
  if (!posInfo) throw new Error('Missing positions buffer in header');
  const positions = new Float32Array(
    arrayBuffer,
    bodyOffset + posInfo.offset,
    posInfo.byte_length / 4
  );

  const clsInfo = buffersInfo.classes;
  if (!clsInfo) throw new Error('Missing classes buffer in header');
  const classes = new Uint8Array(
    arrayBuffer,
    bodyOffset + clsInfo.offset,
    clsInfo.byte_length
  );

  const idsInfo = buffersInfo.ids;
  if (!idsInfo) throw new Error('Missing ids buffer in header');
  const ids = new BigInt64Array(
    arrayBuffer,
    bodyOffset + idsInfo.offset,
    idsInfo.byte_length / 8
  );

  let partition_id: Int32Array | undefined = undefined;
  if (buffersInfo.partition_id) {
    const ptInfo = buffersInfo.partition_id;
    partition_id = new Int32Array(
      arrayBuffer,
      bodyOffset + ptInfo.offset,
      ptInfo.byte_length / 4
    );
  }

  let nk: Int32Array | undefined = undefined;
  if (buffersInfo.nk) {
    const nkInfo = buffersInfo.nk;
    nk = new Int32Array(
      arrayBuffer,
      bodyOffset + nkInfo.offset,
      nkInfo.byte_length / 4
    );
  }

  return {
    n_points: header.n_points,
    legend: header.legend,
    lod: header.lod,
    positions,
    classes,
    ids,
    partition_id,
    nk
  };
}
