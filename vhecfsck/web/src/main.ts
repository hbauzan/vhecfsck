import { PointCloudRenderer } from './scene/renderer';
import { ReportHud, ReportPayload } from './hud/hud';
import { decodeSceneBinary } from './codec/scene_decoder';

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
    }
  });

  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      renderer.resetCamera();
    });
  }

  try {
    const reportRes = await fetch('/api/report');
    if (reportRes.ok) {
      const reportData: ReportPayload = await reportRes.json();
      hud.renderReport(reportData);
    }
  } catch (err) {
    console.warn('Failed to fetch /api/report:', err);
  }

  try {
    const sceneRes = await fetch('/api/scene?budget=200000');
    if (sceneRes.ok) {
      const sceneBuffer = await sceneRes.arrayBuffer();
      const sceneData = decodeSceneBinary(sceneBuffer);
      renderer.renderScene(sceneData);
      hud.updateLodBanner(sceneData);
    }
  } catch (err) {
    console.warn('Failed to fetch /api/scene:', err);
  }
}

document.addEventListener('DOMContentLoaded', bootstrap);
