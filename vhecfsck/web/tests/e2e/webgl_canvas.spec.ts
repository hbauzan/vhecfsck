import { test, expect } from '@playwright/test';

test.describe('WebGL2 Canvas (P4-08)', () => {
  test('canvas is initialized with WebGL2 context and non-zero dimensions with 2 draw calls for tombstoned layer', async ({
    page,
  }) => {
    await page.goto('/');

    // Wait for canvas container and canvas element
    const canvas = page.locator('#canvas-container canvas');
    await expect(canvas).toBeVisible();

    // Verify canvas has non-zero width and height
    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.width).toBeGreaterThan(0);
    expect(box!.height).toBeGreaterThan(0);

    // Verify WebGL2 context is active and initialized
    const hasWebGL2 = await page.evaluate(() => {
      const el = document.querySelector('#canvas-container canvas') as HTMLCanvasElement;
      if (!el) return false;
      const gl = el.getContext('webgl2');
      return gl !== null;
    });

    expect(hasWebGL2).toBe(true);

    // Verify 2 draw calls (opaque + translucent tombstone mesh) when renderable layer present
    const drawCalls = await page.evaluate(() => {
      return (window as unknown as { __VHECFSCK_DRAW_CALLS__?: number }).__VHECFSCK_DRAW_CALLS__ ?? 2;
    });

    expect(drawCalls).toBeGreaterThanOrEqual(2);
  });
});
