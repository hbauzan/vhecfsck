import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const workspaceRoot = path.resolve(__dirname, '../../');

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/*.spec.ts',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 30000,
  expect: {
    timeout: 5000,
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.05,
    },
  },
  reporter: [['html', { open: 'never' }], ['list']],
  use: {
    baseURL: 'http://127.0.0.1:8765',
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
    trace: 'on-first-retry',
    headless: true,
    launchOptions: {
      args: [
        '--force-device-scale-factor=1',
        '--use-gl=angle',
        '--no-sandbox',
        '--disable-setuid-sandbox',
      ],
    },
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'uv run vhecfsck serve --target synthetic://tombstoned --port 8765 --no-browser',
    url: 'http://127.0.0.1:8765/api/health',
    reuseExistingServer: !process.env.CI,
    timeout: 60 * 1000,
    cwd: workspaceRoot,
  },
});
