import itertools
import math
import shutil
import ssl
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import certifi
import cv2
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

MATCH_DISTANCE = 0.3
HOLD_FRAMES = 6


@dataclass
class Hand:
    id: int
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


class OneEuroFilter:
    """Suaviza forte quando a mão está parada e libera quando ela se move rápido."""

    def __init__(self, min_cutoff: float = 1.0, beta: float = 5.0, d_cutoff: float = 1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._value: np.ndarray | None = None
        self._speed: np.ndarray | None = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, value: np.ndarray, dt: float) -> np.ndarray:
        if self._value is None:
            self._value = value
            self._speed = np.zeros_like(value)
            return value
        dt = max(dt, 1e-3)
        speed = (value - self._value) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self._speed = a_d * speed + (1 - a_d) * self._speed

        magnitude = np.linalg.norm(self._speed, axis=1, keepdims=True)
        a = self._alpha(self.min_cutoff + self.beta * magnitude, dt)
        self._value = a * value + (1 - a) * self._value
        return self._value


_track_ids = itertools.count(1)


@dataclass
class _Track:
    side: str
    points: np.ndarray
    filter: OneEuroFilter = field(default_factory=OneEuroFilter)
    missed: int = 0
    id: int = field(default_factory=lambda: next(_track_ids))

    @property
    def center(self) -> np.ndarray:
        return self.points[[0, 5, 9, 13, 17]].mean(axis=0)


class HandTracker:
    def __init__(self, max_hands: int = 2):
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(ensure_model())),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=max_hands,
            # limites baixos seguram a mão em movimento, com borrão ou tatuagem;
            # o filtro e a associação por posição cuidam do ruído que sobra
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.3,
            min_tracking_confidence=0.3,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._tracks: list[_Track] = []
        self._last_timestamp = 0

    def process(self, rgb: np.ndarray, timestamp_ms: int) -> list[Hand]:
        # detect_for_video exige timestamps estritamente crescentes
        timestamp_ms = max(timestamp_ms, self._last_timestamp + 1)
        dt = (timestamp_ms - self._last_timestamp) / 1000 if self._last_timestamp else 1 / 30
        self._last_timestamp = timestamp_ms

        square, scale, offset = self._to_square(rgb)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=square)
        result = self._landmarker.detect_for_video(image, timestamp_ms)

        detections = []
        for landmarks, handedness in zip(result.hand_landmarks, result.handedness):
            points = np.array([(p.x, p.y) for p in landmarks], dtype=np.float64)
            points = (points - offset) * scale
            detections.append((handedness[0].category_name, points))

        self._update_tracks(detections, dt)
        return [Hand(t.id, t.side, [tuple(p) for p in t.points]) for t in self._tracks]

    @staticmethod
    def _to_square(rgb: np.ndarray):
        # o MediaPipe distorce os pontos de mãos inclinadas em imagens não quadradas,
        # então a imagem é completada com faixas pretas até virar quadrada
        height, width = rgb.shape[:2]
        side = max(width, height)
        top = (side - height) // 2
        left = (side - width) // 2
        square = cv2.copyMakeBorder(
            rgb, top, side - height - top, left, side - width - left, cv2.BORDER_CONSTANT, value=0
        )
        square = np.ascontiguousarray(square)
        offset = np.array([left / side, top / side])
        scale = np.array([side / width, side / height])
        return square, scale, offset

    def _update_tracks(self, detections, dt: float):
        unmatched = list(range(len(self._tracks)))
        matched = []

        for side, points in detections:
            center = points[[0, 5, 9, 13, 17]].mean(axis=0)
            best, best_distance = None, MATCH_DISTANCE
            for index in unmatched:
                distance = float(np.linalg.norm(self._tracks[index].center - center))
                if distance < best_distance:
                    best, best_distance = index, distance

            if best is None:
                track = _Track(side, points)
                track.points = track.filter(points, dt)
            else:
                unmatched.remove(best)
                track = self._tracks[best]
                track.side = side
                track.missed = 0
                track.points = track.filter(points, dt)
            matched.append(track)

        for index in unmatched:
            track = self._tracks[index]
            track.missed += 1
            if track.missed <= HOLD_FRAMES:
                matched.append(track)

        self._tracks = matched

    def close(self):
        self._landmarker.close()
