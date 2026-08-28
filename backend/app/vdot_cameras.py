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


def _flatten_feature(entry: dict) -> dict:
    """The real response is standard GeoJSON Features: {type, geometry:
    {type, coordinates: [lon, lat]}, properties: {...all the useful
    fields...}}. Flattens that into one dict so the extraction helpers below
    can do simple key lookups regardless of whether a given entry turns out
    to be a plain flat object instead (defensive: keeps working either way)."""

    flat: dict[str, Any] = {}
    props = entry.get("properties")
    if isinstance(props, dict):
        flat.update(props)
    flat.update({k: v for k, v in entry.items() if k not in ("properties", "geometry")})

    geometry = entry.get("geometry")
    if isinstance(geometry, dict):
        coords = geometry.get("coordinates")
        if isinstance(coords, list) and len(coords) >= 2:
            flat.setdefault("lon", coords[0])
            flat.setdefault("lat", coords[1])

    return flat


def _extract_lat_lon(entry: dict) -> tuple[float, float] | None:
    lat = _get(entry, "latitude", "lat", "y")
    lon = _get(entry, "longitude", "lon", "lng", "x")

    if lat is None or lon is None:
        geom = _get(entry, "geometry", "location", "point")
        if isinstance(geom, dict):
            lat = lat if lat is not None else _get(geom, "latitude", "lat", "y")
            lon = lon if lon is not None else _get(geom, "longitude", "lon", "lng", "x")
            coords = _get(geom, "coordinates")
            if lat is None and isinstance(coords, list) and len(coords) >= 2:
                lon, lat = coords[0], coords[1]

    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def _extract_image_url(entry: dict) -> str | None:
    direct = _get(
        entry,
        "image_url",
        "imageurl",
        "snapshot_url",
        "snapshoturl",
        "thumbnailurl",
        "thumbnail",
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
    # Confirmed on the real feed: "description" is the human-readable
    # location ("University Drive and Sager Avenue"); "name" is actually an
    # opaque per-camera stream token, not a name -- checked last, only as a
    # fallback in case a different shape genuinely uses "name" for a name.
    for key in ("description", "location", "roadway", "title", "name"):
        val = _get(entry, key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return fallback


def _is_active(entry: dict) -> bool:
    val = _get(entry, "active", "isactive", "enabled")
    return val is not False  # missing/None/True all count as active


def _iter_entries(payload: Any) -> list[dict]:
    raw: list[dict] = []
    if isinstance(payload, list):
        raw = [e for e in payload if isinstance(e, dict)]
    elif isinstance(payload, dict):
        for key in ("features", "cams", "cameras", "results", "data"):
            val = payload.get(key)
            if isinstance(val, list):
                raw = [e for e in val if isinstance(e, dict)]
                break
    return [_flatten_feature(e) for e in raw]


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
        if isinstance(payload, (dict, list)):
            sample = payload[0] if isinstance(payload, list) and payload else payload
            logger.warning("VDOT camera raw payload sample (for schema diagnosis): %s", json.dumps(sample)[:2000])
        return []

    had_latlon = 0
    in_bbox = 0
    cameras: list[dict] = []
    for entry in entries:
        if not _is_active(entry):
            continue

        latlon = _extract_lat_lon(entry)
        if latlon is None:
            continue
        had_latlon += 1
        lat, lon = latlon
        if not (settings.vdot_bbox_min_lat <= lat <= settings.vdot_bbox_max_lat):
            continue
        if not (settings.vdot_bbox_min_lon <= lon <= settings.vdot_bbox_max_lon):
            continue
        in_bbox += 1

        image_url = _extract_image_url(entry)
        if not image_url:
            continue  # no real image available for this one -- skip it

        raw_id = _get(entry, "id", "cameraid", "sourceid", "deviceid")
        cid = f"vdot-{raw_id}" if raw_id is not None else f"vdot-{lat:.5f}-{lon:.5f}"

        name = _extract_name(entry, f"VDOT camera {raw_id}")
        jurisdiction = _get(entry, "jurisdiction")
        if isinstance(jurisdiction, str) and jurisdiction.strip():
            name = f"{name} ({jurisdiction.strip()})"

        cameras.append(
            {
                "id": str(cid),
                "name": name,
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
        "VDOT cameras: %d in DC-metro bbox with a usable image, out of %d total entries "
        "(%d had parseable lat/lon, %d of those were in-bbox)",
        len(cameras),
        len(entries),
        had_latlon,
        in_bbox,
    )
    if not cameras:
        logger.warning("VDOT camera raw entry sample (for schema diagnosis): %s", json.dumps(entries[0])[:2000])
    return cameras
