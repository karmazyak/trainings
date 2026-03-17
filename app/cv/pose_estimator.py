import logging
from functools import lru_cache
from pathlib import Path

import cv2
from ultralytics import YOLO

from app.cv.models import FrameKeypoints, Keypoint

logger = logging.getLogger(__name__)

FRAME_SKIP = 3  # process every Nth frame


@lru_cache(maxsize=1)
def get_model() -> YOLO:
    return YOLO("yolo11n-pose.pt")


def extract_keypoints(video_path: Path) -> list[FrameKeypoints]:
    model = get_model()
    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    frames_data = []
    frame_idx = 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % FRAME_SKIP != 0:
                frame_idx += 1
                continue

            results = model(frame, verbose=False)

            if results and results[0].keypoints is not None:
                kps = results[0].keypoints
                if kps.xy is not None and len(kps.xy) > 0:
                    # Take first detected person
                    xy = kps.xy[0].cpu().numpy()
                    conf = kps.conf[0].cpu().numpy() if kps.conf is not None else [1.0] * len(xy)

                    keypoints = [
                        Keypoint(x=float(pt[0]), y=float(pt[1]), confidence=float(c))
                        for pt, c in zip(xy, conf)
                    ]
                    frames_data.append(FrameKeypoints(
                        frame_index=frame_idx,
                        keypoints=keypoints,
                    ))

            frame_idx += 1
    finally:
        cap.release()

    logger.info(f"Extracted keypoints from {len(frames_data)} frames (total: {frame_idx})")
    return frames_data
