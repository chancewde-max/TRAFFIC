"""Simple anomaly-based incident detection: keeps a small rolling baseline of
vehicle count / average speed per camera in memory, and flags a sample that
deviates sharply from that baseline as an incident (e.g. a sudden speed drop
suggesting a stall/collision, or a sudden count spike suggesting an
event/backup).
"""

from __future__ import annotations

from collections import deque

from ..config import settings

MIN_BASELINE_SAMPLES = 6
BASELINE_WINDOW = 30


class _CameraBaseline:
    __slots__ = ("counts", "speeds")

    def __init__(self) -> None:
        self.counts: deque[int] = deque(maxlen=BASELINE_WINDOW)
        self.speeds: deque[float] = deque(maxlen=BASELINE_WINDOW)


class IncidentDetector:
    def __init__(self) -> None:
        self._baselines: dict[str, _CameraBaseline] = {}

    def observe(
        self, camera_id: str, vehicle_count: int, avg_speed_mps: float | None
    ) -> tuple[str, str, str] | None:
        """Returns (kind, severity, description) if this sample looks like an
        incident, else None. Always updates the rolling baseline."""

        baseline = self._baselines.setdefault(camera_id, _CameraBaseline())
        result = None

        if len(baseline.counts) >= MIN_BASELINE_SAMPLES:
            baseline_count = sum(baseline.counts) / len(baseline.counts)
            if baseline_count > 0 and vehicle_count >= baseline_count * settings.incident_count_spike_ratio and vehicle_count >= settings.congestion_moderate_threshold:
                result = (
                    "count_spike",
                    "major" if vehicle_count >= settings.congestion_heavy_threshold else "minor",
                    f"Vehicle count spiked to {vehicle_count} (baseline ~{baseline_count:.1f})",
                )

        if result is None and avg_speed_mps is not None and len(baseline.speeds) >= MIN_BASELINE_SAMPLES:
            baseline_speed = sum(baseline.speeds) / len(baseline.speeds)
            if baseline_speed > 1.0 and avg_speed_mps <= baseline_speed * (1 - settings.incident_speed_drop_ratio):
                result = (
                    "speed_drop",
                    "major" if avg_speed_mps < baseline_speed * 0.25 else "minor",
                    f"Average speed dropped to {avg_speed_mps:.1f} m/s (baseline ~{baseline_speed:.1f} m/s)",
                )

        baseline.counts.append(vehicle_count)
        if avg_speed_mps is not None:
            baseline.speeds.append(avg_speed_mps)

        return result
