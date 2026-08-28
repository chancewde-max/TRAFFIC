from app.schemas import VehiclePosition
from app.services.congestion import compute_level, summarize


def vp(speed):
    return VehiclePosition(
        camera_id="seed-001", track_id=1, lat=0.0, lon=0.0, heading_deg=0.0, speed_mps=speed
    )


def test_compute_level_thresholds():
    assert compute_level(0) == "free"
    assert compute_level(3) == "free"
    assert compute_level(4) == "light"
    assert compute_level(8) == "light"
    assert compute_level(9) == "moderate"
    assert compute_level(15) == "moderate"
    assert compute_level(16) == "heavy"
    assert compute_level(100) == "heavy"


def test_summarize_empty_list():
    count, avg_speed, level = summarize([])
    assert count == 0
    assert avg_speed is None
    assert level == "free"


def test_summarize_averages_known_speeds_and_ignores_missing():
    positions = [vp(2.0), vp(4.0), vp(None)]
    count, avg_speed, level = summarize(positions)
    assert count == 3
    assert avg_speed == 3.0
    assert level == "free"
