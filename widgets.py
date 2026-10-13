from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QWidget

from tracker import FINGERTIPS, HAND_CONNECTIONS, Hand

ACCENT = QColor(64, 120, 255)

# Ícones no estilo Lucide, desenhados com traço branco
ICONS = {
    "hand": '<path d="M18 11V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2"/><path d="M14 10V4a2 2 0 0 0-2-2a2 2 0 0 0-2 2v2"/>'
            '<path d="M10 10.5V6a2 2 0 0 0-2-2a2 2 0 0 0-2 2v8"/>'
            '<path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>',
    "wave": '<path d="M2 12c2.5-5 7.5-5 10 0s7.5 5 10 0"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3" fill="white"/>',
    "flame": '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 '
             '2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
    "snowflake": '<path d="M2 12h20"/><path d="M12 2v20"/><path d="m20 16-4-4 4-4"/><path d="m4 8 4 4-4 4"/>'
                 '<path d="m16 4-4 4-4-4"/><path d="m8 20 4-4 4 4"/>',
    "settings": '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73'
                'l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73'
                'l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2'
                'v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73'
                'l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73'
                'l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
}


def round_pen(color: QColor, width: float) -> QPen:
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


def icon_renderer(name: str) -> QSvgRenderer:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="white" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>'
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
            alpha = 30 if self._hover else 16
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
        self.setFixedHeight(52)

        self.minimize_button = WindowButton("minimize")
        self.zoom_button = WindowButton("maximize")
        self.close_button = WindowButton("close")
        self.minimize_button.clicked.connect(self.minimize_clicked)
        self.zoom_button.clicked.connect(self.zoom_clicked)
        self.close_button.clicked.connect(self.close_clicked)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 14, 0)
        layout.setSpacing(4)
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
        self.setMinimumSize(480, 320)

    def sizeHint(self):
        return QSize(960, 600)

    def set_frame(self, frame: QImage, hands: list[Hand]):
        self._frame = frame
        self._hands = hands
        self.update()

    def set_message(self, message: str):
        self._message = message
        self._frame = None
        self._hands = []
        self.update()

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
            self._draw_hands(p, image_rect)
        p.restore()

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 46), 1))
        p.drawPath(path)

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
