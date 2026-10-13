import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QLabel, QWidget

from effects.base import Effect
from gestures import GestureReader
from tracker import FINGERTIPS, HAND_CONNECTIONS, Hand

LOGO = Path(__file__).resolve().parent / "logo.png"
EFFECT_DIM = 110

# Ícones no estilo Lucide, desenhados com traço branco
ICONS = {
    "hand": '<path d="M18 11V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2"/><path d="M14 10V4a2 2 0 0 0-2-2a2 2 0 0 0-2 2v2"/>'
            '<path d="M10 10.5V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2v8"/>'
            '<path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>',
    "mirror": '<path d="M8 3H5a2 2 0 0 0-2 2v14c0 1.1.9 2 2 2h3"/><path d="M16 3h3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-3"/>'
              '<path d="M12 20v2"/><path d="M12 14v2"/><path d="M12 8v2"/><path d="M12 2v2"/>',
    "switch": '<path d="M11 19H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/><path d="M13 5h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-5"/>'
              '<circle cx="12" cy="12" r="3"/><path d="m18 22-3-3 3-3"/><path d="m6 2 3 3-3 3"/>',
    "pause": '<rect x="14" y="4" width="4" height="16" rx="1"/><rect x="6" y="4" width="4" height="16" rx="1"/>',
    "play": '<path d="M6 3l14 9-14 9z"/>',
    "photo": '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/>'
             '<circle cx="12" cy="13" r="3"/>',
}


def round_pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


def logo_mark(height: int) -> QPixmap:
    """Recorta só a mão do logo, sem o texto e sem a borda transparente."""
    image = QImage(str(LOGO)).convertToFormat(QImage.Format.Format_RGBA8888)
    data = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine())
    alpha = data[:, : image.width() * 4].reshape(image.height(), image.width(), 4)[:, :, 3] > 40

    rows = np.nonzero(alpha.any(axis=1))[0]
    gaps = np.nonzero(np.diff(rows) > 1)[0]
    top, bottom = rows[0], rows[gaps[0]] if len(gaps) else rows[-1]
    cols = np.nonzero(alpha[top:bottom + 1].any(axis=0))[0]

    pad = 12
    left = max(cols[0] - pad, 0)
    top = max(top - pad, 0)
    right = min(cols[-1] + pad, image.width() - 1)
    bottom = min(bottom + pad, image.height() - 1)
    cropped = image.copy(int(left), int(top), int(right - left + 1), int(bottom - top + 1))

    ratio = QGuiApplication.primaryScreen().devicePixelRatio()
    pixmap = QPixmap.fromImage(cropped).scaledToHeight(
        round(height * ratio), Qt.TransformationMode.SmoothTransformation
    )
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def icon_renderer(name: str) -> QSvgRenderer:
    """Aceita o nome de um ícone de ICONS ou o próprio conteúdo SVG."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="white" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{ICONS.get(name, name)}</svg>'
    )
    return QSvgRenderer(QByteArray(svg.encode()))


class SideButton(QAbstractButton):
    SIZE = 46

    def __init__(self, icon: str, tooltip: str, checkable: bool = True, parent=None):
        super().__init__(parent)
        self._renderer = icon_renderer(icon)
        self._hover = False
        self.setCheckable(checkable)
        self.setToolTip(tooltip)
        self.setFixedSize(self.SIZE + 16, self.SIZE + 16)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_icon(self, icon: str):
        self._renderer = icon_renderer(icon)
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        r = self.SIZE / 2

        if self.isChecked():
            glow = QRadialGradient(center, r + 8)
            glow.setColorAt(0.6, QColor(64, 120, 255, 120))
            glow.setColorAt(1, QColor(64, 120, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(center, r + 8, r + 8)

            fill = QRadialGradient(center - QPointF(0, r * 0.4), r * 1.4)
            fill.setColorAt(0, QColor(90, 140, 255))
            fill.setColorAt(1, QColor(38, 70, 200))
            p.setBrush(fill)
            p.setPen(QPen(QColor(170, 200, 255, 220), 1.5))
        else:
            alpha = 46 if self.isDown() else 30 if self._hover else 16
            p.setBrush(QColor(255, 255, 255, alpha))
            p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.drawEllipse(center, r - 0.5, r - 0.5)

        icon = 20
        p.setOpacity(1.0 if self.isChecked() or self._hover else 0.78)
        self._renderer.render(p, QRectF(center.x() - icon / 2, center.y() - icon / 2, icon, icon))


class Separator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(SideButton.SIZE + 16, 17)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawLine(16, 8, self.width() - 16, 8)


class WindowButton(QAbstractButton):
    def __init__(self, glyph: str, parent=None):
        super().__init__(parent)
        self._glyph = glyph
        self._hover = False
        self.setFixedSize(40, 32)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def set_glyph(self, glyph: str):
        self._glyph = glyph
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover:
            color = QColor(232, 17, 35, 200) if self._glyph == "close" else QColor(255, 255, 255, 26)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(self.rect()), 8, 8)

        p.setPen(round_pen(QColor(255, 255, 255, 220), 1.3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        c = QPointF(self.width() / 2, self.height() / 2)
        s = 5.5
        if self._glyph == "close":
            p.drawLine(c + QPointF(-s, -s), c + QPointF(s, s))
            p.drawLine(c + QPointF(-s, s), c + QPointF(s, -s))
        elif self._glyph == "minimize":
            p.drawLine(c + QPointF(-s, 0), c + QPointF(s, 0))
        elif self._glyph == "maximize":
            p.drawRoundedRect(QRectF(c.x() - s, c.y() - s, s * 2, s * 2), 1.5, 1.5)
        else:
            p.drawRoundedRect(QRectF(c.x() - s, c.y() - s + 2, s * 2 - 2, s * 2 - 2), 1.5, 1.5)
            p.drawPolyline([c + QPointF(-s + 2, -s), c + QPointF(s, -s), c + QPointF(s, s - 2)])


class TitleBar(QWidget):
    close_clicked = Signal()
    minimize_clicked = Signal()
    zoom_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)

        mark = QLabel(self)
        mark.setPixmap(logo_mark(30))
        name = QLabel("Handwave", self)
        font = name.font()
        font.setPointSizeF(11.5)
        font.setWeight(QFont.Weight.DemiBold)
        name.setFont(font)
        name.setStyleSheet("color: rgba(255, 255, 255, 0.9);")
        for label in (mark, name):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self.minimize_button = WindowButton("minimize")
        self.zoom_button = WindowButton("maximize")
        self.close_button = WindowButton("close")
        self.minimize_button.clicked.connect(self.minimize_clicked)
        self.zoom_button.clicked.connect(self.zoom_clicked)
        self.close_button.clicked.connect(self.close_clicked)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(36, 0, 14, 0)
        layout.setSpacing(4)
        layout.addWidget(mark)
        layout.addSpacing(6)
        layout.addWidget(name)
        layout.addStretch()
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.zoom_button)
        layout.addWidget(self.close_button)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().windowHandle().startSystemMove()

    def mouseDoubleClickEvent(self, event):
        self.zoom_clicked.emit()


class CameraView(QWidget):
    RADIUS = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame: QImage | None = None
        self._hands: list[Hand] = []
        self._message = "Conectando câmera"
        self._toast = ""
        self._toast_timer = QTimer(self, singleShot=True, interval=2200)
        self._toast_timer.timeout.connect(lambda: self.show_toast(""))
        self.show_hands = True
        self.paused = False
        self.effect: Effect | None = None
        self._gestures = GestureReader()
        self._gesture_labels: dict[int, str] = {}
        self._last_tick = time.perf_counter()
        self._clock = QTimer(self, interval=16)
        self._clock.timeout.connect(self._advance)
        self._clock.start()
        self.setMinimumSize(480, 320)

    def sizeHint(self):
        return QSize(960, 600)

    def set_frame(self, frame: QImage, hands: list[Hand]):
        self._frame = frame
        self._hands = hands
        poses = self._gestures.read(hands, frame.width(), frame.height(), time.perf_counter())
        self._gesture_labels = {pose.id: pose.label for pose in poses}
        if self.effect is not None:
            self.effect.set_hands(poses)
        self.update()

    def set_effect(self, effect: Effect | None):
        self.effect = effect
        self.update()

    def _advance(self):
        now = time.perf_counter()
        dt = min(now - self._last_tick, 0.05)
        self._last_tick = now
        if self.effect is None or self.paused or self._frame is None:
            return
        self.effect.tick(dt)
        self.update()

    def set_message(self, message: str):
        self._message = message
        self._frame = None
        self._hands = []
        self.update()

    def show_toast(self, text: str):
        self._toast = text
        if text:
            self._toast_timer.start()
        self.update()

    def snapshot(self) -> QImage | None:
        if self._frame is None:
            return None
        image = self._frame.convertToFormat(QImage.Format.Format_RGB32)
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.show_hands:
            self._draw_hands(p, QRectF(image.rect()))
        if self.effect is not None:
            p.fillRect(image.rect(), QColor(0, 0, 10, EFFECT_DIM))
            self.effect.draw(p)
        p.end()
        return image

    def _image_rect(self, rect: QRectF) -> QRectF:
        scale = max(rect.width() / self._frame.width(), rect.height() / self._frame.height())
        width = self._frame.width() * scale
        height = self._frame.height() * scale
        return QRectF(rect.center().x() - width / 2, rect.center().y() - height / 2, width, height)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)

        p.save()
        p.setClipPath(path)
        if self._frame is None:
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0, QColor(12, 14, 28, 230))
            gradient.setColorAt(1, QColor(6, 8, 18, 240))
            p.fillRect(rect, gradient)
            p.setPen(QColor(255, 255, 255, 160))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._message)
        else:
            image_rect = self._image_rect(rect)
            p.drawImage(image_rect, self._frame)
            if self.show_hands:
                self._draw_hands(p, image_rect)
            if self.effect is not None:
                # escurece o vídeo para a luz aditiva dos efeitos não estourar em fundo claro
                p.fillRect(image_rect, QColor(0, 0, 10, EFFECT_DIM))
                p.save()
                p.translate(image_rect.topLeft())
                scale = image_rect.width() / self._frame.width()
                p.scale(scale, scale)
                self.effect.draw(p)
                p.restore()
        p.restore()

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 46), 1))
        p.drawPath(path)

        if self.paused and self._frame is not None:
            self._draw_pill(p, "Pausado", rect.top() + 18)
        if self._toast:
            self._draw_pill(p, self._toast, rect.bottom() - 18 - 34)

    def _draw_pill(self, p: QPainter, text: str, y: float):
        font = self.font()
        font.setPointSizeF(10)
        font.setWeight(QFont.Weight.Medium)
        p.setFont(font)
        width = p.fontMetrics().horizontalAdvance(text) + 36
        pill = QRectF(self.width() / 2 - width / 2, y, width, 34)
        p.setPen(QPen(QColor(255, 255, 255, 50), 1))
        p.setBrush(QColor(14, 18, 40, 190))
        p.drawRoundedRect(pill, 17, 17)
        p.setPen(QColor(255, 255, 255, 230))
        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_hands(self, p: QPainter, rect: QRectF):
        glow_pen = round_pen(QColor(70, 130, 255, 70), 7)
        core_pen = round_pen(QColor(190, 215, 255, 220), 1.6)

        for hand in self._hands:
            points = [QPointF(rect.x() + x * rect.width(), rect.y() + y * rect.height()) for x, y in hand.points]

            for pen in (glow_pen, core_pen):
                p.setPen(pen)
                for start, end in HAND_CONNECTIONS:
                    p.drawLine(points[start], points[end])

            p.setPen(Qt.PenStyle.NoPen)
            for index, point in enumerate(points):
                halo = 9 if index in FINGERTIPS else 6
                gradient = QRadialGradient(point, halo)
                gradient.setColorAt(0, QColor(120, 170, 255, 170))
                gradient.setColorAt(1, QColor(70, 130, 255, 0))
                p.setBrush(gradient)
                p.drawEllipse(point, halo, halo)
                p.setBrush(QColor(255, 255, 255))
                core = 2.8 if index in FINGERTIPS else 2.0
                p.drawEllipse(point, core, core)

            label = self._gesture_labels.get(hand.id)
            if label:
                self._draw_gesture_label(p, label, points[0])
        p.setBrush(Qt.BrushStyle.NoBrush)

    def _draw_gesture_label(self, p: QPainter, text: str, wrist: QPointF):
        font = self.font()
        font.setPointSizeF(9)
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        width = p.fontMetrics().horizontalAdvance(text) + 20
        pill = QRectF(wrist.x() - width / 2, wrist.y() + 14, width, 22)
        p.setPen(QPen(QColor(150, 185, 255, 160), 1))
        p.setBrush(QColor(20, 40, 110, 200))
        p.drawRoundedRect(pill, 11, 11)
        p.setPen(QColor(255, 255, 255, 235))
        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)
