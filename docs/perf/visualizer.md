# Visualizer display budget

The default display budget is `200_000` points (`vhecfsck.core.lod.DEFAULT_DISPLAY_BUDGET`).
The hard ceiling is `1_000_000` (`HARD_MAX_DISPLAY_BUDGET`). A client that asks for more
than the device reports it can sustain is refused with a reason rather than left to hang
the tab.

**60 fps** is the product target on integrated graphics. This tree does not record a
wall-clock frame-rate measurement on a named reference machine; that number is owned by
**P8-04**. The gate asserts the properties that do not need a GPU:

- hubs and anti-hubs arrive in chunk 0
- a budget above `device_max` is refused
- ten scene reloads dispose geometry (no Three.js leak)

To regenerate the README tour asset: `make demo-gif`.
