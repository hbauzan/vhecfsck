import { PointCloudRenderer } from './scene/renderer';
import { ReportHud, ReportPayload } from './hud/hud';
import { loadProgressiveScene } from './scene/loader';
import { ProgressClient } from './hud/progress';
import { probePoint } from './interaction/probe';
import { colourBuffer, ColourByMode } from './views/colour';
import { ChartsPayload } from './views/charts';
import { createTour, prefersReducedMotion, PresetsPayload, TourController } from './tour/tour';
import { DEFAULT_DISPLAY_BUDGET, estimateDeviceMaxPoints } from './scene/budget';
import { DecodedScenePayload } from './codec/scene_decoder';

let currentScene: DecodedScenePayload | null = null;
let currentPalette = 'default';
let colourBy: ColourByMode = 'class';
let tour: TourController | null = null;
let tourPlayed = false;
let startTourFn: (() => void) | null = null;

function applyView(renderer: PointCloudRenderer, hud: ReportHud): void {
  if (!currentScene) return;
  const buffer = colourBuffer(currentScene, colourBy, currentPalette);
  hud.setColourBy(colourBy, buffer.unavailableReason);
  if (buffer.available) renderer.applyColourHex(buffer.hex);
}

async function loadScene(
  renderer: PointCloudRenderer,
  hud: ReportHud
): Promise<void> {
  const deviceMax = estimateDeviceMaxPoints();
  currentScene = await loadProgressiveScene({
    budget: DEFAULT_DISPLAY_BUDGET,
    deviceMax,
    palette: currentPalette,
    onChunk: (scene, progress) => {
      currentScene = scene;
      renderer.renderScene(scene);
      hud.updateLodBanner(scene, progress.budgetRefused);
      applyView(renderer, hud);
    }
  });
}

async function loadCharts(hud: ReportHud): Promise<void> {
  try {
    const res = await fetch('/api/charts');
    if (!res.ok) return;
    const charts = (await res.json()) as ChartsPayload;
    hud.renderCharts(charts);
  } catch {
    // charts are advisory
  }
}

async function loadPresets(
  renderer: PointCloudRenderer,
  hud: ReportHud
): Promise<PresetsPayload | null> {
  try {
    const res = await fetch('/api/presets');
    if (!res.ok) return null;
    const payload = (await res.json()) as PresetsPayload;
    const startTour = () => {
      tour?.destroy();
      tour = createTour(
        payload,
        (position, target, _caption) => {
          renderer.applyCamera(position, target);
        },
        { reducedMotion: prefersReducedMotion(), autoplay: !tourPlayed }
      );
      tour.start();
      tourPlayed = true;
    };
    hud.setTourHandler(startTour);
    startTourFn = startTour;
    return payload;
  } catch {
    return null;
  }
}

async function bootstrap() {
  const canvasContainer = document.getElementById('canvas-container');
  const hudContainer = document.getElementById('hud-overlay');
  const fallbackEl = document.getElementById('webgl-fallback');
  const resetBtn = document.getElementById('reset-cam-btn');

  if (!canvasContainer || !hudContainer) return;

  const renderer = new PointCloudRenderer(canvasContainer);
  const isWebGlAvailable = renderer.init();

  if (!isWebGlAvailable && fallbackEl) {
    fallbackEl.style.display = 'block';
    return;
  }

  const hud = new ReportHud(hudContainer, {
    onToggleLayer: (layer) => {
      renderer.toggleLayer(layer);
    },
    onResetCamera: () => {
      renderer.resetCamera();
    },
    onColourBy: (mode) => {
      colourBy = mode;
      applyView(renderer, hud);
    },
    onPalette: (name) => {
      currentPalette = name;
      if (currentScene) {
        currentScene = { ...currentScene, palette: name };
        applyView(renderer, hud);
        hud.updateLodBanner(currentScene);
      }
    },
    onPreset: async (name) => {
      const res = await fetch('/api/presets');
      if (!res.ok) return;
      const payload = (await res.json()) as PresetsPayload;
      const preset = payload.presets[name];
      if (preset?.available) renderer.applyCamera(preset.position, preset.target);
    },
    onTourSkip: () => tour?.skip()
  });

  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      renderer.resetCamera();
    });
  }
  document.getElementById('tour-btn')?.addEventListener('click', () => startTourFn?.());
  document.getElementById('tour-skip-btn')?.addEventListener('click', () => tour?.skip());
  document.querySelectorAll('[data-preset]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const name = (btn as HTMLElement).dataset.preset;
      if (name) void (async () => {
        const res = await fetch('/api/presets');
        if (!res.ok) return;
        const payload = (await res.json()) as PresetsPayload;
        const preset = payload.presets[name];
        if (preset?.available) renderer.applyCamera(preset.position, preset.target);
      })();
    });
  });

  canvasContainer.addEventListener('click', async (ev) => {
    const id = renderer.pickId(ev.clientX, ev.clientY);
    if (id === null) return;
    try {
      const result = await probePoint(id);
      hud.renderProbe(result);
      renderer.highlightIds(new Set(result.true_neighbours), '#00FF7F');
      renderer.highlightIds(new Set(result.missed), '#FF1493');
      renderer.highlightIds(new Set(result.engine_returned), '#00BFFF');
      if (result.cannibalisation) {
        renderer.highlightIds(new Set(result.cannibalisation.query_ids), '#D55E00');
      }
    } catch (err) {
      console.warn('probe failed', err);
    }
  });

  try {
    const reportRes = await fetch('/api/report');
    if (reportRes.ok) {
      const reportData: ReportPayload = await reportRes.json();
      hud.renderReport(reportData);
    }
  } catch (err) {
    console.warn('Failed to fetch /api/report:', err);
  }

  const progress = new ProgressClient({
    onEvent: (event) => hud.updateProgress(event),
    onSceneReady: () => {
      void loadScene(renderer, hud);
    },
    onTerminal: () => {
      void loadScene(renderer, hud);
      void loadCharts(hud);
      void loadPresets(renderer, hud);
    }
  });
  progress.connect();
  // Paint immediately from whatever is already on the server (serve --report).
  void loadScene(renderer, hud);
  void loadCharts(hud);
  void loadPresets(renderer, hud);
}

document.addEventListener('DOMContentLoaded', () => {
  void bootstrap();
});
