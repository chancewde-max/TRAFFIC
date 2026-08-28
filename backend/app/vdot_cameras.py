"""Fetches Virginia's public VDOT 511 camera map data (locations + snapshot
image URLs) for the DC metro area.

VDOT makes 511 traffic camera *video* available to third parties, but only
through a subscription agreement with their contractor Iteris
(511_videosubscription@iteris.com) -- not something this app can wire up on
its own. The map endpoint here is different: it's what VDOT's own public
511 map calls to render camera pins with snapshot thumbnails, and doesn't
require that agreement. Its schema isn't publicly documented, so parsing is
defensive -- this returns an empty list on any failure or unrecognized
shape rather than raising, same as every other best-effort integration in
this codebase (DDOT MQTT, Overpass road snapping).
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)


def _get(obj: dict, *candidates: str) -> Any:
    """Case-insensitive lookup of the first matching key in obj."""
    lower_map = {k.lower(): k for k in obj.keys()}
    for cand in candidates:
        real_key = lower_map.get(cand.lower())
        if real_key is not None:
            return obj[real_key]
    return None


def _extract_lat_lon(entry: dict) -> tuple[float, float] | None:
    lat = _get(entry, "latitude", "lat", "y")
    lon = _get(entry, "longitude", "lon", "lng", "x")

    if lat is None or lon is None:
        geom = _get(entry, "geometry", "location", "point")
        if isinstance(geom, dict):
            lat = lat if lat is not None else _get(geom, "latitude", "lat", "y")
            lon = lon if lon is not None else _get(geom, "longitude", "lon", "lng", "x")
        coords = _get(entry, "coordinates")
        if lat is None and isinstance(coords, list) and len(coords) >= 2:
            lon, lat = coords[0], coords[1]

    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def _extract_image_url(entry: dict) -> str | None:
    direct = _get(
        entry,
        "imageurl",
        "image_url",
        "snapshoturl",
        "snapshot_url",
        "thumbnailurl",
        "thumbnail",
        "url",
        "img",
    )
    if isinstance(direct, str) and direct.startswith("http"):
        return direct

    # Some 511-platform schemas nest a list of camera "views", each with its
    # own image url, rather than one url on the camera itself.
    views = _get(entry, "views", "cameraviews", "images")
    if isinstance(views, list):
        for v in views:
            if isinstance(v, dict):
                url = _get(v, "url", "imageurl", "snapshoturl")
                if isinstance(url, str) and url.startswith("http"):
                    return url

    return None


def _extract_name(entry: dict, fallback: str) -> str:
    for key in ("name", "location", "roadway", "description", "title"):
        val = _get(entry, key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return fallback


def _iter_entries(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [e for e in payload if isinstance(e, dict)]
    if isinstance(payload, dict):
        for key in ("features", "cams", "cameras", "results", "data"):
            val = payload.get(key)
            if isinstance(val, list):
                return [e for e in val if isinstance(e, dict)]
    return []


def _fetch_raw() -> Any:
    req = urllib.request.Request(
        settings.vdot_cameras_url,
        headers={
            "User-Agent": "dc-traffic-tracker/1.0 (+https://github.com/chancewde-max/TRAFFIC)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=settings.vdot_cameras_timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_vdot_cameras() -> list[dict]:
    """Returns camera dicts in this app's internal shape (id, name, lat, lon,
    bearing_deg, stream_url, snapshot_url, source), filtered to the DC metro
    bounding box and to entries with a real image URL. Empty list on any
    failure -- callers should treat this as purely additive."""

    if not settings.vdot_cameras_enabled:
        return []

    try:
        payload = _fetch_raw()
    except Exception:
        logger.warning("VDOT camera fetch failed", exc_info=True)
        return []

    entries = _iter_entries(payload)
    if not entries:
        logger.warning(
            "VDOT camera response had an unexpected shape (top-level type: %s); got 0 usable entries",
            type(payload).__name__,
        )
        return []

    cameras: list[dict] = []
    for entry in entries:
        latlon = _extract_lat_lon(entry)
        if latlon is None:
            continue
        lat, lon = latlon
        if not (settings.vdot_bbox_min_lat <= lat <= settings.vdot_bbox_max_lat):
            continue
        if not (settings.vdot_bbox_min_lon <= lon <= settings.vdot_bbox_max_lon):
            continue

        image_url = _extract_image_url(entry)
        if not image_url:
            continue  # no real image available for this one -- skip it

        raw_id = _get(entry, "id", "cameraid", "sourceid", "deviceid")
        cid = f"vdot-{raw_id}" if raw_id is not None else f"vdot-{lat:.5f}-{lon:.5f}"

        cameras.append(
            {
                "id": str(cid),
                "name": _extract_name(entry, f"VDOT camera {raw_id}"),
                "lat": lat,
                "lon": lon,
                # VDOT's map doesn't publish a compass bearing either -- same
                # stable-placeholder approach as the DDOT/seed cameras.
                "bearing_deg": float(hash(str(cid)) % 360),
                "stream_url": None,
                "snapshot_url": image_url,
                "source": "vdot_511",
            }
        )

    logger.info(
        "VDOT cameras: %d in DC-metro bbox with a usable image, out of %d total entries fetched",
        len(cameras),
        len(entries),
    )
    return cameras
