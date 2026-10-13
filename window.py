from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRectF, QStandardPaths, Qt
from PySide6.QtGui import QColor, QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from blur import enable_blur, set_round_region
from camera import CameraWorker
from effects import EFFECTS
from widgets import CameraView, Separator, SideButton, TitleBar

RADIUS = 26
RESIZE_MARGIN = 6
BODY_MARGINS = (26, 0, 40, 40)


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

        self.hands_button = SideButton("hand", "Ocultar traçado das mãos  (H)")
        self.hands_button.setChecked(True)
        self.hands_button.toggled.connect(self._set_show_hands)

        self.mirror_button = SideButton("mirror", "Espelhar imagem  (M)")
        self.mirror_button.setChecked(True)
        self.mirror_button.toggled.connect(self._set_mirror)

        self.effect_buttons = []
        for number, effect_class in enumerate(EFFECTS, start=1):
            button = SideButton(effect_class.icon, f"{effect_class.name}  ({number})")
            button.toggled.connect(lambda on, cls=effect_class, b=button: self._toggle_effect(cls, b, on))
            self.effect_buttons.append(button)

        self.switch_button = SideButton("switch", "Trocar câmera  (C)", checkable=False)
        self.switch_button.clicked.connect(self._switch_camera)

        self.pause_button = SideButton("pause", "Pausar  (Espaço)")
        self.pause_button.toggled.connect(self._set_paused)

        self.photo_button = SideButton("photo", "Salvar foto  (S)", checkable=False)
        self.photo_button.clicked.connect(self._save_photo)

        self.sidebar = QWidget(self)
        sidebar = QVBoxLayout(self.sidebar)
        sidebar.setContentsMargins(0, 0, 0, 0)
        sidebar.setSpacing(4)
        sidebar.addStretch()
        sidebar.addWidget(self.hands_button)
        sidebar.addWidget(self.mirror_button)
        if self.effect_buttons:
            sidebar.addWidget(Separator())
            for button in self.effect_buttons:
                sidebar.addWidget(button)
        sidebar.addWidget(Separator())
        sidebar.addWidget(self.switch_button)
        sidebar.addWidget(self.pause_button)
        sidebar.addWidget(self.photo_button)
        sidebar.addStretch()

        self.body = QHBoxLayout()
        self.body.setContentsMargins(*BODY_MARGINS)
        self.body.setSpacing(26)
        self.body.addWidget(self.sidebar)
        self.body.addWidget(self.camera_view, 1)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(0, 8, 0, 0)
        self.root.setSpacing(0)
        self.root.addWidget(self.title_bar)
        self.root.addLayout(self.body, 1)

        self._add_shortcuts()

        self.worker = CameraWorker()
        self.worker.frame_ready.connect(self._on_frame)
        self.worker.status_changed.connect(self._on_status)
        self.worker.notice.connect(self.camera_view.show_toast)
        self.worker.start()

        if self.effect_buttons:
            self.effect_buttons[0].setChecked(True)

    def _add_shortcuts(self):
        keys = {
            "H": self.hands_button.toggle,
            "M": self.mirror_button.toggle,
            "C": self.switch_button.click,
            "Space": self.pause_button.toggle,
            "S": self.photo_button.click,
            "F": self._toggle_fullscreen,
            "Esc": self._exit_fullscreen,
        }
        for number, button in enumerate(self.effect_buttons, start=1):
            keys[str(number)] = button.toggle
        for key, action in keys.items():
            QShortcut(QKeySequence(key), self, activated=action)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self._exit_fullscreen()
            return
        self._was_maximized = self.isMaximized()
        self.title_bar.hide()
        self.sidebar.hide()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.root.setContentsMargins(0, 0, 0, 0)
        self.camera_view.radius = 0
        self.showFullScreen()
        self.camera_view.show_toast("Tela cheia. Esc para sair")

    def _exit_fullscreen(self):
        if not self.isFullScreen():
            return
        self.title_bar.show()
        self.sidebar.show()
        self.body.setContentsMargins(*BODY_MARGINS)
        self.root.setContentsMargins(0, 8, 0, 0)
        self.camera_view.radius = CameraView.RADIUS
        if getattr(self, "_was_maximized", False):
            self.showMaximized()
        else:
            self.showNormal()

    def _square_corners(self) -> bool:
        return self.isMaximized() or self.isFullScreen()

    def _on_frame(self, frame, hands, fps):
        self.camera_view.set_frame(frame, hands)

    def _on_status(self, state, text):
        if state != "live":
            self.camera_view.set_message(text)

    def _set_show_hands(self, visible):
        self.camera_view.show_hands = visible
        self.hands_button.setToolTip(f"{'Ocultar' if visible else 'Mostrar'} traçado das mãos  (H)")
        self.camera_view.update()

    def _toggle_effect(self, effect_class, button, on):
        # um efeito por vez: ligar um desliga os outros
        if on:
            for other in self.effect_buttons:
                if other is not button:
                    other.setChecked(False)
            self.camera_view.set_effect(effect_class())
        elif isinstance(self.camera_view.effect, effect_class):
            self.camera_view.set_effect(None)

    def _set_mirror(self, mirror):
        self.worker.mirror = mirror

    def _set_paused(self, paused):
        self.worker.paused = paused
        self.camera_view.paused = paused
        self.pause_button.set_icon("play" if paused else "pause")
        self.pause_button.setToolTip(f"{'Continuar' if paused else 'Pausar'}  (Espaço)")
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
        radius = 0 if self._square_corners() else round(RADIUS * ratio)
        set_round_region(self._hwnd, round(self.width() * ratio), round(self.height() * ratio), radius)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 0 if self._square_corners() else RADIUS
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
        if self._square_corners():
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
