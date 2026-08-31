export const CLASS_ORDER = [
  'HEALTHY',
  'HUB',
  'ANTIHUB',
  'TOMBSTONE',
  'QUERY',
  'TRUE_NEIGHBOUR',
  'RETURNED',
  'MISSED'
] as const;

export function grayscale(hex: string): number {
  const raw = hex.replace('#', '');
  const r = parseInt(raw.slice(0, 2), 16) / 255;
  const g = parseInt(raw.slice(2, 4), 16) / 255;
  const b = parseInt(raw.slice(4, 6), 16) / 255;
  const lin = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

export function contrastRatio(a: string, b: string): number {
  const la = grayscale(a);
  const lb = grayscale(b);
  const light = Math.max(la, lb);
  const dark = Math.min(la, lb);
  return (light + 0.05) / (dark + 0.05);
}

export function criticalA11yViolations(root: ParentNode): string[] {
  const violations: string[] = [];
  const labelled = root.querySelectorAll('button, select, input, [role="button"]');
  labelled.forEach((el) => {
    const node = el as HTMLElement;
    const name =
      node.getAttribute('aria-label') ||
      node.getAttribute('aria-labelledby') ||
      node.textContent?.trim();
    if (!name) violations.push(`unlabelled control: ${node.tagName}`);
  });
  const progress = root.querySelector('[role="progressbar"]');
  if (progress && !progress.getAttribute('aria-valuenow')) {
    violations.push('progressbar missing aria-valuenow');
  }
  return violations;
}
