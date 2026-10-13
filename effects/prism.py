import math
from concurrent.futures import Future, ThreadPoolExecutor

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF

from effects.base import Effect
from gestures import INDEX_MCP, THUMB_TIP, WRIST, HandPose

FILTER_SIZE = (640, 360)
DEPTH = 0.9
BACK_SCALE = 0.85
OPEN_THUMB = 0.45
FOLLOW = 18.0
HOLD_TIME = 0.45

_LIGHT = (np.arange(256, dtype=np.float32) / 255) ** 1.4
_NAVY = np.array([6, 16, 48], np.float32)
_CYAN = np.array([110, 225, 255], np.float32)
DOTS_BASE = (_NAVY + _LIGHT[:, None] * (_CYAN - _NAVY) * 0.45).astype(np.uint8).reshape(256, 1, 3)
DOTS_CHANCE = (_LIGHT * 0.85 * 255).astype(np.uint8)
DOTS_SPARK = _CYAN.astype(np.uint8)


def _to_array(frame: QImage) -> np.ndarray:
    frame = frame.convertToFormat(QImage.Format.Format_RGB888)
    data = np.frombuffer(frame.constBits(), np.uint8).reshape(frame.height(), frame.bytesPerLine())
    return data[:, : frame.width() * 3].reshape(frame.height(), frame.width(), 3)


def _to_image(rgb: np.ndarray) -> QImage:
    rgb = np.ascontiguousarray(rgb)
    height, width = rgb.shape[:2]
    return QImage(rgb.data, width, height, width * 3, QImage.Format.Format_RGB888).copy()


def _polygon(points) -> QPolygonF:
    return QPolygonF([QPointF(float(x), float(y)) for x, y in points])


class Prism(Effect):
    """Caixa 3D entre as duas mãos abertas.

    A face da frente vai do indicador ao polegar de cada mão e as laterais seguem a
    perspectiva da câmera. Cada face é uma lente que mostra o vídeo com um filtro.
    """

    name = "Prisma"
    icon = (
        '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4'
        'a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>'
    )
    wants_frame = True

    def __init__(self):
        self._rng = np.random.default_rng()
        self._size = (1280, 720)
        self._textures: dict[str, QImage] = {}
        self._spark: np.ndarray | None = None
        self._worker = ThreadPoolExecutor(max_workers=1)
        self._job: Future | None = None
        self._front: np.ndarray | None = None
        self._target: np.ndarray | None = None
        self._visible = 0.0
        self._hold = 0.0
        self._pair: tuple[int, int] | None = None

    # entrada

    def set_frame(self, frame: QImage):
        self._size = (frame.width(), frame.height())
        self._collect()
        if not self._active and self._visible < 0.01:
            return
        if self._job is not None:
            # os filtros do quadro anterior ainda estão rodando; este quadro é pulado
            return
        small = cv2.resize(_to_array(frame), FILTER_SIZE, interpolation=cv2.INTER_AREA)
        self._job = self._worker.submit(self._build_textures, small)

    def _collect(self):
        if self._job is not None and self._job.done():
            self._textures = self._job.result()
            self._job = None

    def _build_textures(self, small: np.ndarray) -> dict[str, QImage]:
        # roda fora da thread da interface; OpenCV e numpy liberam o Python enquanto processam
        gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
        return {
            "thermal": _to_image(self._thermal(gray)),
            "dots": _to_image(self._dots(gray)),
            "sketch": _to_image(self._sketch(gray)),
        }

    def set_hands(self, poses: list[HandPose]):
        by_id = {pose.id: pose for pose in poses}
        open_hands = [pose for pose in poses if self._is_open(pose)]
        if len(open_hands) >= 2:
            pair = open_hands[:2]
            self._pair = (pair[0].id, pair[1].id)
            self._hold = HOLD_TIME
        elif self._hold > 0 and self._pair and all(i in by_id for i in self._pair):
            # o gesto falhou por um instante, mas as mesmas mãos continuam na tela: a caixa segue com elas
            pair = [by_id[i] for i in self._pair]
        else:
            return
        left, right = sorted(pair, key=lambda pose: pose.points[WRIST][0])
        self._target = np.array([
            left.index_tip,
            right.index_tip,
            right.points[THUMB_TIP],
            left.points[THUMB_TIP],
        ])

    @property
    def _active(self) -> bool:
        return self._hold > 0

    def close(self):
        self._worker.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _is_open(pose: HandPose) -> bool:
        gap = float(np.linalg.norm(pose.points[THUMB_TIP] - pose.points[INDEX_MCP]))
        return pose.pointing and gap > pose.palm * OPEN_THUMB

    # filtros

    @staticmethod
    def _thermal(gray: np.ndarray) -> np.ndarray:
        heat = cv2.GaussianBlur(gray, (0, 0), 3)
        heat = cv2.equalizeHist(heat)
        return cv2.cvtColor(cv2.applyColorMap(heat, cv2.COLORMAP_JET), cv2.COLOR_BGR2RGB)

    def _dots(self, gray: np.ndarray) -> np.ndarray:
        # cor de fundo e chance de faísca vêm de tabelas por tom de cinza, sem conta pixel a pixel
        base = cv2.LUT(cv2.merge([gray, gray, gray]), DOTS_BASE)
        noise = self._rng.integers(0, 255, gray.shape, dtype=np.uint8)
        sparkle = cv2.compare(noise, cv2.LUT(gray, DOTS_CHANCE), cv2.CMP_LT)
        if self._spark is None or self._spark.shape != base.shape:
            self._spark = np.full_like(base, DOTS_SPARK)
        cv2.copyTo(self._spark, sparkle, base)
        return base

    @staticmethod
    def _sketch(gray: np.ndarray) -> np.ndarray:
        height, width = gray.shape
        small = cv2.resize(255 - gray, (width // 2, height // 2), interpolation=cv2.INTER_AREA)
        blur = cv2.resize(cv2.GaussianBlur(small, (0, 0), 3), (width, height), interpolation=cv2.INTER_LINEAR)
        sketch = cv2.divide(gray, 255 - blur, scale=256)
        return cv2.cvtColor(sketch, cv2.COLOR_GRAY2RGB)

    # animação

    def tick(self, dt: float):
        self._collect()
        self._hold = max(0.0, self._hold - dt)
        target = 1.0 if self._active else 0.0
        self._visible += (target - self._visible) * (1 - math.exp(-dt * (8 if self._active else 4)))
        if self._target is None:
            return
        if self._front is None or self._visible < 0.02:
            self._front = self._target.copy()
        else:
            self._front += (self._target - self._front) * (1 - math.exp(-dt * FOLLOW))

    @property
    def idle(self) -> bool:
        return not self._active and self._visible < 0.005

    @staticmethod
    def _back_face(front: np.ndarray, width: int, height: int) -> np.ndarray:
        # a caixa se estende para o centro da tela, então a face voltada para fora sempre aparece;
        # a profundidade acompanha a altura da frente para manter a proporção ao aproximar as mãos
        center = front.mean(axis=0)
        toward = np.array([width / 2, height / 2]) - center
        distance = float(np.linalg.norm(toward))
        direction = toward / distance if distance > 1 else np.array([0.0, 1.0])
        face_height = float(np.linalg.norm((front[2] + front[3]) / 2 - (front[0] + front[1]) / 2))
        return center + (front - center) * BACK_SCALE + direction * max(face_height, 40.0) * DEPTH

    # desenho

    def draw(self, p: QPainter):
        if self._front is None or self._visible < 0.01 or not self._textures:
            return
        width, height = self._size
        front = self._front
        back = self._back_face(front, width, height)
        frame_rect = QRectF(0, 0, width, height)

        faces = [
            ("dots", [front[0], front[1], back[1], back[0]], 0.92),
            ("sketch", [front[1], front[2], back[2], back[1]], 0.85),
            ("dots", [front[2], front[3], back[3], back[2]], 0.92),
            ("sketch", [front[3], front[0], back[0], back[3]], 0.85),
            ("thermal", list(front), 1.0),
        ]

        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for texture, corners, shade in faces:
            path = QPainterPath()
            path.addPolygon(_polygon(corners))
            path.closeSubpath()
            p.save()
            p.setClipPath(path)
            p.setOpacity(self._visible * shade)
            p.drawImage(frame_rect, self._textures[texture])
            p.restore()

        p.setOpacity(self._visible)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 220), 1.4))
        p.drawPolygon(_polygon(front))
        p.setPen(QPen(QColor(255, 255, 255, 110), 1))
        p.drawPolygon(_polygon(back))
        for a, b in zip(front, back):
            p.drawLine(QPointF(*a), QPointF(*b))
        p.restore()
