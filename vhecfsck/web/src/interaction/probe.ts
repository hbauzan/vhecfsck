export interface ProbeResult {
  query_id: number;
  k: number;
  true_neighbours: number[];
  true_distances: number[];
  engine_returned: number[];
  missed: number[];
  dead_returns: number[];
  unexpected: number[];
  n_k: number | null;
  recall_id: number;
  available: boolean;
  unavailable_reason: string | null;
  cannibalisation: {
    hub_id: number;
    n_k: number;
    query_ids: number[];
    truncated: boolean;
  } | null;
  cached?: boolean;
}

export async function probePoint(
  id: number,
  k = 10,
  fetcher: typeof fetch = fetch
): Promise<ProbeResult> {
  const res = await fetcher('/api/probe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, k })
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `probe failed: ${res.status}`);
  }
  return (await res.json()) as ProbeResult;
}

export function nearestId(
  ids: BigInt64Array,
  positions: Float32Array,
  origin: { x: number; y: number; z: number }
): number | null {
  if (ids.length === 0) return null;
  let best = 0;
  let bestD = Infinity;
  for (let i = 0; i < ids.length; i++) {
    const dx = positions[i * 3] - origin.x;
    const dy = positions[i * 3 + 1] - origin.y;
    const dz = positions[i * 3 + 2] - origin.z;
    const d = dx * dx + dy * dy + dz * dz;
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return Number(ids[best]);
}
