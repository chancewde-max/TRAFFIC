"""Snaps each camera to the nearest real street, from OpenStreetMap data via
the public Overpass API, so simulated (and eventually detected) vehicles can
move along actual road geometry instead of a straight synthetic line.

Best-effort and stdlib-only (no new dependency): a single batched query
covers every camera in one request. Any failure -- network, timeout,
malformed response -- returns an empty mapping rather than raising, so
callers fall back to the existing radial motion per camera exactly as if no
road were found for it.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from .road_geometry import LatLon, nearest_arc_length_m

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Road types that actually carry car traffic -- excludes footways, cycleways,
# steps, pedestrian plazas, etc. so vehicles don't end up snapped to a
# sidewalk.
DRIVABLE_HIGHWAY_TYPES = (
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "living_street",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
    "tertiary_link",
)


def _build_query(cameras: list, radius_m: float, overpass_timeout_s: int) -> str:
    highway_filter = "^(" + "|".join(DRIVABLE_HIGHWAY_TYPES) + ")$"
    clauses = "\n  ".join(
        f'way(around:{radius_m},{c.lat},{c.lon})[highway~"{highway_filter}"];' for c in cameras
    )
    return f"[out:json][timeout:{overpass_timeout_s}];\n(\n  {clauses}\n);\nout geom;"


def _query_overpass(query: str, timeout: float) -> list[dict]:
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(OVERPASS_URL, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("elements", [])


def fetch_roads_near_cameras(
    cameras: list, radius_m: float = 150.0, timeout: float = 30.0
) -> dict[str, list[LatLon]]:
    """Returns {camera_id: road_polyline} for cameras where a nearby drivable
    road was found. Cameras with no match (or if the fetch fails entirely)
    are simply absent from the result."""

    if not cameras:
        return {}

    query = _build_query(cameras, radius_m, overpass_timeout_s=max(5, int(timeout) - 5))

    try:
        elements = _query_overpass(query, timeout)
    except Exception:
        logger.warning("Overpass road fetch failed; all cameras fall back to radial motion", exc_info=True)
        return {}

    ways: list[list[LatLon]] = []
    for el in elements:
        if el.get("type") != "way":
            continue
        geometry = el.get("geometry") or []
        points = [(pt["lat"], pt["lon"]) for pt in geometry if pt and "lat" in pt and "lon" in pt]
        if len(points) >= 2:
            ways.append(points)

    result: dict[str, list[LatLon]] = {}
    for camera in cameras:
        best_dist = float("inf")
        best_points: list[LatLon] | None = None
        for points in ways:
            dist, _arc = nearest_arc_length_m(points, camera.lat, camera.lon)
            if dist < best_dist:
                best_dist = dist
                best_points = points
        if best_points is not None and best_dist <= radius_m:
            result[camera.id] = best_points

    logger.info(
        "Road snapping: matched %d/%d cameras to a real road (%d candidate ways fetched)",
        len(result),
        len(cameras),
        len(ways),
    )
    return result
