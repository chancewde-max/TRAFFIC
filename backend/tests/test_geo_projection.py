from app.cv.geo_projection import (
    FAR_M,
    NEAR_M,
    bbox_center_uv,
    haversine_m,
    meters_per_degree_lon,
    project_detection,
)

CAM_LAT, CAM_LON = 38.9072, -77.0369


def test_bearing_zero_center_near_moves_north_and_close():
    point = project_detection(CAM_LAT, CAM_LON, 0.0, u=0.0, v=1.0)
    assert point.lat > CAM_LAT
    assert abs(point.lon - CAM_LON) < 1e-6
    distance = haversine_m(CAM_LAT, CAM_LON, point.lat, point.lon)
    assert abs(distance - NEAR_M) < 0.5


def test_bearing_zero_center_far_is_further_than_near():
    near = project_detection(CAM_LAT, CAM_LON, 0.0, u=0.0, v=1.0)
    far = project_detection(CAM_LAT, CAM_LON, 0.0, u=0.0, v=0.0)
    d_near = haversine_m(CAM_LAT, CAM_LON, near.lat, near.lon)
    d_far = haversine_m(CAM_LAT, CAM_LON, far.lat, far.lon)
    assert d_far > d_near
    assert abs(d_far - FAR_M) < 0.5


def test_bearing_east_moves_longitude_not_latitude():
    point = project_detection(CAM_LAT, CAM_LON, 90.0, u=0.0, v=1.0)
    assert point.lon > CAM_LON
    assert abs(point.lat - CAM_LAT) < 1e-6


def test_u_out_of_range_is_clamped_not_error():
    point = project_detection(CAM_LAT, CAM_LON, 0.0, u=5.0, v=1.0)
    assert point is not None


def test_heading_offset_from_bearing():
    point = project_detection(CAM_LAT, CAM_LON, 0.0, u=0.25, v=1.0, fov_deg=70.0)
    assert abs(point.heading_deg - 17.5) < 1e-6


def test_haversine_zero_distance_for_same_point():
    assert haversine_m(CAM_LAT, CAM_LON, CAM_LAT, CAM_LON) == 0.0


def test_meters_per_degree_lon_shrinks_towards_poles():
    assert meters_per_degree_lon(0.0) > meters_per_degree_lon(60.0)


def test_bbox_center_uv():
    u, v = bbox_center_uv((0.25, 0.4, 0.75, 0.6))
    assert abs(u - 0.0) < 1e-9
    assert abs(v - 0.5) < 1e-9
