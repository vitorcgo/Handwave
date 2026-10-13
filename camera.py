import sys
import time

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from tracker import HandTracker

if sys.platform == "win32":
    # DirectShow trava várias webcams em 10 fps no 720p
    BACKEND = cv2.CAP_MSMF
elif sys.platform == "darwin":
    BACKEND = cv2.CAP_AVFOUNDATION
else:
    BACKEND = cv2.CAP_ANY


class CameraWorker(QThread):
    frame_ready = Signal(QImage, list, float)
    status_changed = Signal(str, str)

    def __init__(self, max_index: int = 4, parent=None):
        super().__init__(parent)
        self._max_index = max_index

    def run(self):
        self.status_changed.emit("loading", "Preparando rastreamento")
        try:
            tracker = HandTracker()
        except Exception:
            self.status_changed.emit("error", "Não foi possível carregar o modelo de mãos")
            return

        try:
            while not self.isInterruptionRequested():
                capture = self._open_camera()
                if capture is None:
                    self.status_changed.emit("searching", "Procurando câmera")
                    self.msleep(1500)
                    continue
                self.status_changed.emit("live", "Câmera conectada")
                self._stream(capture, tracker)
                capture.release()
        finally:
            tracker.close()

    def _open_camera(self):
        for index in range(self._max_index):
            capture = cv2.VideoCapture(index, BACKEND)
            if not capture.isOpened():
                capture.release()
                continue
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            ok, _ = capture.read()
            if ok:
                return capture
            capture.release()
        return None

    def _stream(self, capture, tracker: HandTracker):
        failures = 0
        last = time.perf_counter()
        fps = 0.0

        while not self.isInterruptionRequested():
            ok, frame = capture.read()
            if not ok:
                failures += 1
                if failures > 15:
                    return
                self.msleep(30)
                continue
            failures = 0

            frame = cv2.flip(frame, 1)
            height, width = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            hands = tracker.process(rgb, int(time.monotonic() * 1000))

            now = time.perf_counter()
            fps = fps * 0.9 + (1.0 / max(now - last, 1e-6)) * 0.1
            last = now

            image = QImage(rgb.data, width, height, width * 3, QImage.Format.Format_RGB888).copy()
            self.frame_ready.emit(image, hands, fps)
