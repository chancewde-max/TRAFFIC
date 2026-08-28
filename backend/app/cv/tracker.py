"""Lightweight greedy IOU tracker.

Assigns persistent track IDs to detections across frames without pulling in a
heavy tracking dependency. Good enough for short-range association between
consecutive samples (we sample video at ~1 fps, not full frame rate).
"""

from __future__ import annotations

from dataclasses import dataclass

from .detector import Detection


@dataclass
class TrackedObject:
    track_id: int
    bbox: tuple[float, float, float, float]
    vehicle_class: str
    last_seen_frame: int


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class IouTracker:
    def __init__(self, iou_threshold: float = 0.25, max_age_frames: int = 5) -> None:
        self.iou_threshold = iou_threshold
        self.max_age_frames = max_age_frames
        self.tracks: dict[int, TrackedObject] = {}
        self._next_id = 1
        self._frame_idx = 0

    def update(self, detections: list[Detection]) -> list[TrackedObject]:
        self._frame_idx += 1
        matched: set[int] = set()
        results: list[TrackedObject] = []

        for det in detections:
            best_id, best_iou = None, 0.0
            for tid, tr in self.tracks.items():
                if tid in matched:
                    continue
                score = iou(det.bbox, tr.bbox)
                if score > best_iou:
                    best_iou, best_id = score, tid

            if best_id is not None and best_iou >= self.iou_threshold:
                track_id = best_id
            else:
                track_id = self._next_id
                self._next_id += 1

            matched.add(track_id)
            obj = TrackedObject(
                track_id=track_id,
                bbox=det.bbox,
                vehicle_class=det.vehicle_class,
                last_seen_frame=self._frame_idx,
            )
            self.tracks[track_id] = obj
            results.append(obj)

        stale = [
            tid
            for tid, tr in self.tracks.items()
            if self._frame_idx - tr.last_seen_frame > self.max_age_frames
        ]
        for tid in stale:
            del self.tracks[tid]

        return results
