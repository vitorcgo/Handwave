import math
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

from effects.base import Effect
from effects.render import array_to_image, frame_to_array
from gestures import HandPose
from tracker import ensure_model

SEGMENTER_URL = (
    "https://storage.googleapis.com/mediapipe-models/image_segmenter/"
    "selfie_segmenter/float16/latest/selfie_segmenter.tflite"
)
SEGMENTER_PATH = Path(__file__).resolve().parent.parent / "selfie_segmenter.tflite"

WORK_SIZE = (640, 360)
# abaixo dessa confiança o pixel conta como fundo e entra na memória do fundo
BACKGROUND_BELOW = 0.3
LEARN_RATE = 0.15
REFRACTION = 14.0
MIN_SIDE = 60
FOLLOW = 16.0
HOLD_TIME = 0.45
HINT_COVERAGE = 0.85


class Glass(Effect):
    """Janela retangular entre os dois indicadores em que a pessoa vira vidro.

    O fundo é memorizado sozinho pelas partes que a pessoa não cobre. Dentro da
    janela, a pessoa some e o fundo aparece através dela, distorcido nas bordas
    como vidro, com brilhos finos no contorno.
    """

    name = "Vidro"
    icon = (
        '<path d="M9 10h.01"/><path d="M15 10h.01"/>'
        '<path d="M12 2a8 8 0 0 0-8 8v12l3-3 2.5 2.5L12 19l2.5 2.5L17 19l3 3V10a8 8 0 0 0-8-8z"/>'
    )
    wants_frame = True

    def __init__(self):
        self._worker = ThreadPoolExecutor(max_workers=1)
        self._job: Future | None = None
        self._segmenter = None
        self._timestamp = 0

        self._background: np.ndarray | None = None
        self._known: np.ndarray | None = None
        self._glass: QImage | None = None
        self._coverage = 0.0
        self._grid_cache: tuple[np.ndarray, np.ndarray] | None = None

        self._size = (1280, 720)
        self._target: np.ndarray | None = None
        self._rect: np.ndarray | None = None
        self._visible = 0.0
        self._hold = 0.0
        self._pair: tuple[int, int] | None = None

    # entrada

    def set_frame(self, frame: QImage):
        self._size = (frame.width(), frame.height())
        self._collect()
        if self._job is not None:
            return
        # o fundo é aprendido o tempo todo com o efeito ligado, para já estar pronto ao abrir a janela
        small = cv2.resize(frame_to_array(frame), WORK_SIZE, interpolation=cv2.INTER_AREA)
        region = None if self._rect is None else self._rect / np.array([*self._size, *self._size])
        self._job = self._worker.submit(self._process, small, region)

    def set_hands(self, poses: list[HandPose]):
        by_id = {pose.id: pose for pose in poses}
        pointing = [pose for pose in poses if pose.pointing]
        if len(pointing) >= 2:
            pair = pointing[:2]
            self._pair = (pair[0].id, pair[1].id)
            self._hold = HOLD_TIME
        elif self._hold > 0 and self._pair and all(i in by_id for i in self._pair):
            pair = [by_id[i] for i in self._pair]
        else:
            return
        a, b = pair[0].index_tip, pair[1].index_tip
        rect = np.array([min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])])
        if rect[2] - rect[0] >= MIN_SIDE and rect[3] - rect[1] >= MIN_SIDE:
            self._target = rect

    @property
    def _active(self) -> bool:
        return self._hold > 0 and self._target is not None

    def close(self):
        self._worker.shutdown(wait=False, cancel_futures=True)

    # processamento, fora da thread da interface

    def _collect(self):
        if self._job is not None and self._job.done():
            self._glass, self._coverage = self._job.result()
            self._job = None

    def _segment(self, rgb: np.ndarray) -> np.ndarray:
        if self._segmenter is None:
            options = vision.ImageSegmenterOptions(
                base_options=BaseOptions(model_asset_path=str(ensure_model(SEGMENTER_URL, SEGMENTER_PATH))),
                running_mode=vision.RunningMode.VIDEO,
                output_confidence_masks=True,
            )
            self._segmenter = vision.ImageSegmenter.create_from_options(options)
        self._timestamp += 33
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        result = self._segmenter.segment_for_video(image, self._timestamp)
        mask = result.confidence_masks[-1].numpy_view()
        return cv2.GaussianBlur(mask.reshape(mask.shape[:2]).astype(np.float32), (0, 0), 1.5)

    def _grid(self, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
        if self._grid_cache is None or self._grid_cache[0].shape != (height, width):
            self._grid_cache = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
        return self._grid_cache

    def _learn_background(self, rgb: np.ndarray, person: np.ndarray):
        frame = rgb.astype(np.float32)
        free = (person < BACKGROUND_BELOW).astype(np.uint8)
        if self._background is None:
            self._background = frame.copy()
            self._known = free.astype(np.float32)
            return
        cv2.accumulateWeighted(frame, self._background, LEARN_RATE, mask=free)
        np.maximum(self._known, free, out=self._known)

    def _process(self, rgb: np.ndarray, region: np.ndarray | None) -> tuple[QImage, float]:
        person = self._segment(rgb)
        self._learn_background(rgb, person)

        height, width = person.shape
        frame = rgb.astype(np.float32)
        # onde o fundo ainda não foi visto, um borrão forte da própria imagem faz as vezes de fundo;
        # borrar em 1/4 da resolução dá o mesmo resultado por uma fração do custo
        tiny = cv2.resize(frame, (width // 4, height // 4), interpolation=cv2.INTER_AREA)
        fallback = cv2.resize(cv2.GaussianBlur(tiny, (0, 0), 4.5), (width, height))
        background = cv2.blendLinear(self._background, fallback, self._known, 1 - self._known)

        # refração: o fundo é deslocado na direção da borda da silhueta, como luz atravessando vidro
        small_mask = cv2.resize(person, (width // 2, height // 2), interpolation=cv2.INTER_AREA)
        soft = cv2.resize(cv2.GaussianBlur(small_mask, (0, 0), 3), (width, height))
        grad_x = cv2.Sobel(soft, cv2.CV_32F, 1, 0, ksize=5)
        grad_y = cv2.Sobel(soft, cv2.CV_32F, 0, 1, ksize=5)
        grid_x, grid_y = self._grid(width, height)
        refracted = cv2.remap(
            background, grid_x + grad_x * REFRACTION, grid_y + grad_y * REFRACTION,
            cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT,
        )

        # brilhos: contorno da silhueta e um pouco do relevo da própria pessoa
        edge = cv2.magnitude(grad_x, grad_y)
        edge = cv2.min(edge * (1.6 / max(float(edge.max()), 1e-6)), 1.0)
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        detail = cv2.convertScaleAbs(cv2.Laplacian(cv2.GaussianBlur(gray, (0, 0), 1.2), cv2.CV_16S, ksize=3))
        detail = cv2.min(detail.astype(np.float32) * (1 / 40), 1.0) * person

        alpha = cv2.min(person * 1.25, 1.0)
        glass = cv2.blendLinear(refracted, frame, alpha, 1 - alpha)
        # elevar a borda ao quadrado afina o contorno e deixa o brilho só onde a curva é forte
        shine = cv2.min(edge * edge * 0.6 + detail * 0.4, 1.0) * alpha
        glass += cv2.merge([shine * 200, shine * 225, shine * 255])
        glass = cv2.convertScaleAbs(glass)

        coverage = 1.0
        if region is not None:
            x0, y0, x1, y1 = (region * np.array([width, height, width, height])).astype(int)
            inside = self._known[max(y0, 0):max(y1, 1), max(x0, 0):max(x1, 1)]
            coverage = float(inside.mean()) if inside.size else 1.0
        return array_to_image(glass), coverage

    # animação

    def tick(self, dt: float):
        self._collect()
        self._hold = max(0.0, self._hold - dt)
        target = 1.0 if self._active else 0.0
        self._visible += (target - self._visible) * (1 - math.exp(-dt * (8 if self._active else 4)))
        if self._target is None:
            return
        if self._rect is None or self._visible < 0.02:
            self._rect = self._target.copy()
        else:
            self._rect += (self._target - self._rect) * (1 - math.exp(-dt * FOLLOW))

    @property
    def idle(self) -> bool:
        return not self._active and self._visible < 0.005

    # desenho

    def draw(self, p: QPainter):
        if self._rect is None or self._glass is None or self._visible < 0.01:
            return
        width, height = self._size
        x0, y0, x1, y1 = (float(v) for v in self._rect)
        window = QRectF(x0, y0, x1 - x0, y1 - y0)

        p.save()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setClipRect(window)
        p.setOpacity(self._visible)
        p.drawImage(QRectF(0, 0, width, height), self._glass)
        p.setClipping(False)

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(70, 120, 255, 230), 1.5))
        p.drawRect(window)

        if self._coverage < HINT_COVERAGE:
            self._draw_hint(p, window)
        p.restore()

    def _draw_hint(self, p: QPainter, window: QRectF):
        font = QFont()
        font.setPixelSize(14)
        p.setFont(font)
        text = "Saia da frente por um instante para o vidro aprender o fundo"
        width = p.fontMetrics().horizontalAdvance(text) + 28
        pill = QRectF(window.center().x() - width / 2, window.top() + 12, width, 30)
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(QColor(14, 18, 40, 200))
        p.drawRoundedRect(pill, 15, 15)
        p.setPen(QColor(255, 255, 255, 230))
        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)
