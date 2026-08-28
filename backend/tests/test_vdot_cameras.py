from app.vdot_cameras import (
    _extract_image_url,
    _extract_lat_lon,
    _extract_name,
    _is_active,
    _iter_entries,
    fetch_vdot_cameras,
)


def real_feature(**overrides):
    """A GeoJSON Feature shaped like VDOT's actual response (confirmed via a
    real Railway deployment log, not guessed)."""
    feature = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-77.3055, 38.84519]},
        "properties": {
            "id": "3958",
            "name": "0i6a7bfbs60yq2lbgivq0b8xk3scij3c",  # opaque stream token, not a name
            "description": "University Drive and Sager Avenue",
            "jurisdiction": "City of Fairfax",
            "image_url": "https://snapshot.vdotcameras.com/thumbs/0i6a7bfbs60yq2lbgivq0b8xk3scij3c.flv.png",
            "https_url": "https://media-sfs7.vdotcameras.com/rtplive/0i6a7bfbs60yq2lbgivq0b8xk3scij3c/playlist.m3u8",
            "active": True,
        },
    }
    feature["properties"].update(overrides)
    return feature


def test_extract_lat_lon_flat_fields():
    assert _extract_lat_lon({"Latitude": 38.9, "Longitude": -77.0}) == (38.9, -77.0)


def test_extract_lat_lon_case_insensitive_short_names():
    assert _extract_lat_lon({"lat": "38.9", "lon": "-77.0"}) == (38.9, -77.0)


def test_extract_lat_lon_nested_geometry_object():
    entry = {"geometry": {"Latitude": 38.9, "Longitude": -77.0}}
    assert _extract_lat_lon(entry) == (38.9, -77.0)


def test_extract_lat_lon_nested_geometry_coordinates():
    entry = {"geometry": {"coordinates": [-77.0, 38.9]}}
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


def test_extract_name_prefers_description_over_name():
    # VDOT's real "name" field is an opaque stream token, not human-readable.
    entry = {"description": "University Drive and Sager Avenue", "name": "0i6a7bfbs60yq2lbgivq0b8xk3scij3c"}
    assert _extract_name(entry, "fallback") == "University Drive and Sager Avenue"


def test_extract_name_falls_back_to_name_when_no_description():
    assert _extract_name({"Name": "I-395 at Duke St"}, "fallback") == "I-395 at Duke St"


def test_extract_name_falls_back():
    assert _extract_name({}, "fallback") == "fallback"


def test_is_active_true_by_default():
    assert _is_active({}) is True


def test_is_active_false_when_explicitly_false():
    assert _is_active({"active": False}) is False


def test_iter_entries_top_level_list():
    assert _iter_entries([{"a": 1}, {"b": 2}]) == [{"a": 1}, {"b": 2}]


def test_iter_entries_wrapped_in_features_key():
    payload = {"features": [{"a": 1}]}
    assert _iter_entries(payload) == [{"a": 1}]


def test_iter_entries_unexpected_shape_returns_empty():
    assert _iter_entries("not a list or dict") == []
    assert _iter_entries({"nothing": "useful"}) == []


def test_iter_entries_flattens_real_geojson_feature_shape():
    flattened = _iter_entries([real_feature()])
    assert len(flattened) == 1
    entry = flattened[0]
    assert entry["lat"] == 38.84519
    assert entry["lon"] == -77.3055
    assert entry["id"] == "3958"
    assert entry["description"] == "University Drive and Sager Avenue"
    assert entry["image_url"].startswith("https://snapshot.vdotcameras.com/")


def test_fetch_vdot_cameras_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr("app.vdot_cameras.settings.vdot_cameras_enabled", False)
    assert fetch_vdot_cameras() == []


def test_fetch_vdot_cameras_real_shape_end_to_end(monkeypatch):
    fake_payload = {
        "type": "FeatureCollection",
        "features": [
            real_feature(id="1", description="Camera A"),  # in DC-metro bbox -> kept
            real_feature(  # outside bbox (Richmond, VA) -> dropped
                id="2", description="Camera B"
            ),
            real_feature(id="3", description="Camera C", active=False),  # inactive -> dropped
        ],
    }
    # Move camera "2" out of the DC-metro bbox by editing its geometry directly.
    fake_payload["features"][1]["geometry"]["coordinates"] = [-77.4, 37.5]

    monkeypatch.setattr("app.vdot_cameras._fetch_raw", lambda: fake_payload)

    cameras = fetch_vdot_cameras()
    assert len(cameras) == 1
    assert cameras[0]["id"] == "vdot-1"
    assert "Camera A" in cameras[0]["name"]
    assert "City of Fairfax" in cameras[0]["name"]
    assert cameras[0]["snapshot_url"].startswith("https://snapshot.vdotcameras.com/")
    assert cameras[0]["source"] == "vdot_511"


def test_fetch_vdot_cameras_network_failure_returns_empty(monkeypatch):
    def boom():
        raise OSError("network unreachable")

    monkeypatch.setattr("app.vdot_cameras._fetch_raw", boom)
    assert fetch_vdot_cameras() == []
