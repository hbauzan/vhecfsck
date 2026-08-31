# Visual regression baselines (P6-09)

These tests live in `vhecfsck/web/tests/visual/` and run with:

```bash
npm --prefix vhecfsck/web run test:visual
```

They compare palette buffers, marker coverage, tombstone-layer policy, the populated
probe panel, and the `capability_limited` explanation. Animation is disabled by not
starting the tour. Viewport is irrelevant: the assertions are on computed buffers,
not screenshots, so they do not false-positive on GPU/driver noise.

## Updating a baseline

1. Change the buffer or HUD assertion in `baselines.test.ts`.
2. Run `npm --prefix vhecfsck/web run test:visual` and confirm the failure is the
   intended one (swapping hub/anti-hub colours must fail).
3. Commit the test change in the same pull request as the images or buffer
   expectations it introduces. Do not land a baseline update without the image or
   hex dump visible in the diff.
