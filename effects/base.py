from PySide6.QtGui import QImage, QPainter

from gestures import HandPose


class Effect:
    """Contrato dos efeitos. Todas as coordenadas estão em pixels do quadro da câmera."""

    name = ""
    # conteúdo de um SVG 24x24 com traço, no estilo Lucide
    icon = ""
    # efeitos que filtram a imagem recebem cada quadro em set_frame
    wants_frame = False

    def set_frame(self, frame: QImage):
        """Chamado a cada quadro novo, antes de set_hands, só se wants_frame for verdadeiro."""

    def set_hands(self, poses: list[HandPose]):
        """Chamado a cada quadro novo da câmera."""

    def tick(self, dt: float):
        """Chamado a 60 fps para animar, mesmo entre quadros da câmera."""

    def draw(self, p: QPainter):
        """Desenha por cima do vídeo."""

    def close(self):
        """Chamado quando o efeito é desligado, para liberar threads ou recursos."""

    @property
    def dim(self) -> float:
        """De 0 a 1, quanto o vídeo escurece por baixo do efeito."""
        return 0.0

    @property
    def idle(self) -> bool:
        """Verdadeiro quando não há nada animando, para a tela não repintar à toa."""
        return False
