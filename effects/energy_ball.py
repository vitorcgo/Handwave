import math

import numpy as np
from PySide6.QtCore import QLineF, QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QStaticText

from effects.base import Effect
from effects.render import DEEP, ICE, WHITE, draw_glow, mono_font
from gestures import HandPose

CLOUD_SIZE = 360
LABELED_RATIO = 0.12
COMPACT_LABELS = 6
COMPACT_RADIUS = 30

FLICK_SPEED = 700
FLICK_ALIGNMENT = 0.35
FLIGHT_TIME = 0.4
TRANSFER_COOLDOWN = 0.6
BALL_FOLLOW = 22.0

RELEASE_TIME = 0.7
LINK_DISTANCE = 0.38
LINKS_PER_POINT = 2
LINK_LEVELS = 4

EXPAND_SPEED = 5.0
EXPAND_HOLD = 0.4
EXPAND_MIN = 120
EXPAND_MAX = 380
DISK_TILT = 1.15
ROTATION_GAIN = 1.6

TINTS = (WHITE, ICE, DEEP)
ASCII = list("+*:.=#%-~<>|")


def _wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def _orbit(radius, theta, height, tilt, node):
    """Posição 3D de cada partícula na sua órbita, já girada pelo plano da órbita."""
    x = radius * np.cos(theta)
    y = radius * np.sin(theta)
    z = height
    y, z = y * np.cos(tilt) - z * np.sin(tilt), y * np.sin(tilt) + z * np.cos(tilt)
    x, y = x * np.cos(node) - y * np.sin(node), x * np.sin(node) + y * np.cos(node)
    return np.stack([x, y], axis=1), z


class EnergyBall(Effect):
    """Orbe de partículas na ponta do indicador.

    Peteleco na direção da outra mão lança a bola até ela.
    L com a outra mão abre a bola num disco de partículas; girar o L gira o disco
    e a distância entre as mãos define o tamanho.
    Fechar a mão que segura a bola apaga a bola; apontar de novo acende.
    """

    name = "Bola de energia"
    icon = (
        '<circle cx="12" cy="12" r="3"/><circle cx="19" cy="5" r="2"/><circle cx="5" cy="19" r="2"/>'
        '<path d="M10.4 21.9a10 10 0 0 0 9.941-15.416"/><path d="M13.5 2.1a10 10 0 0 0-9.841 15.416"/>'
    )

    def __init__(self):
        self._rng = np.random.default_rng()
        self._poses: dict[int, HandPose] = {}
        self._owner: int | None = None
        self._flight: dict | None = None
        self._cooldown = 0.0
        self._time = 0.0

        self._ball: np.ndarray | None = None
        self._visible = 0.0
        self._release_clock = 0.0

        self._expand = 0.0
        self._expand_target = 0.0
        self._radius = float(EXPAND_MIN)
        self._radius_target = float(EXPAND_MIN)
        self._rotation = 0.0
        self._rotation_target = 0.0
        self._grip: tuple[float, float] | None = None
        self._frame_id: int | None = None
        self._expand_hold = 0.0

        self._build_cloud()
        self._sparks = np.zeros((0, 5))
        self._label_clock = 0.0
        self._text_cache: dict[str, QStaticText] = {}

    def _build_cloud(self):
        rng, n = self._rng, CLOUD_SIZE
        dust = rng.random(n) < 0.15
        self._r = np.where(dust, rng.uniform(1.0, 1.5, n), 0.1 + 0.9 * rng.random(n) ** 1.6)
        self._theta = rng.uniform(0, 2 * math.pi, n)
        self._height = rng.normal(0, 0.06, n)

        # fechada: órbitas em planos aleatórios formam uma esfera
        self._spin_compact = rng.choice([-1, 1], n) * rng.uniform(1.5, 3.0, n)
        self._tilt_compact = np.arccos(rng.uniform(-1, 1, n))
        self._node_compact = rng.uniform(0, 2 * math.pi, n)
        # aberta: todas no mesmo disco, as de dentro girando mais rápido
        self._spin_disk = 0.35 + 0.6 / (self._r + 0.3)

        self._stiffness = rng.uniform(12, 26, n)[:, None]
        self._phase = rng.uniform(0, 2 * math.pi, n)
        kind = rng.random(n)
        self._size = np.select(
            [kind < 0.70, kind < 0.94], [rng.uniform(1.8, 3.5, n), rng.uniform(4, 7, n)], rng.uniform(9, 14, n)
        )
        self._tint = rng.choice(len(TINTS), n, p=[0.55, 0.3, 0.15])

        candidates = np.nonzero(self._size > 4)[0]
        count = max(int(n * LABELED_RATIO), 1)
        self._labeled = rng.choice(candidates, size=min(count, len(candidates)), replace=False)
        self._labels = {int(i): self._random_label() for i in self._labeled}
        self._particles: np.ndarray | None = None
        self._depth = np.zeros(n)

    def _random_label(self) -> str:
        r = self._rng
        kind = r.integers(0, 4)
        if kind == 0:
            return f"#{r.integers(1000, 9999)}"
        if kind == 1:
            return f"0x{r.integers(0, 0xFFF):03X}"
        if kind == 2:
            return "".join(r.choice(ASCII, size=r.integers(2, 5)))
        return f"[{r.integers(0, 999)},{r.integers(0, 999)}]"

    # entrada

    def set_hands(self, poses: list[HandPose]):
        last_owner = self._poses.get(self._owner)
        self._poses = {pose.id: pose for pose in poses}

        if self._owner not in self._poses:
            self._owner = None
            # a mão some no meio de um peteleco rápido; o último movimento dela ainda vale
            if last_owner is not None:
                self._check_flick(last_owner)
        if self._flight and self._flight["target"] not in self._poses:
            self._flight = None

        if self._owner is None and self._flight is None:
            pointing = [pose for pose in poses if pose.pointing]
            if pointing:
                if self._ball is None:
                    self._owner = pointing[0].id
                else:
                    self._owner = min(pointing, key=lambda pose: np.linalg.norm(pose.index_tip - self._ball)).id

        owner = self._poses.get(self._owner)
        if owner is not None:
            self._check_flick(owner)
        self._read_expansion(owner, poses)

    def _check_flick(self, owner: HandPose):
        if self._flight or self._cooldown > 0 or self._expand > 0.3 or self._ball is None:
            return
        others = [pose for pose in self._poses.values() if pose.id != owner.id]
        velocity = owner.peak_velocity
        speed = float(np.linalg.norm(velocity))
        if not others or speed < FLICK_SPEED:
            return

        target = min(others, key=lambda pose: np.linalg.norm(pose.index_tip - owner.index_tip))
        direction = target.index_tip - owner.index_tip
        distance = float(np.linalg.norm(direction))
        if distance < 1 or float(np.dot(velocity / speed, direction / distance)) < FLICK_ALIGNMENT:
            return

        self._flight = {"start": self._ball.copy(), "target": target.id, "t": 0.0}
        self._owner = None

    def _read_expansion(self, owner: HandPose | None, poses: list[HandPose]):
        framing = [pose for pose in poses if owner is not None and pose.id != owner.id and pose.l_shape]
        if framing:
            frame = framing[0]
            self._frame_id = frame.id
            self._expand_hold = EXPAND_HOLD
        elif owner is not None and self._expand_hold > 0:
            # o L falhou por um instante; enquanto a mesma mão estiver na tela, o disco continua aberto
            frame = self._poses.get(self._frame_id)
        else:
            frame = None

        if frame is None or owner is None:
            if self._expand_hold <= 0:
                self._expand_target = 0.0
                self._grip = None
            return

        spread = float(np.linalg.norm(frame.index_tip - owner.index_tip))
        self._radius_target = float(np.clip(spread * 0.55, EXPAND_MIN, EXPAND_MAX))

        # a mão do L funciona como um botão giratório: o quanto ela gira desde que o L começou
        direction = frame.index_direction
        angle = math.atan2(direction[1], direction[0])
        if self._grip is None:
            self._grip = (angle, self._rotation_target)
        start_angle, start_rotation = self._grip
        self._rotation_target = start_rotation + _wrap(angle - start_angle) * ROTATION_GAIN
        self._expand_target = 1.0

    @staticmethod
    def _tip_anchor(pose: HandPose) -> np.ndarray:
        return pose.index_tip + pose.index_direction * pose.palm * 0.18

    @property
    def dim(self) -> float:
        # a luz aditiva estoura em fundo claro, então o vídeo escurece conforme a bola acende
        return self._visible

    @property
    def idle(self) -> bool:
        return self._visible < 0.005 and not len(self._sparks) and self._owner is None and self._flight is None

    # animação

    def tick(self, dt: float):
        self._time += dt
        self._cooldown = max(0.0, self._cooldown - dt)
        self._expand_hold = max(0.0, self._expand_hold - dt)
        if self._expand_hold <= 0 and self._expand_target > 0 and self._owner is None:
            self._expand_target = 0.0
            self._grip = None
        self._check_release(dt)
        previous = None if self._ball is None else self._ball.copy()

        self._move_ball(dt)
        if self._ball is None:
            return

        active = self._owner is not None or self._flight is not None
        target = 1.0 if active else 0.0
        rate = 6.0 if target > self._visible else 1.5
        self._visible += (target - self._visible) * (1 - math.exp(-dt * rate))

        k = 1 - math.exp(-dt * EXPAND_SPEED)
        self._expand += (self._expand_target - self._expand) * k
        k = 1 - math.exp(-dt * 10)
        self._radius += (self._radius_target - self._radius) * k
        self._rotation += (self._rotation_target - self._rotation) * k

        self._update_particles(dt)
        self._update_sparks(dt, previous)
        self._refresh_labels(dt)

    def _move_ball(self, dt: float):
        if self._flight:
            flight = self._flight
            target = self._poses.get(flight["target"])
            if target is None:
                self._flight = None
                return
            flight["t"] = min(flight["t"] + dt / FLIGHT_TIME, 1.0)
            t = 1 - (1 - flight["t"]) ** 3
            start, end = flight["start"], self._tip_anchor(target)
            lift = np.array([0.0, -0.18 * float(np.linalg.norm(end - start))])
            control = (start + end) / 2 + lift
            self._ball = (1 - t) ** 2 * start + 2 * (1 - t) * t * control + t ** 2 * end
            if flight["t"] >= 1.0:
                self._owner = flight["target"]
                self._flight = None
                self._cooldown = TRANSFER_COOLDOWN
                self._burst(self._ball, 26, 200)
            return

        owner = self._poses.get(self._owner)
        if owner is None:
            return
        anchor = self._tip_anchor(owner)
        if self._ball is None or self._visible < 0.05:
            # acende direto no dedo, sem atravessar a tela vindo de onde apagou
            self._ball = anchor.copy()
            self._particles = None
            self._burst(anchor, 40, 260)
        else:
            self._ball += (anchor - self._ball) * (1 - math.exp(-dt * BALL_FOLLOW))

    def _check_release(self, dt: float):
        owner = self._poses.get(self._owner)
        if owner is None or owner.pointing or self._expand_target > 0:
            self._release_clock = 0.0
            return
        self._release_clock += dt
        if self._release_clock >= RELEASE_TIME:
            self._owner = None
            self._release_clock = 0.0

    def _burst(self, origin: np.ndarray, count: int, speed: float):
        angle = self._rng.uniform(0, 2 * math.pi, count)
        velocity = self._rng.uniform(0.3, 1.0, count) * speed
        burst = np.zeros((count, 5))
        burst[:, :2] = origin
        burst[:, 2] = np.cos(angle) * velocity
        burst[:, 3] = np.sin(angle) * velocity
        burst[:, 4] = self._rng.uniform(0.35, 0.8, count)
        self._sparks = np.vstack([self._sparks, burst])

    def _update_particles(self, dt: float):
        t, e = self._time, self._expand
        breathing = 1 + 0.12 * np.sin(t * 2.2 + self._phase)

        compact, compact_z = _orbit(
            self._r * 0.8 + 0.2, self._theta + self._spin_compact * t, 0, self._tilt_compact, self._node_compact
        )
        compact = compact * (COMPACT_RADIUS * breathing)[:, None]
        target, depth = compact, compact_z / 1.0

        if e > 0.001:
            disk, disk_z = _orbit(self._r, self._theta + self._spin_disk * t, self._height, DISK_TILT, self._rotation)
            disk = disk * self._radius
            target = compact * (1 - e) + disk * e
            depth = compact_z * (1 - e) + disk_z / 1.5 * e

        target = target + self._ball
        self._depth = np.clip(depth, -1, 1)
        if self._particles is None:
            self._particles = target.copy()
        else:
            self._particles += (target - self._particles) * (1 - np.exp(-dt * self._stiffness))

    def _update_sparks(self, dt: float, previous: np.ndarray | None):
        if previous is not None and dt > 0:
            velocity = (self._ball - previous) / dt
            speed = float(np.linalg.norm(velocity))
            if speed > 400:
                count = min(int(speed * dt * 0.15) + 1, 8)
                spawn = np.zeros((count, 5))
                spawn[:, :2] = self._ball + self._rng.normal(0, 4, (count, 2))
                spawn[:, 2:4] = -velocity * 0.08 + self._rng.normal(0, 60, (count, 2))
                spawn[:, 4] = self._rng.uniform(0.4, 0.9, count)
                self._sparks = np.vstack([self._sparks, spawn])

        if len(self._sparks):
            self._sparks[:, :2] += self._sparks[:, 2:4] * dt
            self._sparks[:, 2:4] *= math.exp(-dt * 2.5)
            self._sparks[:, 4] -= dt
            self._sparks = self._sparks[self._sparks[:, 4] > 0]

    def _refresh_labels(self, dt: float):
        self._label_clock += dt
        if self._label_clock < 0.35 or not len(self._labeled):
            return
        self._label_clock = 0.0
        for index in self._rng.choice(self._labeled, size=min(3, len(self._labeled)), replace=False):
            self._labels[int(index)] = self._random_label()

    # desenho

    def draw(self, p: QPainter):
        if self._particles is None or self._visible < 0.01:
            return
        visible, expand = self._visible, self._expand

        p.save()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # partículas mais perto da câmera ficam maiores e mais fortes
        near = (self._depth + 1) / 2
        twinkle = 0.6 + 0.4 * np.sin(self._time * 5 + self._phase)
        strength = visible * twinkle * (0.45 + 0.55 * near)
        scale = 0.75 + 0.5 * near
        for (x, y), size, tint, power, grow in zip(self._particles, self._size, self._tint, strength, scale):
            if power > 0.03:
                draw_glow(p, x, y, size * grow, power, TINTS[tint])

        for x, y, _, _, life in self._sparks:
            draw_glow(p, x, y, 3.5, min(life * 2, 1.0) * 0.8)

        if expand > 0.05:
            self._draw_links(p, visible * expand)
        self._draw_labels(p, visible, expand, near)

        x, y = self._ball
        bloom = 58 + 5 * math.sin(self._time * 7) + 30 * expand
        draw_glow(p, x, y, bloom, visible * 0.45, ICE)
        draw_glow(p, x, y, 22, visible)
        draw_glow(p, x, y, 10, visible)
        p.restore()

    def _draw_links(self, p: QPainter, strength: float):
        """Liga cada partícula com número às vizinhas mais próximas, como uma rede de dados."""
        points = self._particles[self._labeled]
        limit = self._radius * LINK_DISTANCE
        distance = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=2)
        np.fill_diagonal(distance, np.inf)
        nearest = np.argsort(distance, axis=1)[:, :LINKS_PER_POINT]

        # linhas agrupadas por transparência, desenhadas em lote
        groups: list[list[QLineF]] = [[] for _ in range(LINK_LEVELS)]
        seen = set()
        for a, row in enumerate(nearest):
            for b in row:
                d = distance[a, b]
                if d >= limit or (b, a) in seen:
                    continue
                seen.add((a, b))
                level = min(int((1 - d / limit) * LINK_LEVELS), LINK_LEVELS - 1)
                groups[level].append(QLineF(*points[a], *points[b]))

        p.setPen(QPen(QColor(*ICE, 255), 0.8))
        for level, lines in enumerate(groups):
            if lines:
                p.setOpacity(strength * 0.4 * (level + 1) / LINK_LEVELS)
                p.drawLines(lines)

    def _draw_labels(self, p: QPainter, visible: float, expand: float, near: np.ndarray):
        p.setFont(mono_font(10))
        p.setPen(QPen(QColor(220, 232, 255, 210), 1))
        for order, index in enumerate(self._labeled):
            strength = visible * (1.0 if order < COMPACT_LABELS else expand) * (0.35 + 0.65 * near[index])
            if strength < 0.03:
                continue
            x, y = self._particles[index]
            size = float(self._size[index])
            p.setOpacity(strength * 0.85)
            if size > 8:
                p.drawEllipse(QPointF(x, y), size * 0.8, size * 0.8)
            p.drawStaticText(QPointF(x + size * 0.6 + 4, y - 6), self._static_text(self._labels[int(index)]))

    def _static_text(self, text: str) -> QStaticText:
        # texto pré-calculado; refazer o layout de cada número a 60 fps pesa
        cached = self._text_cache.get(text)
        if cached is None:
            cached = QStaticText(text)
            cached.prepare(font=mono_font(10))
            if len(self._text_cache) > 400:
                self._text_cache.clear()
            self._text_cache[text] = cached
        return cached
