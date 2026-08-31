"""Report-derived camera presets and a frame-deterministic guided tour.

P6-06. Presets aim at whatever the audit actually found — the hub cluster of
*this* index, not a coordinate someone liked once — so the same script produces
a meaningful shot on every corpus. The tour is sampled from a declarative
timeline rather than driven by wall-clock animation, which is what makes a
recording reproducible frame for frame.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from vhecfsck.models.scene import PointClass, ScenePayload

OVERVIEW = "overview"
HUB_CLUSTER = "hub-cluster"
ANTIHUB_PERIPHERY = "antihub-periphery"
WORST_PARTITION = "worst-partition"

PRESET_NAMES = (OVERVIEW, HUB_CLUSTER, ANTIHUB_PERIPHERY, WORST_PARTITION)

DEFAULT_FOV_DEGREES = 45.0
#: Padding factor on the framing distance so the subject is not flush with the
#: viewport edge.
_FRAMING_MARGIN = 1.35
#: Floor on the framed radius; a single point has no extent to frame.
_MIN_RADIUS = 0.15

_UP = (0.0, 1.0, 0.0)

#: A fixed viewing direction per preset keeps successive shots visually
#: distinct while staying reproducible.
_DIRECTIONS: dict[str, tuple[float, float, float]] = {
    OVERVIEW: (0.0, 0.0, 1.0),
    HUB_CLUSTER: (0.6, 0.35, 0.72),
    ANTIHUB_PERIPHERY: (-0.65, 0.2, 0.73),
    WORST_PARTITION: (0.15, -0.55, 0.82),
}

_CAPTIONS: dict[str, str] = {
    OVERVIEW: "The whole index, projected to three dimensions.",
    HUB_CLUSTER: (
        "Hubs: the points that absorb queries they have no business answering."
    ),
    ANTIHUB_PERIPHERY: "Anti-hubs: vectors no query ever reaches.",
    WORST_PARTITION: "The most oversized IVF partition, in one colour.",
}


@dataclass(frozen=True)
class CameraPreset:
    """A named, reproducible camera transform.

    Attributes:
        name: Preset key, one of :data:`PRESET_NAMES`.
        position: Eye position in the display cube.
        target: Point the camera looks at.
        up: Up vector.
        fov_degrees: Vertical field of view.
        caption: Sentence shown while this preset is on screen.
        available: False when the scene lacks the points this preset frames.
        unavailable_reason: Why the preset is unavailable, or None.
    """

    name: str
    position: tuple[float, float, float]
    target: tuple[float, float, float]
    up: tuple[float, float, float]
    fov_degrees: float
    caption: str
    available: bool
    unavailable_reason: str | None


@dataclass(frozen=True)
class TourStep:
    """One beat of the guided tour.

    Attributes:
        preset: Preset to fly to.
        caption: Caption displayed for this beat.
        transition_seconds: Time spent flying from the previous preset.
        hold_seconds: Time held still once arrived.
    """

    preset: str
    caption: str
    transition_seconds: float
    hold_seconds: float


@dataclass(frozen=True)
class TourTimeline:
    """A declarative, frame-accurate tour script.

    Attributes:
        steps: Beats in order.
        fps: Frames per second the timeline is sampled at.
    """

    steps: tuple[TourStep, ...]
    fps: int

    @property
    def duration_seconds(self) -> float:
        """Total running time of the tour."""
        return sum(s.transition_seconds + s.hold_seconds for s in self.steps)

    @property
    def total_frames(self) -> int:
        """Number of frames :func:`sample_tour` will produce."""
        return sum(
            round(s.transition_seconds * self.fps) + round(s.hold_seconds * self.fps)
            for s in self.steps
        )


@dataclass(frozen=True)
class TourFrame:
    """One sampled frame of the tour.

    Attributes:
        index: Zero-based frame number.
        time_seconds: Timeline position of this frame.
        preset: Preset being flown to or held.
        caption: Caption on screen.
        position: Interpolated eye position.
        target: Interpolated look-at point.
        holding: True when the camera is still rather than moving.
    """

    index: int
    time_seconds: float
    preset: str
    caption: str
    position: tuple[float, float, float]
    target: tuple[float, float, float]
    holding: bool


def _frame_points(
    points: NDArray[np.float32],
    direction: tuple[float, float, float],
    *,
    fov_degrees: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Place a camera so ``points`` fill the frame from ``direction``."""
    centre = points.mean(axis=0, dtype=np.float64)
    delta = points.astype(np.float64) - centre
    squared = np.einsum("ij,ij->i", delta, delta)
    radius = max(_MIN_RADIUS, float(np.sqrt(max(0.0, float(squared.max())))))

    half_fov = math.radians(fov_degrees) * 0.5
    distance = (radius / math.tan(half_fov)) * _FRAMING_MARGIN

    unit = np.asarray(direction, dtype=np.float64)
    norm = float(np.sqrt(float(unit @ unit)))
    unit = unit / norm if norm > 0.0 else np.array([0.0, 0.0, 1.0])

    eye = centre + unit * distance
    return (
        (float(eye[0]), float(eye[1]), float(eye[2])),
        (float(centre[0]), float(centre[1]), float(centre[2])),
    )


def _unavailable(name: str, reason: str) -> CameraPreset:
    return CameraPreset(
        name=name,
        position=(0.0, 0.0, 3.2),
        target=(0.0, 0.0, 0.0),
        up=_UP,
        fov_degrees=DEFAULT_FOV_DEGREES,
        caption=_CAPTIONS[name],
        available=False,
        unavailable_reason=reason,
    )


def _preset_for(
    name: str,
    points: NDArray[np.float32],
    *,
    fov_degrees: float,
    empty_reason: str,
) -> CameraPreset:
    if points.shape[0] == 0:
        return _unavailable(name, empty_reason)
    position, target = _frame_points(points, _DIRECTIONS[name], fov_degrees=fov_degrees)
    return CameraPreset(
        name=name,
        position=position,
        target=target,
        up=_UP,
        fov_degrees=fov_degrees,
        caption=_CAPTIONS[name],
        available=True,
        unavailable_reason=None,
    )


def worst_partition_id(scene: ScenePayload) -> int | None:
    """Identify the partition holding the most points in the scene.

    Args:
        scene: Scene carrying a ``partition_id`` buffer.

    Returns:
        The partition id with the highest count, lowest id winning a tie, or
        None when the scene has no partition data.
    """
    if scene.partition_id is None or scene.partition_id.shape[0] == 0:
        return None
    values, counts = np.unique(scene.partition_id, return_counts=True)
    best = int(np.argmax(counts))
    return int(values[best])


def derive_presets(
    scene: ScenePayload,
    *,
    fov_degrees: float = DEFAULT_FOV_DEGREES,
) -> dict[str, CameraPreset]:
    """Derive every camera preset from the scene's own contents.

    Args:
        scene: Scene to aim at.
        fov_degrees: Vertical field of view for all presets.

    Returns:
        Mapping from preset name to :class:`CameraPreset`. Presets whose
        subject is absent are returned unavailable with a reason rather than
        omitted, so the UI can grey them out and say why.
    """
    positions = scene.positions

    presets: dict[str, CameraPreset] = {
        OVERVIEW: _preset_for(
            OVERVIEW,
            positions,
            fov_degrees=fov_degrees,
            empty_reason="the scene contains no points",
        ),
        HUB_CLUSTER: _preset_for(
            HUB_CLUSTER,
            positions[scene.classes == PointClass.HUB.value],
            fov_degrees=fov_degrees,
            empty_reason="no hubs were found in this scene",
        ),
        ANTIHUB_PERIPHERY: _preset_for(
            ANTIHUB_PERIPHERY,
            positions[scene.classes == PointClass.ANTIHUB.value],
            fov_degrees=fov_degrees,
            empty_reason="no anti-hubs were found in this scene",
        ),
    }

    worst = worst_partition_id(scene)
    if worst is None or scene.partition_id is None:
        presets[WORST_PARTITION] = _unavailable(
            WORST_PARTITION,
            "partition data is UNAVAILABLE for this target",
        )
    else:
        presets[WORST_PARTITION] = _preset_for(
            WORST_PARTITION,
            positions[scene.partition_id == worst],
            fov_degrees=fov_degrees,
            empty_reason="the worst partition holds no points in this scene",
        )

    return presets


def build_tour(
    presets: dict[str, CameraPreset],
    *,
    fps: int = 30,
    transition_seconds: float = 1.6,
    hold_seconds: float = 2.4,
) -> TourTimeline:
    """Script a tour across the presets that are actually available.

    Args:
        presets: Presets from :func:`derive_presets`.
        fps: Sampling rate for :func:`sample_tour`.
        transition_seconds: Fly time into each beat.
        hold_seconds: Still time on each beat.

    Returns:
        A :class:`TourTimeline` covering the available presets in narrative
        order: the whole index, then each finding.

    Raises:
        ValueError: If ``fps`` is below one or no preset is available.
    """
    if fps < 1:
        msg = "fps must be >= 1"
        raise ValueError(msg)

    steps = tuple(
        TourStep(
            preset=name,
            caption=presets[name].caption,
            # The opening shot does not fly in from anywhere.
            transition_seconds=0.0 if index == 0 else transition_seconds,
            hold_seconds=hold_seconds,
        )
        for index, name in enumerate(
            n for n in PRESET_NAMES if n in presets and presets[n].available
        )
    )
    if not steps:
        msg = "no preset is available for this scene; cannot script a tour"
        raise ValueError(msg)

    return TourTimeline(steps=steps, fps=fps)


def _lerp(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    t: float,
) -> tuple[float, float, float]:
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def _smoothstep(t: float) -> float:
    """Ease-in-out with zero derivative at both ends."""
    return t * t * (3.0 - 2.0 * t)


def sample_tour(
    timeline: TourTimeline,
    presets: dict[str, CameraPreset],
) -> tuple[TourFrame, ...]:
    """Expand a timeline into the exact frames a recorder should capture.

    Frames are a pure function of the timeline and the presets: no wall clock,
    no animation loop, no device timing. Two runs produce identical output,
    which is the property the README capture depends on.

    Args:
        timeline: Script to sample.
        presets: Presets referenced by the script.

    Returns:
        One :class:`TourFrame` per frame, in order.

    Raises:
        KeyError: If the timeline references a preset that was not supplied.
    """
    frames: list[TourFrame] = []
    frame_index = 0
    previous = presets[timeline.steps[0].preset]

    for step in timeline.steps:
        target_preset = presets[step.preset]
        transition_frames = round(step.transition_seconds * timeline.fps)
        hold_frames = round(step.hold_seconds * timeline.fps)

        for i in range(transition_frames):
            t = _smoothstep((i + 1) / float(transition_frames))
            frames.append(
                TourFrame(
                    index=frame_index,
                    time_seconds=frame_index / float(timeline.fps),
                    preset=step.preset,
                    caption=step.caption,
                    position=_lerp(previous.position, target_preset.position, t),
                    target=_lerp(previous.target, target_preset.target, t),
                    holding=False,
                )
            )
            frame_index += 1

        for _ in range(hold_frames):
            frames.append(
                TourFrame(
                    index=frame_index,
                    time_seconds=frame_index / float(timeline.fps),
                    preset=step.preset,
                    caption=step.caption,
                    position=target_preset.position,
                    target=target_preset.target,
                    holding=True,
                )
            )
            frame_index += 1

        previous = target_preset

    return tuple(frames)
