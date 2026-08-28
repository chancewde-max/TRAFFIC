from app.cv.geo_projection import haversine_m
from app.cv.road_geometry import (
    nearest_arc_length_m,
    offset_point,
    point_at_distance,
    polyline_length_m,
)

# A short straight "road" running north-south near DC, ~111m total.
ROAD = [(38.900, -77.000), (38.9005, -77.000), (38.901, -77.000)]


def test_polyline_length_matches_sum_of_segments():
    expected = haversine_m(*ROAD[0], *ROAD[1]) + haversine_m(*ROAD[1], *ROAD[2])
    assert abs(polyline_length_m(ROAD) - expected) < 1e-6


def test_polyline_length_zero_for_single_point():
    assert polyline_length_m([(38.9, -77.0)]) == 0.0


def test_point_at_distance_zero_is_start():
    p = point_at_distance(ROAD, 0.0)
    assert abs(p.lat - ROAD[0][0]) < 1e-9
    assert abs(p.lon - ROAD[0][1]) < 1e-9


def test_point_at_distance_full_length_is_end():
    total = polyline_length_m(ROAD)
    p = point_at_distance(ROAD, total)
    assert abs(p.lat - ROAD[-1][0]) < 1e-6
    assert abs(p.lon - ROAD[-1][1]) < 1e-6


def test_point_at_distance_clamps_beyond_ends():
    total = polyline_length_m(ROAD)
    p_over = point_at_distance(ROAD, total + 500)
    p_end = point_at_distance(ROAD, total)
    assert abs(p_over.lat - p_end.lat) < 1e-9
    p_under = point_at_distance(ROAD, -500)
    p_start = point_at_distance(ROAD, 0.0)
    assert abs(p_under.lat - p_start.lat) < 1e-9


def test_point_at_distance_heading_points_north():
    p = point_at_distance(ROAD, 10.0)
    assert abs(p.heading_deg - 0.0) < 1.0 or abs(p.heading_deg - 360.0) < 1.0


def test_nearest_arc_length_on_the_line_is_near_zero_distance():
    # A point essentially on the road, partway along it.
    dist, arc = nearest_arc_length_m(ROAD, 38.9005, -77.000)
    assert dist < 1.0
    expected_arc = haversine_m(*ROAD[0], *ROAD[1])
    assert abs(arc - expected_arc) < 1.0


def test_nearest_arc_length_off_the_line_has_larger_distance():
    dist, _ = nearest_arc_length_m(ROAD, 38.9005, -76.999)
    assert dist > 50.0


def test_nearest_arc_length_empty_polyline_is_infinite():
    dist, arc = nearest_arc_length_m([], 38.9, -77.0)
    assert dist == float("inf")
    assert arc == 0.0


def test_offset_point_facing_north_shifts_right_to_the_east():
    lat, lon = offset_point(38.9, -77.0, 0.0, 10.0)
    assert abs(lat - 38.9) < 1e-9  # due-north heading -> right offset has no north/south component
    assert lon > -77.0  # right of due north is east -> longitude increases


def test_offset_point_facing_south_shifts_right_to_the_west():
    lat, lon = offset_point(38.9, -77.0, 180.0, 10.0)
    assert abs(lat - 38.9) < 1e-9
    assert lon < -77.0  # right of due south is west -> longitude decreases


def test_offset_point_zero_offset_is_a_no_op():
    lat, lon = offset_point(38.9, -77.0, 45.0, 0.0)
    assert abs(lat - 38.9) < 1e-12
    assert abs(lon - (-77.0)) < 1e-12


def test_offset_point_magnitude_roughly_matches_requested_meters():
    lat, lon = offset_point(38.9, -77.0, 90.0, 25.0)  # facing east -> right is south
    assert abs(lat - 38.9) > 0
    dist = haversine_m(38.9, -77.0, lat, lon)
    assert abs(dist - 25.0) < 0.5
