import shutil
import ssl
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import certifi
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)
MODEL_PATH = Path(__file__).resolve().parent / "hand_landmarker.task"

HAND_CONNECTIONS = [(c.start, c.end) for c in vision.HandLandmarksConnections.HAND_CONNECTIONS]
FINGERTIPS = (4, 8, 12, 16, 20)


@dataclass
class Hand:
    side: str
    points: list[tuple[float, float]]


def ensure_model() -> Path:
    if MODEL_PATH.exists():
        return MODEL_PATH
    partial = MODEL_PATH.with_suffix(".part")
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(MODEL_URL, context=context, timeout=30) as response:
        with open(partial, "wb") as file:
            shutil.copyfileobj(response, file)
    partial.replace(MODEL_PATH)
    return MODEL_PATH


class HandTracker:
    def __init__(self, max_hands: int = 2, smoothing: float = 0.45):
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(ensure_model())),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=max_hands,
            min_hand_detection_confidence=0.6,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._smoothing = smoothing
        self._previous: dict[str, list[tuple[float, float]]] = {}
        self._last_timestamp = 0

    def process(self, rgb: np.ndarray, timestamp_ms: int) -> list[Hand]:
        # detect_for_video exige timestamps estritamente crescentes
        timestamp_ms = max(timestamp_ms, self._last_timestamp + 1)
        self._last_timestamp = timestamp_ms

        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        result = self._landmarker.detect_for_video(image, timestamp_ms)

        hands = []
        for landmarks, handedness in zip(result.hand_landmarks, result.handedness):
            side = handedness[0].category_name
            points = self._smooth(side, [(p.x, p.y) for p in landmarks])
            hands.append(Hand(side, points))

        seen = {hand.side for hand in hands}
        self._previous = {side: pts for side, pts in self._previous.items() if side in seen}
        return hands

    def _smooth(self, side: str, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        previous = self._previous.get(side)
        if previous:
            a = self._smoothing
            points = [
                (px * a + x * (1 - a), py * a + y * (1 - a))
                for (x, y), (px, py) in zip(points, previous)
            ]
        self._previous[side] = points
        return points

    def close(self):
        self._landmarker.close()
