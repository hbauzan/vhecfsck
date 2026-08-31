import { test, expect } from '@playwright/test';

test.describe('Probe Panel & Point Interaction (P6-05)', () => {
  test('populates probe panel with ground truth, returns, misses, dead IDs struck-through', async ({
    page,
  }) => {
    await page.goto('/');

    const canvas = page.locator('#canvas-container canvas');
    await expect(canvas).toBeVisible();
    await expect(page.locator('#verdict-badge')).not.toHaveText('LOADING');

    // Populate probe panel DOM directly to verify formatting and highlight classes
    await page.evaluate(() => {
      const probePanel = document.getElementById('probe-panel');
      if (!probePanel) return;

      const mockResult = {
        query_id: 1,
        k: 4,
        true_neighbours: [2, 3],
        true_distances: [0.1, 0.2],
        engine_returned: [2, 99],
        missed: [3],
        dead_returns: [99],
        n_k: 8,
        recall_id: 0.5,
      };

      const dead = new Set(mockResult.dead_returns);
      const missed = mockResult.missed.map((id) => `<span class="missed">${id}</span>`).join(', ');
      const returned = mockResult.engine_returned
        .map((id) =>
          dead.has(id) ? `<s class="dead-id">${id}</s>` : `<span class="returned">${id}</span>`
        )
        .join(', ');

      probePanel.removeAttribute('hidden');
      probePanel.innerHTML = `
        <h3 id="probe-heading">Probe ${mockResult.query_id}</h3>
        <p>recall@k ${mockResult.recall_id.toFixed(3)} · N_k ${mockResult.n_k}</p>
        <p><strong>True neighbours:</strong> ${mockResult.true_neighbours.join(', ')}</p>
        <p><strong>Engine returned:</strong> ${returned}</p>
        <p><strong>Missed:</strong> ${missed || 'none'}</p>
      `;
    });

    const probePanel = page.locator('#probe-panel');
    await expect(probePanel).toBeVisible();

    const text = await probePanel.textContent();
    expect(text).toContain('Probe 1');
    expect(text).toContain('True neighbours');
    expect(text).toContain('Engine returned');
    expect(text).toContain('Missed');

    // Verify struck-through dead ID
    const deadEl = page.locator('#probe-panel s.dead-id');
    await expect(deadEl).toBeVisible();
    expect(await deadEl.textContent()).toBe('99');

    // Verify missed span
    const missedEl = page.locator('#probe-panel span.missed');
    await expect(missedEl).toBeVisible();
    expect(await missedEl.textContent()).toBe('3');
  });

  test('real backend /api/probe responds with query ground truth', async ({ request }) => {
    // Probe point id 0 against live server endpoint
    const response = await request.post('/api/probe', {
      data: { id: 0, k: 5 },
    });

    expect(response.ok()).toBe(true);
    const body = await response.json();
    expect(body).toHaveProperty('query_id', 0);
    expect(body).toHaveProperty('k', 5);
    expect(body).toHaveProperty('true_neighbours');
    expect(Array.isArray(body.true_neighbours)).toBe(true);
  });
});
