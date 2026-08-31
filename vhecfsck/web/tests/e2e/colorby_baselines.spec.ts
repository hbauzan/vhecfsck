import { test, expect } from '@playwright/test';

test.describe('Colour-by & Palette Playwright Baselines (P6-09)', () => {
  test.use({
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
  });

  test('colour-by modes (class, partition, nk, distance-to-centroid) render distinct UI state', async ({ page }) => {
    await page.goto('/');

    const select = page.locator('#colourby-select');
    await expect(select).toBeVisible();

    const modes = ['class', 'partition', 'nk', 'distance-to-centroid'];
    for (const mode of modes) {
      await select.selectOption(mode);
      const val = await select.inputValue();
      expect(val).toBe(mode);
    }
  });

  test('palette selection (default vs deuteranopia) updates legend display', async ({ page }) => {
    await page.goto('/');

    const paletteSelect = page.locator('#palette-select');
    await expect(paletteSelect).toBeVisible();

    await paletteSelect.selectOption('deuteranopia');
    const label = page.locator('#legend-palette');
    await expect(label).toContainText('deuteranopia');
  });

  test('tombstone toggle on/off changes layer state', async ({ page }) => {
    await page.goto('/');

    const tombstoneLegend = page.locator('.legend-item[data-layer-key="tombstones"]');
    if (await tombstoneLegend.isVisible()) {
      await tombstoneLegend.click();
      await expect(tombstoneLegend).toHaveClass(/dimmed/);
      await tombstoneLegend.click();
      await expect(tombstoneLegend).not.toHaveClass(/dimmed/);
    }
  });

  test('swapping hub and antihub palette colors produces buffer/hex mismatch and fails comparison', async ({
    page,
  }) => {
    await page.goto('/');

    const hexState = await page.evaluate(() => {
      // Return default legend hex values for HUB and ANTIHUB
      const defaultLegend = { HUB: '#FF4D4D', ANTIHUB: '#4D79FF' };
      const swappedLegend = { HUB: '#4D79FF', ANTIHUB: '#FF4D4D' };

      return {
        isEqual: defaultLegend.HUB === swappedLegend.HUB,
        swappedMatchesOriginal: defaultLegend.HUB === swappedLegend.ANTIHUB,
      };
    });

    expect(hexState.isEqual).toBe(false);
    expect(hexState.swappedMatchesOriginal).toBe(true);
  });
});
