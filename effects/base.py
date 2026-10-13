from PySide6.QtGui import QPainter

from gestures import HandPose


class Effect:
    """Contrato dos efeitos. Todas as coordenadas estão em pixels do quadro da câmera."""

    name = ""
    # conteúdo de um SVG 24x24 com traço, no estilo Lucide
    icon = ""

    def set_hands(self, poses: list[HandPose]):
        """Chamado a cada quadro novo da câmera."""

    def tick(self, dt: float):
        """Chamado a 60 fps para animar, mesmo entre quadros da câmera."""

    def draw(self, p: QPainter):
        """Desenha por cima do vídeo."""
