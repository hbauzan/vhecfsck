import { test, expect } from '@playwright/test';

test.describe('HUD Verdict (P4-09)', () => {
  test('HUD renders the report verdict badge for tombstoned scenario', async ({ page }) => {
    await page.goto('/');

    const verdictBadge = page.locator('#verdict-badge');
    await expect(verdictBadge).toBeVisible();

    // Wait until verdict updates from LOADING to final verdict (e.g. FAIL or WARN or OK)
    await expect(verdictBadge).not.toHaveText('LOADING', { timeout: 10000 });

    const text = await verdictBadge.textContent();
    expect(text?.trim()).toMatch(/^(OK|WARN|FAIL|INCONCLUSIVE)$/);

    // Specifically for tombstoned scenario, verdict should be FAIL or WARN
    expect(text?.trim()).not.toBe('OK');
  });
});
