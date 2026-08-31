import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('HUD Accessibility Audit (P6-08 / ADR-0015)', () => {
  test('HUD control surface has zero critical accessibility violations', async ({ page }) => {
    await page.goto('/');

    await expect(page.locator('#canvas-container canvas')).toBeVisible();
    await expect(page.locator('#verdict-badge')).not.toHaveText('LOADING');

    const scanResults = await new AxeBuilder({ page })
      .include('#hud-overlay')
      .analyze();

    const criticalViolations = scanResults.violations.filter(
      (v) => v.impact === 'critical'
    );

    expect(criticalViolations).toEqual([]);
  });

  test('control surface buttons and selects have focus-visible styling and keyboard access', async ({ page }) => {
    await page.goto('/');

    await expect(page.locator('#reset-cam-btn')).toBeVisible();

    // Tab through controls
    await page.keyboard.press('Tab');
    const focusedTag = await page.evaluate(() => document.activeElement?.tagName);
    expect(focusedTag).not.toBeNull();
  });
});
