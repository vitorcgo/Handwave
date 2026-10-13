import ctypes
import sys
from pathlib import Path

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from window import MainWindow

LOGO = Path(__file__).resolve().parent / "logo.png"


def main():
    if sys.platform == "win32":
        # sem isso a barra de tarefas mostra o ícone do Python
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("handwave.app")

    app = QApplication(sys.argv)
    app.setApplicationName("Handwave")
    app.setWindowIcon(QIcon(str(LOGO)))

    font = QFont()
    font.setFamilies(["SF Pro Text", ".AppleSystemUIFont", "Segoe UI Variable Text", "Segoe UI", "Helvetica Neue"])
    font.setPointSizeF(10)
    app.setFont(font)
    app.setStyleSheet(
        "QToolTip {"
        " background-color: rgb(18, 22, 46);"
        " color: rgba(255, 255, 255, 0.92);"
        " border: 1px solid rgba(150, 180, 255, 0.35);"
        " border-radius: 8px;"
        " padding: 6px 10px;"
        "}"
    )

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
