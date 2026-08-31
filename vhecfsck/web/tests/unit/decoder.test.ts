import { describe, it, expect } from 'vitest';
import { decodeSceneBinary, DecodedScenePayload } from '../../src/codec/scene_decoder';

function createMockBinaryScenePayload(): ArrayBuffer {
  const headerObj = {
    n_points: 2,
    legend: {
      HEALTHY: '#808080',
      HUB: '#FF4D4D',
      TOMBSTONE: '#4A4A4A'
    },
    lod: {
      requested_budget: 200000,
      actual_count: 2,
      decimation_method: 'none',
      complete: true,
      has_tombstones: true
    },
    buffers: {
      positions: { offset: 0, byte_length: 24, dtype: 'float32', shape: [2, 3] },
      classes: { offset: 24, byte_length: 2, dtype: 'uint8', shape: [2] },
      ids: { offset: 32, byte_length: 16, dtype: 'int64', shape: [2] }
    }
  };

  const encoder = new TextEncoder();
  const headerJson = JSON.stringify(headerObj);
  let headerBytes = encoder.encode(headerJson);

  // 8-byte align header length + 4
  const headerPadding = (8 - ((4 + headerBytes.length) % 8)) % 8;
  if (headerPadding > 0) {
    const paddedHeader = new Uint8Array(headerBytes.length + headerPadding);
    paddedHeader.set(headerBytes);
    for (let i = headerBytes.length; i < paddedHeader.length; i++) {
      paddedHeader[i] = 32; // space padding
    }
    headerBytes = paddedHeader;
  }

  const positionsData = new Float32Array([0.1, 0.2, 0.3, -0.4, -0.5, -0.6]);
  const classesData = new Uint8Array([0, 3]); // HEALTHY, TOMBSTONE
  const idsData = new BigInt64Array([101n, 202n]);

  const bodySize = 32 + 16; // offset 32 + 16 bytes for ids
  const totalSize = 4 + headerBytes.length + bodySize;

  const buffer = new ArrayBuffer(totalSize);
  const view = new DataView(buffer);

  view.setUint32(0, headerBytes.length, true);

  const uint8View = new Uint8Array(buffer);
  uint8View.set(headerBytes, 4);

  const bodyOffset = 4 + headerBytes.length;

  const posDest = new Float32Array(buffer, bodyOffset, 6);
  posDest.set(positionsData);

  const clsDest = new Uint8Array(buffer, bodyOffset + 24, 2);
  clsDest.set(classesData);

  const idsDest = new BigInt64Array(buffer, bodyOffset + 32, 2);
  idsDest.set(idsData);

  return buffer;
}

describe('scene_decoder', () => {
  it('throws an error for payloads shorter than 4 bytes', () => {
    const tinyBuffer = new ArrayBuffer(2);
    expect(() => decodeSceneBinary(tinyBuffer)).toThrow('Binary scene payload too short');
  });

  it('throws an error for truncated headers', () => {
    const buffer = new ArrayBuffer(8);
    const view = new DataView(buffer);
    view.setUint32(0, 100, true); // claims header is 100 bytes long
    expect(() => decodeSceneBinary(buffer)).toThrow('Truncated binary scene header');
  });

  it('decodes a valid binary scene buffer correctly', () => {
    const buffer = createMockBinaryScenePayload();
    const scene: DecodedScenePayload = decodeSceneBinary(buffer);

    expect(scene.n_points).toBe(2);
    expect(scene.legend.HUB).toBe('#FF4D4D');
    expect(scene.lod.complete).toBe(true);
    expect(scene.lod.has_tombstones).toBe(true);

    expect(scene.positions[0]).toBeCloseTo(0.1);
    expect(scene.positions[1]).toBeCloseTo(0.2);
    expect(scene.positions[2]).toBeCloseTo(0.3);
    expect(scene.positions[3]).toBeCloseTo(-0.4);

    expect(scene.classes[0]).toBe(0); // HEALTHY
    expect(scene.classes[1]).toBe(3); // TOMBSTONE

    expect(scene.ids[0]).toBe(101n);
    expect(scene.ids[1]).toBe(202n);
  });
});
