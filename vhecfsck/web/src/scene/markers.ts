/** Marker coverage in the point-sprite unit square. Shape is the non-hue
 *  channel that keeps class legible when colour is not (P6-08). */

export const MARKER = {
  DOT: 0,
  DISC: 1,
  RING: 2,
  SQUARE: 3,
  CROSS: 4,
  DIAMOND: 5,
  TRIANGLE: 6,
  X_MARK: 7
} as const;

export function markerCovers(marker: number, u: number, v: number): boolean {
  const x = u * 2 - 1;
  const y = v * 2 - 1;
  const r2 = x * x + y * y;
  switch (marker) {
    case MARKER.DOT:
      return r2 <= 0.16;
    case MARKER.DISC:
      return r2 <= 1.0;
    case MARKER.RING:
      return r2 <= 1.0 && r2 >= 0.45;
    case MARKER.SQUARE:
      return Math.abs(x) <= 0.75 && Math.abs(y) <= 0.75;
    case MARKER.CROSS:
      return Math.abs(x) < 0.22 || Math.abs(y) < 0.22;
    case MARKER.DIAMOND:
      return Math.abs(x) + Math.abs(y) <= 1.0;
    case MARKER.TRIANGLE:
      return y > -0.7 && y < 0.85 - 1.6 * Math.abs(x);
    case MARKER.X_MARK:
      return Math.abs(Math.abs(x) - Math.abs(y)) < 0.22 && r2 <= 1.0;
    default:
      return r2 <= 1.0;
  }
}
