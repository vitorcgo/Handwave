from dataclasses import dataclass

import numpy as np

from tracker import Hand

WRIST = 0
THUMB_MCP, THUMB_TIP = 2, 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_PIP, RING_TIP = 14, 16
PINKY_PIP, PINKY_TIP = 18, 20


@dataclass
class HandPose:
    """Mão já interpretada, com pontos em pixels do quadro da câmera."""

    id: int
    points: np.ndarray
    palm: float
    pointing: bool
    l_shape: bool
    velocity: np.ndarray

    @property
    def index_tip(self) -> np.ndarray:
        return self.points[INDEX_TIP]

    @property
    def index_direction(self) -> np.ndarray:
        direction = self.points[INDEX_TIP] - self.points[INDEX_PIP]
        return direction / max(float(np.linalg.norm(direction)), 1e-6)


def _distance(a, b) -> float:
    return float(np.linalg.norm(a - b))


def _extended(points: np.ndarray, tip: int, pip: int) -> bool:
    wrist = points[WRIST]
    return _distance(points[tip], wrist) > _distance(points[pip], wrist) * 1.15


def _is_l_shape(points: np.ndarray, palm: float, index: bool) -> bool:
    if not index or _extended(points, MIDDLE_TIP, MIDDLE_PIP) or _extended(points, RING_TIP, RING_PIP):
        return False
    if _distance(points[THUMB_TIP], points[INDEX_MCP]) < palm * 0.7:
        return False
    thumb = points[THUMB_TIP] - points[THUMB_MCP]
    finger = points[INDEX_TIP] - points[INDEX_MCP]
    cosine = float(np.dot(thumb, finger) / max(np.linalg.norm(thumb) * np.linalg.norm(finger), 1e-6))
    return cosine < 0.55


class GestureReader:
    def __init__(self):
        self._previous: dict[int, tuple[np.ndarray, float, np.ndarray]] = {}

    def read(self, hands: list[Hand], width: int, height: int, timestamp: float) -> list[HandPose]:
        poses = []
        for hand in hands:
            points = np.asarray(hand.points, dtype=np.float64) * (width, height)
            palm = max(_distance(points[WRIST], points[MIDDLE_MCP]), 1.0)
            index = _extended(points, INDEX_TIP, INDEX_PIP)
            velocity = self._velocity(hand.id, points[INDEX_TIP], timestamp)
            poses.append(HandPose(hand.id, points, palm, index, _is_l_shape(points, palm, index), velocity))

        seen = {pose.id for pose in poses}
        self._previous = {key: value for key, value in self._previous.items() if key in seen}
        return poses

    def _velocity(self, hand_id: int, tip: np.ndarray, timestamp: float) -> np.ndarray:
        velocity = np.zeros(2)
        previous = self._previous.get(hand_id)
        if previous is not None:
            last_tip, last_time, last_velocity = previous
            dt = timestamp - last_time
            velocity = last_velocity
            if dt > 1e-3:
                velocity = last_velocity * 0.4 + (tip - last_tip) / dt * 0.6
        self._previous[hand_id] = (tip.copy(), timestamp, velocity)
        return velocity
