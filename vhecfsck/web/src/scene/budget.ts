/** Client-side display-budget guard. Numbers come from ``core.lod``; this module
 *  only refuses to ask the renderer for a budget the device cannot support. */

export const DEFAULT_DISPLAY_BUDGET = 200_000;
export const HARD_MAX_DISPLAY_BUDGET = 1_000_000;

export interface BudgetDecision {
  requested: number;
  granted: number;
  accepted: boolean;
  reason: string | null;
  deviceMax: number;
}

export function estimateDeviceMaxPoints(): number {
  const cores = typeof navigator !== 'undefined' ? navigator.hardwareConcurrency || 4 : 4;
  // Conservative envelope for integrated graphics. Not a measured fps budget.
  const guessed = cores >= 8 ? 400_000 : DEFAULT_DISPLAY_BUDGET;
  return Math.min(guessed, HARD_MAX_DISPLAY_BUDGET);
}

export function resolveClientBudget(
  requested: number,
  deviceMax: number = estimateDeviceMaxPoints(),
  hardMax: number = HARD_MAX_DISPLAY_BUDGET
): BudgetDecision {
  if (requested < 1) {
    throw new Error('budget must be >= 1');
  }
  const ceiling = Math.min(Math.floor(deviceMax), Math.floor(hardMax));
  if (requested <= ceiling) {
    return {
      requested,
      granted: requested,
      accepted: true,
      reason: null,
      deviceMax: ceiling
    };
  }
  const limitName = deviceMax < hardMax ? 'device capability' : 'hard ceiling';
  return {
    requested,
    granted: ceiling,
    accepted: false,
    reason: `requested budget ${requested} exceeds the ${limitName} of ${ceiling} points; render at most ${ceiling}`,
    deviceMax: ceiling
  };
}
