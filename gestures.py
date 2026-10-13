from collections import deque
from dataclasses import dataclass

import numpy as np

from tracker import Hand

WRIST = 0
THUMB_MCP, THUMB_TIP = 2, 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP = 9

THUMB = (1, 2, 3, 4)
INDEX = (5, 6, 7, 8)
MIDDLE = (9, 10, 11, 12)
RING = (13, 14, 15, 16)

STRAIGHT = 0.85
CURLED = 0.75
DEBOUNCE_FRAMES = 3
FAST_MOTION = 900


@dataclass
class HandPose:
    """Mão já interpretada, com pontos em pixels do quadro da câmera."""

    id: int
    points: np.ndarray
    palm: float
    pointing: bool
    l_shape: bool
    velocity: np.ndarray
    # maior velocidade dos últimos instantes; segura gestos rápidos em que o rastreador perde a mão
    peak_velocity: np.ndarray
    # pontos 3D em metros (x para a direita, y para baixo, z se afastando da câmera)
    world: np.ndarray | None = None

    @property
    def index_tip(self) -> np.ndarray:
        return self.points[INDEX_TIP]

    @property
    def index_direction(self) -> np.ndarray:
        direction = self.points[INDEX_TIP] - self.points[INDEX_PIP]
        return direction / max(float(np.linalg.norm(direction)), 1e-6)

    @property
    def label(self) -> str:
        if self.l_shape:
            return "L"
        if self.pointing:
            return "apontando"
        return ""


def _distance(a, b) -> float:
    return float(np.linalg.norm(a - b))


def _straightness(joints: np.ndarray, finger: tuple[int, ...]) -> float:
    """1 para dedo totalmente reto, perto de 0.5 ou menos para dedo dobrado."""
    path = sum(_distance(joints[a], joints[b]) for a, b in zip(finger, finger[1:]))
    return _distance(joints[finger[0]], joints[finger[-1]]) / max(path, 1e-6)


def _curled(joints: np.ndarray, points: np.ndarray, finger: tuple[int, ...]) -> bool:
    # o 3D do MediaPipe achata dedos dobrados na direção da câmera, então basta um dos dois indicar
    pip, tip = finger[1], finger[-1]
    folded_in_image = _distance(points[tip], points[WRIST]) < _distance(points[pip], points[WRIST]) * 1.15
    return folded_in_image or _straightness(joints, finger) < CURLED


def _index_extended(joints: np.ndarray, points: np.ndarray) -> bool:
    in_image = _distance(points[INDEX_TIP], points[WRIST]) > _distance(points[INDEX_PIP], points[WRIST]) * 1.15
    return in_image and _straightness(joints, INDEX) > STRAIGHT


def _thumb_open(points: np.ndarray, palm: float, was_open: bool) -> bool:
    # o L é uma forma vista de frente, então polegar e indicador são medidos na imagem;
    # entrar exige polegar bem aberto e sair exige bem fechado, para não oscilar no meio-termo
    gap = _distance(points[THUMB_TIP], points[INDEX_MCP]) / palm
    thumb = points[THUMB_TIP] - points[THUMB_MCP]
    finger = points[INDEX_TIP] - points[INDEX_MCP]
    cosine = float(np.dot(thumb, finger) / max(np.linalg.norm(thumb) * np.linalg.norm(finger), 1e-6))
    if was_open:
        return gap > 0.45 and cosine < 0.75
    return gap > 0.65 and cosine < 0.5


def _is_l_shape(joints: np.ndarray, points: np.ndarray, palm: float, index: bool, was_l: bool) -> bool:
    if not index:
        return False
    if not _curled(joints, points, MIDDLE) or not _curled(joints, points, RING):
        return False
    return _thumb_open(points, palm, was_l)


class GestureReader:
    PEAK_WINDOW = 0.25

    def __init__(self):
        self._previous: dict[int, tuple[np.ndarray, float, np.ndarray]] = {}
        self._history: dict[int, deque[tuple[float, np.ndarray]]] = {}
        self._stable: dict[tuple[int, str], tuple[bool, int]] = {}

    def read(self, hands: list[Hand], width: int, height: int, timestamp: float) -> list[HandPose]:
        poses = []
        for hand in hands:
            points = np.asarray(hand.points, dtype=np.float64) * (width, height)
            palm = max(_distance(points[WRIST], points[MIDDLE_MCP]), 1.0)

            # em 3D a pose não depende da rotação da mão; sem 3D, usa o plano da imagem
            joints = hand.world if hand.world is not None else np.column_stack([points, np.zeros(21)])
            velocity = self._velocity(hand.id, points[INDEX_TIP], timestamp)
            peak = self._peak(hand.id, velocity, timestamp)
            # com a mão em movimento rápido o borrão engana a leitura, então o gesto fica como estava
            frozen = float(np.linalg.norm(velocity)) > FAST_MOTION

            index = _index_extended(joints, points)
            pointing = self._debounce(hand.id, "pointing", index, frozen)
            was_l = self._stable.get((hand.id, "l_shape"), (False, 0))[0]
            l_shape = self._debounce(hand.id, "l_shape", _is_l_shape(joints, points, palm, index, was_l), frozen)
            poses.append(HandPose(hand.id, points, palm, pointing, l_shape, velocity, peak, hand.world))

        seen = {pose.id for pose in poses}
        self._previous = {key: value for key, value in self._previous.items() if key in seen}
        self._history = {key: value for key, value in self._history.items() if key in seen}
        self._stable = {key: value for key, value in self._stable.items() if key[0] in seen}
        return poses

    def _debounce(self, hand_id: int, name: str, value: bool, frozen: bool = False) -> bool:
        """Só troca o estado depois de alguns quadros seguidos discordando, para não piscar."""
        key = (hand_id, name)
        current, streak = self._stable.get(key, (value, 0))
        if frozen and key in self._stable:
            return current
        if value == current:
            streak = 0
        else:
            streak += 1
            if streak >= DEBOUNCE_FRAMES:
                current, streak = value, 0
        self._stable[key] = (current, streak)
        return current

    def _peak(self, hand_id: int, velocity: np.ndarray, timestamp: float) -> np.ndarray:
        history = self._history.setdefault(hand_id, deque())
        history.append((timestamp, velocity))
        while history and timestamp - history[0][0] > self.PEAK_WINDOW:
            history.popleft()
        return max((v for _, v in history), key=lambda v: float(np.linalg.norm(v)))

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
