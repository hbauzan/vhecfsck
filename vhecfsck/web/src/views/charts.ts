export interface HistogramBucket {
  lo: number;
  hi: number;
  count: number;
}

export interface ChartsPayload {
  nk_histogram: HistogramBucket[];
  nk_log_y: boolean;
  partition_histogram: HistogramBucket[] | null;
  partition_mean: number | null;
  partition_unavailable_reason: string | null;
}

export function drawHistogram(
  canvas: HTMLCanvasElement,
  buckets: HistogramBucket[],
  options: { logY?: boolean; mean?: number | null; fill?: string } = {}
): void {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  if (buckets.length === 0) return;

  const counts = buckets.map((b) => b.count);
  const maxCount = Math.max(...counts, 1);
  const logY = Boolean(options.logY);
  const maxY = logY ? Math.log10(maxCount + 1) : maxCount;
  const barW = w / buckets.length;
  const fill = options.fill ?? '#56B4E9';

  ctx.fillStyle = fill;
  for (let i = 0; i < buckets.length; i++) {
    const raw = logY ? Math.log10(buckets[i].count + 1) : buckets[i].count;
    const barH = (raw / maxY) * (h - 4);
    ctx.fillRect(i * barW + 1, h - barH, Math.max(1, barW - 2), barH);
  }

  if (options.mean !== null && options.mean !== undefined && buckets.length > 0) {
    const lo = buckets[0].lo;
    const hi = buckets[buckets.length - 1].hi;
    const span = hi - lo || 1;
    const x = ((options.mean - lo) / span) * w;
    ctx.strokeStyle = '#F0E442';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }
}
