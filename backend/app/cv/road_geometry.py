"""Pure geometry helpers for moving a point along a real road polyline.

No network calls here -- see road_snap.py for fetching the actual polylines
from OpenStreetMap. Kept separate so this arc-length math is trivially unit
testable without a live network dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .geo_projection import DEG_PER_METER_LAT, haversine_m, meters_per_degree_lon

LatLon = tuple[float, float]


@dataclass
class RoadPoint:
    lat: float
    lon: float
    heading_deg: float


def cumulative_lengths_m(points: list[LatLon]) -> list[float]:
    """Cumulative distance (meters) at each point, starting at 0.0."""

    cum = [0.0]
    for (lat1, lon1), (lat2, lon2) in zip(points, points[1:]):
        cum.append(cum[-1] + haversine_m(lat1, lon1, lat2, lon2))
    return cum


def polyline_length_m(points: list[LatLon]) -> float:
    if len(points) < 2:
        return 0.0
    return cumulative_lengths_m(points)[-1]


def offset_point(lat: float, lon: float, heading_deg: float, offset_m: float) -> LatLon:
    """A point shifted `offset_m` meters to the right of `heading_deg` (compass
    bearing, degrees clockwise from north). Used to place same-direction
    traffic on its own side of a road's centerline instead of every vehicle
    -- both directions included -- sharing one line down the middle."""

    perp_rad = math.radians(heading_deg + 90.0)
    dx_east = offset_m * math.sin(perp_rad)
    dy_north = offset_m * math.cos(perp_rad)
    dlat = dy_north * DEG_PER_METER_LAT
    dlon = dx_east / meters_per_degree_lon(lat)
    return lat + dlat, lon + dlon


def _bearing_deg(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def point_at_distance(points: list[LatLon], distance_m: float) -> RoadPoint:
    """The point (and direction of travel) `distance_m` along the polyline,
    clamped to [0, length]."""

    if len(points) < 2:
        lat, lon = points[0] if points else (0.0, 0.0)
        return RoadPoint(lat=lat, lon=lon, heading_deg=0.0)

    cum = cumulative_lengths_m(points)
    total = cum[-1]
    distance_m = max(0.0, min(total, distance_m))

    for i in range(len(points) - 1):
        seg_start, seg_end = cum[i], cum[i + 1]
        if distance_m <= seg_end or i == len(points) - 2:
            seg_len = seg_end - seg_start
            t = 0.0 if seg_len <= 0 else (distance_m - seg_start) / seg_len
            (lat1, lon1), (lat2, lon2) = points[i], points[i + 1]
            lat = lat1 + (lat2 - lat1) * t
            lon = lon1 + (lon2 - lon1) * t
            heading = _bearing_deg(points[i], points[i + 1])
            return RoadPoint(lat=lat, lon=lon, heading_deg=heading)

    lat, lon = points[-1]
    return RoadPoint(lat=lat, lon=lon, heading_deg=0.0)


def nearest_arc_length_m(points: list[LatLon], lat: float, lon: float) -> tuple[float, float]:
    """Returns (distance_from_polyline_m, arc_length_of_nearest_point_m) --
    the closest a camera (or any point) gets to this road, and where along
    the road that closest approach is. Uses a flat local-meters approximation
    per segment, which is accurate enough at the ~100m scale we snap over."""

    if len(points) < 2:
        if not points:
            return float("inf"), 0.0
        return haversine_m(lat, lon, points[0][0], points[0][1]), 0.0

    m_per_deg_lon = meters_per_degree_lon(lat)
    px = lon * m_per_deg_lon
    py = lat / DEG_PER_METER_LAT

    cum = cumulative_lengths_m(points)
    best_dist = float("inf")
    best_arc = 0.0

    for i in range(len(points) - 1):
        (lat1, lon1), (lat2, lon2) = points[i], points[i + 1]
        ax, ay = lon1 * m_per_deg_lon, lat1 / DEG_PER_METER_LAT
        bx, by = lon2 * m_per_deg_lon, lat2 / DEG_PER_METER_LAT

        dx, dy = bx - ax, by - ay
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq <= 1e-9:
            t = 0.0
        else:
            t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
            t = max(0.0, min(1.0, t))

        cx, cy = ax + dx * t, ay + dy * t
        dist = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5

        if dist < best_dist:
            best_dist = dist
            seg_len = cum[i + 1] - cum[i]
            best_arc = cum[i] + seg_len * t

    return best_dist, best_arc
