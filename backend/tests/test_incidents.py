from app.services.incidents import MIN_BASELINE_SAMPLES, IncidentDetector


def test_no_incident_before_baseline_established():
    detector = IncidentDetector()
    for _ in range(MIN_BASELINE_SAMPLES - 1):
        assert detector.observe("seed-001", 10, 5.0) is None


def test_count_spike_detected_after_baseline():
    detector = IncidentDetector()
    for _ in range(MIN_BASELINE_SAMPLES):
        detector.observe("seed-001", 10, 5.0)

    result = detector.observe("seed-001", 25, 5.0)
    assert result is not None
    kind, severity, description = result
    assert kind == "count_spike"
    assert "25" in description


def test_speed_drop_detected_after_baseline():
    detector = IncidentDetector()
    for _ in range(MIN_BASELINE_SAMPLES):
        detector.observe("seed-001", 5, 8.0)

    result = detector.observe("seed-001", 5, 1.0)
    assert result is not None
    kind, _severity, _description = result
    assert kind == "speed_drop"


def test_stable_traffic_produces_no_incident():
    detector = IncidentDetector()
    for _ in range(MIN_BASELINE_SAMPLES + 5):
        result = detector.observe("seed-001", 6, 5.0)
    assert result is None


def test_baselines_are_independent_per_camera():
    detector = IncidentDetector()
    for _ in range(MIN_BASELINE_SAMPLES):
        detector.observe("seed-001", 5, 5.0)
        detector.observe("seed-002", 20, 5.0)

    # A count that would spike relative to seed-001's baseline is normal for
    # seed-002's much busier baseline, and vice versa.
    assert detector.observe("seed-002", 21, 5.0) is None
