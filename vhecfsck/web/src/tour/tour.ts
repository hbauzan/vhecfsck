export interface CameraPreset {
  name: string;
  position: [number, number, number];
  target: [number, number, number];
  up: [number, number, number];
  fov_degrees: number;
  caption: string;
  available: boolean;
  unavailable_reason: string | null;
}

export interface TourStep {
  preset: string;
  caption: string;
  transition_seconds: number;
  hold_seconds: number;
}

export interface TourPayload {
  fps: number;
  duration_seconds: number;
  total_frames: number;
  steps: TourStep[];
}

export interface PresetsPayload {
  presets: Record<string, CameraPreset>;
  tour: TourPayload | null;
  frame_count?: number;
}

export function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  );
}

export function lerp3(
  a: [number, number, number],
  b: [number, number, number],
  t: number
): [number, number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

export function smoothstep(t: number): number {
  return t * t * (3 - 2 * t);
}

export interface TourController {
  start: () => void;
  skip: () => void;
  next: () => void;
  prev: () => void;
  destroy: () => void;
  running: () => boolean;
}

export function createTour(
  payload: PresetsPayload,
  apply: (position: [number, number, number], target: [number, number, number], caption: string) => void,
  options: { reducedMotion?: boolean; autoplay?: boolean } = {}
): TourController {
  const tour = payload.tour;
  const reduced = options.reducedMotion ?? prefersReducedMotion();
  let timer: number | null = null;
  let step = 0;
  let running = false;

  const applyStep = (index: number) => {
    if (!tour) return;
    const beat = tour.steps[index];
    const preset = payload.presets[beat.preset];
    if (!preset) return;
    apply(preset.position, preset.target, beat.caption);
  };

  const stop = () => {
    if (timer !== null) {
      window.clearTimeout(timer);
      timer = null;
    }
    running = false;
  };

  const schedule = () => {
    if (!tour || reduced) return;
    const beat = tour.steps[step];
    const ms = (beat.transition_seconds + beat.hold_seconds) * 1000;
    timer = window.setTimeout(() => {
      if (step < tour.steps.length - 1) {
        step += 1;
        applyStep(step);
        schedule();
      } else {
        stop();
      }
    }, ms);
  };

  return {
    start: () => {
      if (!tour || tour.steps.length === 0) return;
      running = true;
      step = 0;
      applyStep(0);
      if (!reduced && options.autoplay !== false) schedule();
    },
    skip: () => {
      stop();
    },
    next: () => {
      if (!tour) return;
      step = Math.min(step + 1, tour.steps.length - 1);
      applyStep(step);
    },
    prev: () => {
      if (!tour) return;
      step = Math.max(step - 1, 0);
      applyStep(step);
    },
    destroy: stop,
    running: () => running
  };
}
