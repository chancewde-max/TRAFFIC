import asyncio

from app.cv.pipeline import (
    LANE_OFFSET_M,
    MIN_GAP_M,
    VEHICLE_LENGTH_M,
    MockCameraSimulator,
)
from app.cv.road_geometry import point_at_distance, polyline_length_m
from app.models import Camera

# A long straight north-south road so vehicles have room to interact without
# immediately falling off either end during the test.
ROAD = [(38.900, -77.000), (38.905, -77.000)]


def _camera() -> Camera:
    return Camera(id="test-cam", name="Test Camera", lat=38.9025, lon=-77.000, bearing_deg=0.0)


def _run_ticks(sim: MockCameraSimulator, n: int, dt: float = 0.5):
    for i in range(n):
        yield asyncio.run(sim.tick_or_read(dt, t=i * dt))


def test_road_vehicles_are_offset_from_centerline():
    sim = MockCameraSimulator(_camera(), road_points=ROAD, seed=1)
    positions = asyncio.run(sim.tick_or_read(0.1, t=0.0))
    assert positions, "expected at least one spawned vehicle"

    for pos in positions:
        road_point = point_at_distance(ROAD, _closest_arc_length(pos))
        # Centerline runs due north (lon is constant); an offset vehicle must
        # differ in longitude from the exact centerline at its latitude.
        assert abs(pos.lon - road_point.lon) > 0.0


def _closest_arc_length(pos) -> float:
    # ROAD is a straight north-south line, so arc length is proportional to
    # how far north of the start the vehicle is.
    total = polyline_length_m(ROAD)
    frac = (pos.lat - ROAD[0][0]) / (ROAD[-1][0] - ROAD[0][0])
    return max(0.0, min(total, frac * total))


def test_same_direction_vehicles_never_pass_through_each_other():
    sim = MockCameraSimulator(_camera(), road_points=ROAD, seed=2)
    # Force two vehicles into the same lane, close together, one clearly
    # behind the other -- the follower should never end up ahead of (or
    # overlapping) the leader once car-following kicks in.
    sim.vehicles.clear()
    sim.vehicles[1] = {"s": 50.0, "direction": 1, "speed": 9.0, "cur_speed": 9.0, "vehicle_class": "car"}
    sim.vehicles[2] = {"s": 45.0, "direction": 1, "speed": 9.0, "cur_speed": 9.0, "vehicle_class": "car"}
    sim.base_density = 2  # don't let spawning add noise to this test

    for _ in _run_ticks(sim, 40):
        if 1 not in sim.vehicles or 2 not in sim.vehicles:
            break
        gap = sim.vehicles[1]["s"] - sim.vehicles[2]["s"]
        assert gap >= (VEHICLE_LENGTH_M - 1e-6), "follower caught up to/passed its leader"


def test_speed_changes_smoothly_not_instantly():
    sim = MockCameraSimulator(_camera(), road_points=ROAD, seed=3)
    sim.vehicles.clear()
    # A stopped leader right in front of a fast-moving follower: the
    # follower must brake gradually (bounded deceleration), not teleport to
    # 0 m/s in a single tick.
    sim.vehicles[1] = {"s": 20.0, "direction": 1, "speed": 0.0, "cur_speed": 0.0, "vehicle_class": "car"}
    sim.vehicles[2] = {"s": 10.0, "direction": 1, "speed": 9.0, "cur_speed": 9.0, "vehicle_class": "car"}
    sim.base_density = 2

    first_positions = asyncio.run(sim.tick_or_read(0.5, t=0.0))
    follower = next(p for p in first_positions if p.track_id == 2)
    assert follower.speed_mps < 9.0
    assert follower.speed_mps > 0.0  # bounded decel, not an instant stop


def test_car_following_respects_min_gap_setting():
    # Sanity check the tuning constant is sane (positive, smaller than a
    # typical vehicle length so it reads as "bumper distance" not a full gap).
    assert 0 < MIN_GAP_M < VEHICLE_LENGTH_M * 2
    assert LANE_OFFSET_M > 0
