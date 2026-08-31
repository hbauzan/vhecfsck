import { DecodedScenePayload, className } from '../codec/scene_decoder';

export type ColourByMode = 'class' | 'partition' | 'nk' | 'distance-to-centroid';

export interface ColourBuffer {
  mode: ColourByMode;
  hex: string[];
  available: boolean;
  unavailableReason: string | null;
}

const PARTITION_RAMP = [
  '#0072B2',
  '#E69F00',
  '#009E73',
  '#CC79A7',
  '#56B4E9',
  '#D55E00',
  '#F0E442',
  '#999999'
];

function lerpHex(a: string, b: string, t: number): string {
  const parse = (h: string): [number, number, number] => {
    const raw = h.replace('#', '');
    return [
      parseInt(raw.slice(0, 2), 16),
      parseInt(raw.slice(2, 4), 16),
      parseInt(raw.slice(4, 6), 16)
    ];
  };
  const [ar, ag, ab] = parse(a);
  const [br, bg, bb] = parse(b);
  const hex = (n: number) =>
    Math.max(0, Math.min(255, Math.round(n)))
      .toString(16)
      .padStart(2, '0');
  return `#${hex(ar + (br - ar) * t)}${hex(ag + (bg - ag) * t)}${hex(ab + (bb - ab) * t)}`;
}

export function colourBuffer(
  scene: DecodedScenePayload,
  mode: ColourByMode,
  paletteName: string = scene.palette
): ColourBuffer {
  const n = scene.n_points;
  const palette = (scene.palettes ?? {})[paletteName] ?? scene.legend;

  if (mode === 'class') {
    const hex = Array.from({ length: n }, (_, i) => palette[className(scene.classes[i])] ?? '#808080');
    return { mode, hex, available: true, unavailableReason: null };
  }

  if (mode === 'partition') {
    if (!scene.partition_id) {
      return {
        mode,
        hex: [],
        available: false,
        unavailableReason:
          'partition data is UNAVAILABLE for this target: the adapter does not expose IVF partition assignments'
      };
    }
    const hex = Array.from({ length: n }, (_, i) => {
      const id = scene.partition_id![i];
      return PARTITION_RAMP[((id % PARTITION_RAMP.length) + PARTITION_RAMP.length) % PARTITION_RAMP.length];
    });
    return { mode, hex, available: true, unavailableReason: null };
  }

  const source = mode === 'nk' ? scene.nk : scene.dist_centroid;
  if (!source) {
    return {
      mode,
      hex: [],
      available: false,
      unavailableReason:
        mode === 'nk'
          ? 'in-degree data is UNAVAILABLE for this scene: hubness did not run or the adapter could not supply neighbours'
          : 'distance-to-centroid buffer is missing'
    };
  }

  let lo = Infinity;
  let hi = -Infinity;
  for (let i = 0; i < n; i++) {
    const v = source[i];
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  const span = hi - lo;
  const hex = Array.from({ length: n }, (_, i) => {
    const t = span <= 0 ? 0 : (source[i] - lo) / span;
    return lerpHex('#0072B2', '#E69F00', t);
  });
  return { mode, hex, available: true, unavailableReason: null };
}
