from functools import cache

import numpy as np
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QRadialGradient


WHITE = (235, 242, 255)
ICE = (150, 190, 255)
DEEP = (90, 130, 255)


@cache
def glow_sprite(tint: tuple[int, int, int] = WHITE, size: int = 64) -> QImage:
    """Ponto de luz com núcleo quente e halo suave, para desenhar em modo aditivo."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    r, g, b = tint
    gradient = QRadialGradient(size / 2, size / 2, size / 2)
    gradient.setColorAt(0.0, QColor(255, 255, 255, 255))
    gradient.setColorAt(0.08, QColor(255, 255, 255, 235))
    gradient.setColorAt(0.22, QColor(r, g, b, 140))
    gradient.setColorAt(0.5, QColor(r, g, b, 38))
    gradient.setColorAt(1.0, QColor(r, g, b, 0))
    p = QPainter(image)
    p.fillRect(image.rect(), gradient)
    p.end()
    return image


def draw_glow(p: QPainter, x: float, y: float, radius: float, opacity: float, tint=WHITE):
    # sprite já no tamanho certo: copiar é bem mais barato que redimensionar a cada partícula
    diameter = max(2, round(radius * 2))
    p.setOpacity(max(0.0, min(opacity, 1.0)))
    p.drawImage(QPointF(x - diameter / 2, y - diameter / 2), glow_sprite(tint, diameter))


def frame_to_array(frame: QImage) -> np.ndarray:
    """Quadro da câmera como array RGB, sem cópia quando o formato já bate."""
    frame = frame.convertToFormat(QImage.Format.Format_RGB888)
    data = np.frombuffer(frame.constBits(), np.uint8).reshape(frame.height(), frame.bytesPerLine())
    return data[:, : frame.width() * 3].reshape(frame.height(), frame.width(), 3)


def array_to_image(rgb: np.ndarray) -> QImage:
    rgb = np.ascontiguousarray(rgb)
    height, width = rgb.shape[:2]
    return QImage(rgb.data, width, height, width * 3, QImage.Format.Format_RGB888).copy()


@cache
def mono_font(pixel_size: int = 10) -> QFont:
    font = QFont()
    font.setFamilies(["Cascadia Mono", "Consolas", "Menlo", "Courier New"])
    font.setPixelSize(pixel_size)
    return font


def point(xy) -> QPointF:
    return QPointF(float(xy[0]), float(xy[1]))
