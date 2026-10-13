from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRectF, QStandardPaths, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from blur import enable_blur, set_round_region
from camera import CameraWorker
from widgets import CameraView, Separator, SideButton, TitleBar

RADIUS = 26
RESIZE_MARGIN = 6


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Handwave")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setMinimumSize(760, 520)
        self.resize(1220, 760)

        self._hwnd = int(self.winId())
        self._blurred = enable_blur(self._hwnd)

        self.title_bar = TitleBar(self)
        self.title_bar.close_clicked.connect(self.close)
        self.title_bar.minimize_clicked.connect(self.showMinimized)
        self.title_bar.zoom_clicked.connect(self._toggle_zoom)

        self.camera_view = CameraView(self)

        self.hands_button = SideButton("hand", "Mostrar mãos")
        self.hands_button.setChecked(True)
        self.hands_button.toggled.connect(self._set_show_hands)

        self.mirror_button = SideButton("mirror", "Espelhar imagem")
        self.mirror_button.setChecked(True)
        self.mirror_button.toggled.connect(self._set_mirror)

        self.switch_button = SideButton("switch", "Trocar câmera", checkable=False)
        self.switch_button.clicked.connect(self._switch_camera)

        self.pause_button = SideButton("pause", "Pausar")
        self.pause_button.toggled.connect(self._set_paused)

        self.photo_button = SideButton("photo", "Salvar foto", checkable=False)
        self.photo_button.clicked.connect(self._save_photo)

        sidebar = QVBoxLayout()
        sidebar.setContentsMargins(0, 0, 0, 0)
        sidebar.setSpacing(4)
        sidebar.addStretch()
        sidebar.addWidget(self.hands_button)
        sidebar.addWidget(self.mirror_button)
        sidebar.addWidget(Separator())
        sidebar.addWidget(self.switch_button)
        sidebar.addWidget(self.pause_button)
        sidebar.addWidget(self.photo_button)
        sidebar.addStretch()

        body = QHBoxLayout()
        body.setContentsMargins(26, 0, 40, 40)
        body.setSpacing(26)
        body.addLayout(sidebar)
        body.addWidget(self.camera_view, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.title_bar)
        layout.addLayout(body, 1)

        self.worker = CameraWorker()
        self.worker.frame_ready.connect(self._on_frame)
        self.worker.status_changed.connect(self._on_status)
        self.worker.notice.connect(self.camera_view.show_toast)
        self.worker.start()

    def _on_frame(self, frame, hands, fps):
        self.camera_view.set_frame(frame, hands)

    def _on_status(self, state, text):
        if state != "live":
            self.camera_view.set_message(text)

    def _set_show_hands(self, visible):
        self.camera_view.show_hands = visible
        self.hands_button.setToolTip("Ocultar mãos" if visible else "Mostrar mãos")
        self.camera_view.update()

    def _set_mirror(self, mirror):
        self.worker.mirror = mirror

    def _set_paused(self, paused):
        self.worker.paused = paused
        self.camera_view.paused = paused
        self.pause_button.set_icon("play" if paused else "pause")
        self.pause_button.setToolTip("Continuar" if paused else "Pausar")
        self.camera_view.update()

    def _switch_camera(self):
        if self.pause_button.isChecked():
            self.pause_button.setChecked(False)
        self.camera_view.set_message("Trocando câmera")
        self.worker.switch_camera()

    def _save_photo(self):
        image = self.camera_view.snapshot()
        if image is None:
            self.camera_view.show_toast("Nenhuma imagem para salvar")
            return
        folder = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)) / "Handwave"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"handwave_{datetime.now():%Y%m%d_%H%M%S}.png"
        if image.save(str(path)):
            self.camera_view.show_toast("Foto salva em Imagens/Handwave")
        else:
            self.camera_view.show_toast("Não foi possível salvar a foto")

    def _toggle_zoom(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange:
            self.title_bar.zoom_button.set_glyph("restore" if self.isMaximized() else "maximize")
            self._update_region()
        super().changeEvent(event)

    def resizeEvent(self, event):
        self._update_region()
        super().resizeEvent(event)

    def _update_region(self):
        if not self._blurred:
            return
        ratio = self.devicePixelRatioF()
        radius = 0 if self.isMaximized() else round(RADIUS * ratio)
        set_round_region(self._hwnd, round(self.width() * ratio), round(self.height() * ratio), radius)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 0 if self.isMaximized() else RADIUS
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        alpha = 1 if self._blurred else 3
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, QColor(70, 90, 170, min(255, 60 * alpha)))
        gradient.setColorAt(1, QColor(14, 18, 48, min(255, 90 * alpha)))
        p.fillPath(path, gradient)

        border = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        border.setColorAt(0, QColor(255, 255, 255, 80))
        border.setColorAt(1, QColor(255, 255, 255, 24))
        p.setPen(QPen(border, 1))
        p.drawPath(path)

    def _edges_at(self, pos):
        edges = Qt.Edge(0)
        if self.isMaximized():
            return edges
        if pos.x() <= RESIZE_MARGIN:
            edges |= Qt.Edge.LeftEdge
        elif pos.x() >= self.width() - RESIZE_MARGIN:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= RESIZE_MARGIN:
            edges |= Qt.Edge.TopEdge
        elif pos.y() >= self.height() - RESIZE_MARGIN:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mouseMoveEvent(self, event):
        edges = self._edges_at(event.position().toPoint())
        horizontal = edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge)
        vertical = edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge)
        if horizontal and vertical:
            diagonal = edges in (Qt.Edge.LeftEdge | Qt.Edge.TopEdge, Qt.Edge.RightEdge | Qt.Edge.BottomEdge)
            self.setCursor(Qt.CursorShape.SizeFDiagCursor if diagonal else Qt.CursorShape.SizeBDiagCursor)
        elif horizontal:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif vertical:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.unsetCursor()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        edges = self._edges_at(event.position().toPoint())
        if edges:
            self.windowHandle().startSystemResize(edges)
        else:
            self.windowHandle().startSystemMove()

    def closeEvent(self, event):
        self.worker.requestInterruption()
        self.worker.wait(3000)
        super().closeEvent(event)
