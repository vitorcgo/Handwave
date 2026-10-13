from functools import cache

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QRadialGradient


@cache
def glow_sprite(size: int = 64) -> QImage:
    """Ponto de luz branco-azulado com borda suave, para desenhar em modo aditivo."""
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    gradient = QRadialGradient(size / 2, size / 2, size / 2)
    gradient.setColorAt(0.0, QColor(255, 255, 255, 255))
    gradient.setColorAt(0.2, QColor(220, 232, 255, 190))
    gradient.setColorAt(0.5, QColor(150, 180, 255, 60))
    gradient.setColorAt(1.0, QColor(120, 150, 255, 0))
    p = QPainter(image)
    p.fillRect(image.rect(), gradient)
    p.end()
    return image


def draw_glow(p: QPainter, x: float, y: float, radius: float, opacity: float):
    p.setOpacity(max(0.0, min(opacity, 1.0)))
    p.drawImage(QRectF(x - radius, y - radius, radius * 2, radius * 2), glow_sprite())


@cache
def mono_font(pixel_size: int = 10) -> QFont:
    font = QFont()
    font.setFamilies(["Cascadia Mono", "Consolas", "Menlo", "Courier New"])
    font.setPixelSize(pixel_size)
    return font


def point(xy) -> QPointF:
    return QPointF(float(xy[0]), float(xy[1]))
