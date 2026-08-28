from __future__ import annotations

from ..config import settings
from ..schemas import VehiclePosition


def compute_level(vehicle_count: int) -> str:
    if vehicle_count >= settings.congestion_heavy_threshold:
        return "heavy"
    if vehicle_count >= settings.congestion_moderate_threshold:
        return "moderate"
    if vehicle_count >= settings.congestion_light_threshold:
        return "light"
    return "free"


def summarize(positions: list[VehiclePosition]) -> tuple[int, float | None, str]:
    count = len(positions)
    speeds = [p.speed_mps for p in positions if p.speed_mps is not None]
    avg_speed = sum(speeds) / len(speeds) if speeds else None
    level = compute_level(count)
    return count, avg_speed, level
