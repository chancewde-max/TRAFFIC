"""YOLO-based vehicle detector. Only imported/instantiated in live camera mode.

Requires `ultralytics` + `torch`, which are heavy optional dependencies -- the
rest of the app runs fine without them (mock mode).
"""

from __future__ import annotations

from dataclasses import dataclass

VEHICLE_COCO_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


@dataclass
class Detection:
    bbox: tuple[float, float, float, float]  # normalized x1, y1, x2, y2
    confidence: float
    vehicle_class: str


class YoloVehicleDetector:
    def __init__(self, model_path: str, confidence: float) -> None:
        from ultralytics import YOLO  # deferred import: heavy + optional

        self.model = YOLO(model_path)
        self.confidence = confidence

    def detect(self, frame) -> list[Detection]:
        h, w = frame.shape[:2]
        results = self.model.predict(
            frame,
            verbose=False,
            conf=self.confidence,
            classes=list(VEHICLE_COCO_CLASSES),
        )[0]

        detections: list[Detection] = []
        for box in results.boxes:
            cls_id = int(box.cls[0])
            vehicle_class = VEHICLE_COCO_CLASSES.get(cls_id)
            if vehicle_class is None:
                continue
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            detections.append(
                Detection(
                    bbox=(x1 / w, y1 / h, x2 / w, y2 / h),
                    confidence=float(box.conf[0]),
                    vehicle_class=vehicle_class,
                )
            )
        return detections


def build_detector(model_path: str, confidence: float) -> "YoloVehicleDetector | None":
    """Returns a shared detector instance for live mode, or None if the
    optional ML dependencies (ultralytics/torch) aren't installed."""

    try:
        return YoloVehicleDetector(model_path, confidence)
    except ImportError:
        import logging

        logging.getLogger(__name__).warning(
            "ultralytics/torch not installed; cameras will fall back to mock simulation"
        )
        return None
