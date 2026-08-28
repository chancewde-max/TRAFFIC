import json

from app.cv.road_snap import _load_cache, _save_cache, fetch_roads_near_cameras
from app.models import Camera


def make_camera(cid, lat, lon):
    return Camera(id=cid, name=cid, lat=lat, lon=lon, bearing_deg=0.0)


def test_save_and_load_cache_roundtrip(tmp_path):
    path = str(tmp_path / "roads.json")
    data = {"seed-001": [(38.9, -77.0), (38.901, -77.001)]}
    _save_cache(path, data)
    loaded = _load_cache(path)
    assert loaded == data


def test_load_cache_missing_file_returns_empty(tmp_path):
    assert _load_cache(str(tmp_path / "does_not_exist.json")) == {}


def test_load_cache_corrupt_file_returns_empty(tmp_path):
    path = tmp_path / "roads.json"
    path.write_text("not valid json{{{")
    assert _load_cache(str(path)) == {}


def test_fully_cached_cameras_skip_network_entirely(tmp_path, monkeypatch):
    path = str(tmp_path / "roads.json")
    cached_road = [(38.9, -77.0), (38.901, -77.001)]
    _save_cache(path, {"seed-001": cached_road})

    def boom(*args, **kwargs):
        raise AssertionError("should not hit the network when fully cached")

    monkeypatch.setattr("app.cv.road_snap._query_overpass", boom)

    result = fetch_roads_near_cameras([make_camera("seed-001", 38.9, -77.0)], cache_path=path)
    assert result == {"seed-001": cached_road}


def test_cache_is_updated_with_newly_fetched_cameras(tmp_path, monkeypatch):
    path = str(tmp_path / "roads.json")

    def fake_query(query, timeout):
        return [
            {
                "type": "way",
                "tags": {"highway": "residential"},
                "geometry": [{"lat": 38.9, "lon": -77.0}, {"lat": 38.901, "lon": -77.0}],
            }
        ]

    monkeypatch.setattr("app.cv.road_snap._query_overpass", fake_query)

    cameras = [make_camera("seed-001", 38.9005, -77.0)]
    result = fetch_roads_near_cameras(cameras, cache_path=path)
    assert "seed-001" in result

    on_disk = json.loads((tmp_path / "roads.json").read_text())
    assert "seed-001" in on_disk
