"""YOLOv8-based object detector wrapper."""
from ultralytics import YOLO
import numpy as np


class YOLODetector:
    """Wraps a YOLOv8 model to produce bounding-box detections from video frames."""
    def __init__(self, model_name: str = "yolov8n.pt", confidence: float = 0.5):
        self.model = YOLO(model_name)
        self.confidence = confidence
        self.class_names = self.model.names

    def detect(self, frame: np.ndarray, override_conf: float | None = None) -> np.ndarray:
        """
        Run detection on a single frame.
        Returns array of shape (N, 6): [x1, y1, x2, y2, confidence, class_id]
        """
        results = self.model(frame, conf=override_conf if override_conf is not None else self.confidence, verbose=False)[0]
        boxes = results.boxes

        if boxes is None or len(boxes) == 0:
            return np.empty((0, 6))

        xyxy = boxes.xyxy.cpu().numpy()
        confs = boxes.conf.cpu().numpy().reshape(-1, 1)
        cls = boxes.cls.cpu().numpy().reshape(-1, 1)

        return np.hstack([xyxy, confs, cls])

    def get_class_name(self, class_id: int) -> str:
        """Return the COCO class label for the given integer class ID."""
        return self.class_names.get(int(class_id), "unknown")
