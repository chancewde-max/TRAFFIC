from app.vdot_cameras import _extract_image_url, _extract_lat_lon, _extract_name, _iter_entries, fetch_vdot_cameras


def test_extract_lat_lon_flat_fields():
    assert _extract_lat_lon({"Latitude": 38.9, "Longitude": -77.0}) == (38.9, -77.0)


def test_extract_lat_lon_case_insensitive_short_names():
    assert _extract_lat_lon({"lat": "38.9", "lon": "-77.0"}) == (38.9, -77.0)


def test_extract_lat_lon_nested_geometry():
    entry = {"geometry": {"Latitude": 38.9, "Longitude": -77.0}}
    assert _extract_lat_lon(entry) == (38.9, -77.0)


def test_extract_lat_lon_coordinates_array_lon_lat_order():
    entry = {"coordinates": [-77.0, 38.9]}
    assert _extract_lat_lon(entry) == (38.9, -77.0)


def test_extract_lat_lon_missing_returns_none():
    assert _extract_lat_lon({"name": "no coords here"}) is None


def test_extract_image_url_direct_field():
    entry = {"ImageUrl": "https://example.com/cam1.jpg"}
    assert _extract_image_url(entry) == "https://example.com/cam1.jpg"


def test_extract_image_url_nested_views():
    entry = {"Views": [{"Url": "https://example.com/cam2.jpg"}]}
    assert _extract_image_url(entry) == "https://example.com/cam2.jpg"


def test_extract_image_url_non_http_value_ignored():
    entry = {"url": "not-a-url"}
    assert _extract_image_url(entry) is None


def test_extract_name_prefers_name_field():
    assert _extract_name({"Name": "I-395 at Duke St"}, "fallback") == "I-395 at Duke St"


def test_extract_name_falls_back():
    assert _extract_name({}, "fallback") == "fallback"


def test_iter_entries_top_level_list():
    assert _iter_entries([{"a": 1}, {"b": 2}]) == [{"a": 1}, {"b": 2}]


def test_iter_entries_wrapped_in_features_key():
    payload = {"features": [{"a": 1}]}
    assert _iter_entries(payload) == [{"a": 1}]


def test_iter_entries_unexpected_shape_returns_empty():
    assert _iter_entries("not a list or dict") == []
    assert _iter_entries({"nothing": "useful"}) == []


def test_fetch_vdot_cameras_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr("app.vdot_cameras.settings.vdot_cameras_enabled", False)
    assert fetch_vdot_cameras() == []


def test_fetch_vdot_cameras_filters_bbox_and_requires_image(monkeypatch):
    fake_payload = [
        # Inside DC-metro bbox, has an image -> kept
        {"Id": 1, "Latitude": 38.9, "Longitude": -77.0, "Name": "Camera A", "ImageUrl": "https://x/a.jpg"},
        # Outside bbox (Richmond, VA) -> dropped
        {"Id": 2, "Latitude": 37.5, "Longitude": -77.4, "Name": "Camera B", "ImageUrl": "https://x/b.jpg"},
        # Inside bbox but no image -> dropped
        {"Id": 3, "Latitude": 38.85, "Longitude": -77.1, "Name": "Camera C"},
    ]
    monkeypatch.setattr("app.vdot_cameras._fetch_raw", lambda: fake_payload)

    cameras = fetch_vdot_cameras()
    assert len(cameras) == 1
    assert cameras[0]["id"] == "vdot-1"
    assert cameras[0]["snapshot_url"] == "https://x/a.jpg"
    assert cameras[0]["source"] == "vdot_511"


def test_fetch_vdot_cameras_network_failure_returns_empty(monkeypatch):
    def boom():
        raise OSError("network unreachable")

    monkeypatch.setattr("app.vdot_cameras._fetch_raw", boom)
    assert fetch_vdot_cameras() == []
