"""Snaps each camera to the nearest real street, from OpenStreetMap data via
the public Overpass API, so simulated (and eventually detected) vehicles can
move along actual road geometry instead of a straight synthetic line.

Best-effort and stdlib-only (no new dependency): queries are chunked (a few
cameras per request) since the public Overpass instance times out on one big
query covering many locations at once. Any failure -- network, timeout,
malformed response -- for a chunk just drops those cameras back to the
existing radial motion; it never raises out of fetch_roads_near_cameras.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from .road_geometry import LatLon, nearest_arc_length_m

logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Cameras per Overpass request. The public instance times out (504) on one
# big query covering ~28 locations with a tag filter; a handful per request
# comes back in a few seconds.
CHUNK_SIZE = 6

# Road types that actually carry car traffic -- excludes footways, cycleways,
# steps, pedestrian plazas, etc. so vehicles don't end up snapped to a
# sidewalk. Filtered client-side (see below) rather than with a server-side
# regex, which is measurably more expensive for Overpass to evaluate.
DRIVABLE_HIGHWAY_TYPES = frozenset(
    {
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
    }
)


def _build_query(cameras: list, radius_m: float, overpass_timeout_s: int) -> str:
    # Cheap presence filter server-side; the specific drivable-type check
    # happens client-side against each way's tags below.
    clauses = "\n  ".join(f"way(around:{radius_m},{c.lat},{c.lon})[highway];" for c in cameras)
    return f"[out:json][timeout:{overpass_timeout_s}];\n(\n  {clauses}\n);\nout tags geom;"


def _query_overpass(query: str, timeout: float) -> list[dict]:
    body = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(
        OVERPASS_URL,
        data=body,
        method="POST",
        headers={
            # Overpass/OSM infrastructure rejects the default
            # "Python-urllib/x.y" User-Agent (HTTP 406) -- they require a
            # descriptive one identifying the application.
            "User-Agent": "dc-traffic-tracker/1.0 (+https://github.com/chancewde-max/TRAFFIC)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("elements", [])


def _parse_drivable_ways(elements: list[dict]) -> list[list[LatLon]]:
    ways: list[list[LatLon]] = []
    for el in elements:
        if el.get("type") != "way":
            continue
        if el.get("tags", {}).get("highway") not in DRIVABLE_HIGHWAY_TYPES:
            continue
        geometry = el.get("geometry") or []
        points = [(pt["lat"], pt["lon"]) for pt in geometry if pt and "lat" in pt and "lon" in pt]
        if len(points) >= 2:
            ways.append(points)
    return ways


def _load_cache(path: str) -> dict[str, list[LatLon]]:
    try:
        with open(path) as f:
            raw = json.load(f)
        return {cid: [(pt[0], pt[1]) for pt in pts] for cid, pts in raw.items()}
    except (FileNotFoundError, json.JSONDecodeError, OSError, KeyError, IndexError, TypeError):
        return {}


def _save_cache(path: str, data: dict[str, list[LatLon]]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump({cid: [list(pt) for pt in pts] for cid, pts in data.items()}, f)
    except OSError:
        logger.warning("Failed to write road cache to %s", path, exc_info=True)


def fetch_roads_near_cameras(
    cameras: list, radius_m: float = 150.0, timeout: float = 30.0, cache_path: str | None = None
) -> dict[str, list[LatLon]]:
    """Returns {camera_id: road_polyline} for cameras where a nearby drivable
    road was found. Cameras with no match (or whose chunk's fetch failed)
    are simply absent from the result.

    When cache_path is given, cameras already matched on a previous run are
    served from disk instead of re-querying Overpass -- this is real road
    geometry that doesn't change, so there's no reason to keep asking a
    shared public API for it on every restart. Only cameras still unmatched
    are (re-)fetched, so a previous rate-limit/timeout isn't permanent.
    """

    if not cameras:
        return {}

    cached = _load_cache(cache_path) if cache_path else {}
    to_fetch = [c for c in cameras if c.id not in cached]

    if not to_fetch:
        logger.info("Road snapping: all %d/%d cameras served from cache", len(cameras), len(cameras))
        return {c.id: cached[c.id] for c in cameras}

    all_ways: list[list[LatLon]] = []
    chunks = [to_fetch[i : i + CHUNK_SIZE] for i in range(0, len(to_fetch), CHUNK_SIZE)]

    for i, chunk in enumerate(chunks):
        if i > 0:
            # Firing chunks back-to-back gets the shared public Overpass
            # instance to rate-limit us (HTTP 429) partway through -- a
            # small gap between requests avoids that.
            time.sleep(2.0)

        query = _build_query(chunk, radius_m, overpass_timeout_s=max(5, int(timeout) - 5))
        try:
            elements = _query_overpass(query, timeout)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                logger.info("Overpass rate-limited a chunk of %d camera(s); backing off and retrying once", len(chunk))
                time.sleep(10.0)
                try:
                    elements = _query_overpass(query, timeout)
                except Exception:
                    logger.warning(
                        "Overpass retry also failed for a chunk of %d camera(s); those fall back to radial motion",
                        len(chunk),
                        exc_info=True,
                    )
                    continue
            else:
                logger.warning(
                    "Overpass road fetch failed for a chunk of %d camera(s); those fall back to radial motion",
                    len(chunk),
                    exc_info=True,
                )
                continue
        except Exception:
            logger.warning(
                "Overpass road fetch failed for a chunk of %d camera(s); those fall back to radial motion",
                len(chunk),
                exc_info=True,
            )
            continue
        all_ways.extend(_parse_drivable_ways(elements))

    newly_matched: dict[str, list[LatLon]] = {}
    for camera in to_fetch:
        best_dist = float("inf")
        best_points: list[LatLon] | None = None
        for points in all_ways:
            dist, _arc = nearest_arc_length_m(points, camera.lat, camera.lon)
            if dist < best_dist:
                best_dist = dist
                best_points = points
        if best_points is not None and best_dist <= radius_m:
            newly_matched[camera.id] = best_points

    if cache_path and newly_matched:
        _save_cache(cache_path, {**cached, **newly_matched})

    result = {**{cid: pts for cid, pts in cached.items() if cid in {c.id for c in cameras}}, **newly_matched}

    logger.info(
        "Road snapping: matched %d/%d cameras to a real road (%d cached, %d newly fetched, %d candidate ways queried)",
        len(result),
        len(cameras),
        len(cached),
        len(newly_matched),
        len(all_ways),
    )
    return result
