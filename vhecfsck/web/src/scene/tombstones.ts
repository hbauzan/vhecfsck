import { DecodedScenePayload } from '../codec/scene_decoder';

export interface TombstoneLayerView {
  renderable: boolean;
  count: number | null;
  reason: string | null;
}

export function tombstoneLayerFromScene(scene: DecodedScenePayload): TombstoneLayerView {
  const count = scene.lod.tombstone_count ?? null;
  const reason = scene.lod.tombstone_reason ?? null;
  const renderable = Boolean(scene.lod.has_tombstones);
  return { renderable, count, reason };
}

export function tombstoneBadgeText(layer: TombstoneLayerView): string {
  if (layer.renderable && layer.count !== null) {
    return `${layer.count.toLocaleString()} tombstones`;
  }
  if (layer.count !== null) {
    return `${layer.count.toLocaleString()} tombstones (positions unavailable)`;
  }
  return 'tombstone count UNAVAILABLE';
}
