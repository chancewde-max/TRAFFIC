from app.cv.detector import Detection
from app.cv.tracker import IouTracker, iou


def det(x1, y1, x2, y2, vehicle_class="car", confidence=0.9):
    return Detection(bbox=(x1, y1, x2, y2), confidence=confidence, vehicle_class=vehicle_class)


def test_iou_identical_boxes_is_one():
    box = (0.1, 0.1, 0.3, 0.3)
    assert iou(box, box) == 1.0


def test_iou_disjoint_boxes_is_zero():
    assert iou((0.0, 0.0, 0.1, 0.1), (0.5, 0.5, 0.6, 0.6)) == 0.0


def test_tracker_keeps_same_id_for_slightly_moved_box():
    tracker = IouTracker(iou_threshold=0.25)
    first = tracker.update([det(0.1, 0.1, 0.3, 0.3)])
    second = tracker.update([det(0.12, 0.1, 0.32, 0.3)])
    assert first[0].track_id == second[0].track_id


def test_tracker_assigns_distinct_ids_to_simultaneous_detections():
    tracker = IouTracker()
    results = tracker.update([det(0.0, 0.0, 0.1, 0.1), det(0.8, 0.8, 0.9, 0.9)])
    ids = {r.track_id for r in results}
    assert len(ids) == 2


def test_tracker_drops_stale_tracks_after_max_age():
    tracker = IouTracker(max_age_frames=2)
    tracker.update([det(0.1, 0.1, 0.3, 0.3)])
    # Advance frames with unrelated detections far away so the original track
    # isn't re-matched, until it exceeds max_age_frames and is pruned.
    for _ in range(5):
        tracker.update([det(0.6, 0.6, 0.7, 0.7)])
    assert len(tracker.tracks) == 1
    remaining = next(iter(tracker.tracks.values()))
    assert remaining.bbox == (0.6, 0.6, 0.7, 0.7)


def test_tracker_reassigns_new_id_after_track_expires():
    tracker = IouTracker(max_age_frames=1)
    first = tracker.update([det(0.1, 0.1, 0.3, 0.3)])
    for _ in range(4):
        tracker.update([det(0.9, 0.9, 0.95, 0.95)])
    reappeared = tracker.update([det(0.1, 0.1, 0.3, 0.3)])
    assert reappeared[0].track_id != first[0].track_id
