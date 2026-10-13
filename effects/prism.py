import math
from concurrent.futures import Future, ThreadPoolExecutor

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF

from effects.base import Effect
from effects.render import array_to_image, frame_to_array
from gestures import INDEX_MCP, INDEX_TIP, THUMB_TIP, WRIST, HandPose

FILTER_SIZE = (640, 360)
FOCAL = 1400.0
OPEN_THUMB = 0.45
FOLLOW = 18.0
HOLD_TIME = 0.45
# com as mãos em pé, a face branca fica de frente para a câmera
BASE_ROLL = math.radians(30)

# filtro de cada uma das três faces, na ordem em que giram
FACE_TEXTURES = ("sketch", "thermal", "dots")
CAP_TEXTURE = "thermal"

_LIGHT = (np.arange(256, dtype=np.float32) / 255) ** 1.4
_NAVY = np.array([6, 16, 48], np.float32)
_CYAN = np.array([110, 225, 255], np.float32)
DOTS_BASE = (_NAVY + _LIGHT[:, None] * (_CYAN - _NAVY) * 0.45).astype(np.uint8).reshape(256, 1, 3)
DOTS_CHANCE = (_LIGHT * 0.85 * 255).astype(np.uint8)
DOTS_SPARK = _CYAN.astype(np.uint8)


def _polygon(points) -> QPolygonF:
    return QPolygonF([QPointF(float(x), float(y)) for x, y in points])


def _wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


class Prism(Effect):
    """Prisma triangular entre as duas mãos abertas.

    O eixo vai de uma mão à outra e o tamanho segue a abertura entre indicador e polegar.
    Inclinar os pulsos para a frente ou para trás gira o prisma no eixo. Cada face é uma
    lente com um filtro: branco, térmico e pontos azuis.
    """

    name = "Prisma"
    icon = (
        '<path d="M12 3 3 19h18Z"/><path d="M12 3v16"/>'
    )
    wants_frame = True

    def __init__(self):
        self._rng = np.random.default_rng()
        self._size = (1280, 720)
        self._textures: dict[str, QImage] = {}
        self._spark: np.ndarray | None = None
        self._worker = ThreadPoolExecutor(max_workers=1)
        self._job: Future | None = None

        self._visible = 0.0
        self._hold = 0.0
        self._pair: tuple[int, int] | None = None

        self._target: tuple[np.ndarray, float, float] | None = None
        self._axis: np.ndarray | None = None
        self._radius = 0.0
        self._roll = 0.0

    # entrada

    def set_frame(self, frame: QImage):
        self._size = (frame.width(), frame.height())
        self._collect()
        if not self._active and self._visible < 0.01:
            return
        if self._job is not None:
            # os filtros do quadro anterior ainda estão rodando; este quadro é pulado
            return
        small = cv2.resize(frame_to_array(frame), FILTER_SIZE, interpolation=cv2.INTER_AREA)
        self._job = self._worker.submit(self._build_textures, small)

    def set_hands(self, poses: list[HandPose]):
        by_id = {pose.id: pose for pose in poses}
        open_hands = [pose for pose in poses if self._is_open(pose)]
        if len(open_hands) >= 2:
            pair = open_hands[:2]
            self._pair = (pair[0].id, pair[1].id)
            self._hold = HOLD_TIME
        elif self._hold > 0 and self._pair and all(i in by_id for i in self._pair):
            # o gesto falhou por um instante, mas as mesmas mãos continuam na tela: o prisma segue com elas
            pair = [by_id[i] for i in self._pair]
        else:
            return

        left, right = sorted(pair, key=lambda pose: pose.points[WRIST][0])
        start = (left.index_tip + left.points[THUMB_TIP]) / 2
        end = (right.index_tip + right.points[THUMB_TIP]) / 2
        axis = np.array([start, end])
        radius = (self._opening(left) + self._opening(right)) / 4
        roll = self._mean_angle([self._hand_roll(left, axis), self._hand_roll(right, axis)])
        self._target = (axis, radius, roll)

    @staticmethod
    def _is_open(pose: HandPose) -> bool:
        gap = float(np.linalg.norm(pose.points[THUMB_TIP] - pose.points[INDEX_MCP]))
        return pose.pointing and gap > pose.palm * OPEN_THUMB

    @staticmethod
    def _opening(pose: HandPose) -> float:
        return float(np.linalg.norm(pose.index_tip - pose.points[THUMB_TIP]))

    @staticmethod
    def _hand_roll(pose: HandPose, axis: np.ndarray) -> float:
        """Quanto a mão está inclinada para a câmera, pelo vetor do polegar ao indicador em 3D."""
        if pose.world is None:
            return 0.0
        up = Prism._up(axis)
        vector = pose.world[INDEX_TIP] - pose.world[THUMB_TIP]
        along_screen = float(vector[0] * up[0] + vector[1] * up[1])
        toward_camera = float(-vector[2])
        return math.atan2(toward_camera, along_screen)

    @staticmethod
    def _mean_angle(angles: list[float]) -> float:
        return math.atan2(sum(math.sin(a) for a in angles), sum(math.cos(a) for a in angles))

    @staticmethod
    def _up(axis: np.ndarray) -> np.ndarray:
        """Direção perpendicular ao eixo, apontando para cima na tela."""
        direction = axis[1] - axis[0]
        direction = direction / max(float(np.linalg.norm(direction)), 1e-6)
        up = np.array([direction[1], -direction[0]])
        return up if up[1] <= 0 else -up

    @property
    def _active(self) -> bool:
        return self._hold > 0

    def close(self):
        self._worker.shutdown(wait=False, cancel_futures=True)

    # filtros

    def _collect(self):
        if self._job is not None and self._job.done():
            self._textures = self._job.result()
            self._job = None

    def _build_textures(self, small: np.ndarray) -> dict[str, QImage]:
        # roda fora da thread da interface; OpenCV e numpy liberam o Python enquanto processam
        gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
        return {
            "thermal": array_to_image(self._thermal(gray)),
            "dots": array_to_image(self._dots(gray)),
            "sketch": array_to_image(self._sketch(gray)),
        }

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

        axis, radius, roll = self._target
        if self._axis is None or self._visible < 0.02:
            self._axis, self._radius, self._roll = axis.copy(), radius, roll
            return
        k = 1 - math.exp(-dt * FOLLOW)
        self._axis += (axis - self._axis) * k
        self._radius += (radius - self._radius) * k
        self._roll += _wrap(roll - self._roll) * (1 - math.exp(-dt * 10))

    @property
    def idle(self) -> bool:
        return not self._active and self._visible < 0.005

    # geometria

    def _faces(self) -> list[tuple[str, list[np.ndarray], float]]:
        """Faces visíveis já projetadas, com o filtro e o quanto cada uma está de frente."""
        width, height = self._size
        center = np.array([width / 2, height / 2])
        camera = np.array([center[0], center[1], FOCAL])

        start, end = self._axis
        direction = end - start
        direction = direction / max(float(np.linalg.norm(direction)), 1e-6)
        up = self._up(self._axis)

        angles = BASE_ROLL + self._roll + np.array([0.0, 2 * math.pi / 3, 4 * math.pi / 3])
        offsets = np.stack(
            [np.cos(angles) * up[0], np.cos(angles) * up[1], np.sin(angles)], axis=1
        ) * self._radius
        near = np.append(start, 0.0) + offsets
        far = np.append(end, 0.0) + offsets

        def project(points3d: np.ndarray) -> list[np.ndarray]:
            # perspectiva simples a partir do centro da câmera; z positivo fica mais perto
            scale = FOCAL / (FOCAL - points3d[:, 2])
            return list(center + (points3d[:, :2] - center) * scale[:, None])

        faces = []
        for k in range(3):
            j = (k + 1) % 3
            quad = np.array([near[k], far[k], far[j], near[j]])
            middle = angles[k] + math.pi / 3
            normal = np.array([math.cos(middle) * up[0], math.cos(middle) * up[1], math.sin(middle)])
            faces.append((FACE_TEXTURES[k], quad, normal))

        axis3d = np.append(direction, 0.0)
        faces.append((CAP_TEXTURE, near, -axis3d))
        faces.append((CAP_TEXTURE, far, axis3d))

        visible = []
        for texture, corners, normal in faces:
            view = camera - corners.mean(axis=0)
            facing = float(np.dot(normal, view) / np.linalg.norm(view))
            if facing > 0:
                visible.append((texture, project(corners), facing))
        return visible

    # desenho

    def draw(self, p: QPainter):
        if self._axis is None or self._visible < 0.01 or not self._textures:
            return
        width, height = self._size
        frame_rect = QRectF(0, 0, width, height)
        faces = self._faces()

        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for texture, corners, facing in faces:
            path = QPainterPath()
            path.addPolygon(_polygon(corners))
            path.closeSubpath()
            p.save()
            p.setClipPath(path)
            p.setOpacity(self._visible * (0.55 + 0.45 * facing))
            p.drawImage(frame_rect, self._textures[texture])
            p.restore()

        p.setOpacity(self._visible)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 210), 1.3))
        for _, corners, _ in faces:
            p.drawPolygon(_polygon(corners))
        p.restore()
