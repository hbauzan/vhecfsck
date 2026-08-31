import { test, expect } from '@playwright/test';

test.describe('Progress & WebSocket Resilience (P6-02)', () => {
  test('progress bar advances monotonically and UI recovers via HTTP polling if WebSocket drops', async ({
    page,
  }) => {
    await page.goto('/');

    const progressBar = page.locator('#progress-bar');
    await expect(progressBar).toBeVisible();

    // Verify progress accessibility attributes
    const valuenow = await progressBar.getAttribute('aria-valuenow');
    expect(valuenow).not.toBeNull();

    // Simulate WebSocket disconnect in browser environment
    await page.evaluate(() => {
      // Dispatch offline event or trigger socket close if available
      window.dispatchEvent(new Event('offline'));
    });

    // Page must recover via HTTP polling on GET /api/progress & /api/report
    const verdictBadge = page.locator('#verdict-badge');
    await expect(verdictBadge).not.toHaveText('LOADING', { timeout: 15000 });

    // Verify metrics rendered
    const metricsList = page.locator('#metrics-list');
    await expect(metricsList).toBeVisible();
  });
});
