import math

import numpy as np
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainter, QPen

from effects.base import Effect
from effects.render import draw_glow, mono_font, point
from gestures import THUMB_TIP, INDEX_MCP, HandPose

CLOUD_SIZE = 240
LABELED_RATIO = 0.25
COMPACT_LABELS = 7

FLICK_SPEED = 1500
FLICK_ALIGNMENT = 0.5
FLIGHT_TIME = 0.4
TRANSFER_COOLDOWN = 0.6
BALL_FOLLOW = 22.0
EXPAND_SPEED = 5.0

ASCII = list("+*:.=#%-~<>|")


def _rotate(vectors: np.ndarray, radians: float) -> np.ndarray:
    c, s = math.cos(radians), math.sin(radians)
    return vectors @ np.array([[c, s], [-s, c]])


class EnergyBall(Effect):
    """Orbe de luz na ponta do indicador.

    Peteleco na direção da outra mão lança a bola até ela.
    L com as duas mãos abre a bola numa nuvem com um anel entre as mãos.
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
        self._core: np.ndarray | None = None
        self._visible = 0.0

        self._expand = 0.0
        self._expand_target = 0.0
        self._frame_target: tuple[np.ndarray, np.ndarray, float] | None = None
        self._center: np.ndarray | None = None
        self._axes = np.array([1.0, 1.0])
        self._angle = 0.0

        self._build_cloud()
        self._sparks = np.zeros((0, 5))
        self._label_clock = 0.0

    def _build_cloud(self):
        rng, n = self._rng, CLOUD_SIZE
        self._compact = rng.normal(0, 1, (n, 2)) * 16
        radius = np.sqrt(rng.uniform(0.05, 1, n)) * rng.uniform(0.7, 1.45, n)
        angle = rng.uniform(0, 2 * math.pi, n)
        self._spread = np.stack([np.cos(angle) * radius, np.sin(angle) * radius], axis=1)
        self._stiffness = rng.uniform(5, 14, n)[:, None]
        self._phase = rng.uniform(0, 2 * math.pi, n)
        big = rng.random(n) < 0.12
        self._size = np.where(big, rng.uniform(9, 15, n), rng.uniform(2.5, 6, n))
        self._labeled = np.nonzero(rng.random(n) < LABELED_RATIO)[0]
        self._labels = {int(i): self._random_label() for i in self._labeled}
        self._particles: np.ndarray | None = None

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
        self._poses = {pose.id: pose for pose in poses}

        if self._owner not in self._poses:
            self._owner = None
        if self._flight and self._flight["target"] not in self._poses:
            self._flight = None

        if self._owner is None and self._flight is None:
            pointing = [pose for pose in poses if pose.pointing]
            if pointing:
                if self._ball is None:
                    self._owner = pointing[0].id
                else:
                    self._owner = min(pointing, key=lambda pose: np.linalg.norm(pose.index_tip - self._ball)).id

        self._check_flick()
        self._read_frame_gesture(poses)

    def _check_flick(self):
        owner = self._poses.get(self._owner)
        if owner is None or self._flight or self._cooldown > 0 or self._expand > 0.3 or self._ball is None:
            return
        others = [pose for pose in self._poses.values() if pose.id != owner.id]
        speed = float(np.linalg.norm(owner.velocity))
        if not others or speed < FLICK_SPEED:
            return

        target = min(others, key=lambda pose: np.linalg.norm(pose.index_tip - owner.index_tip))
        direction = target.index_tip - owner.index_tip
        distance = float(np.linalg.norm(direction))
        if distance < 1 or float(np.dot(owner.velocity / speed, direction / distance)) < FLICK_ALIGNMENT:
            return

        self._flight = {"start": self._ball.copy(), "target": target.id, "t": 0.0}
        self._owner = None

    def _read_frame_gesture(self, poses: list[HandPose]):
        framing = [pose for pose in poses if pose.l_shape]
        if len(framing) < 2:
            self._expand_target = 0.0
            return
        a, b = framing[:2]
        center = np.mean([a.index_tip, a.points[THUMB_TIP], b.index_tip, b.points[THUMB_TIP]], axis=0)
        line = b.points[INDEX_MCP] - a.points[INDEX_MCP]
        span = max(float(np.linalg.norm(line)), 40.0)
        angle = math.atan2(line[1], line[0])
        if angle > math.pi / 2:
            angle -= math.pi
        elif angle < -math.pi / 2:
            angle += math.pi
        self._frame_target = (center, np.array([span * 0.42, span * 0.58]), angle)
        self._expand_target = 1.0

    @staticmethod
    def _tip_anchor(pose: HandPose) -> np.ndarray:
        return pose.index_tip + pose.index_direction * pose.palm * 0.18

    # animação

    def tick(self, dt: float):
        self._time += dt
        self._cooldown = max(0.0, self._cooldown - dt)
        previous = None if self._ball is None else self._ball.copy()

        self._move_ball(dt)
        if self._ball is None:
            return

        active = self._owner is not None or self._flight is not None
        target = 1.0 if active else 0.0
        rate = 6.0 if target > self._visible else 1.5
        self._visible += (target - self._visible) * (1 - math.exp(-dt * rate))

        self._update_expansion(dt)
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
            return

        owner = self._poses.get(self._owner)
        if owner is None:
            return
        anchor = self._tip_anchor(owner)
        if self._ball is None:
            self._ball = anchor.copy()
        else:
            self._ball += (anchor - self._ball) * (1 - math.exp(-dt * BALL_FOLLOW))

    def _update_expansion(self, dt: float):
        self._expand += (self._expand_target - self._expand) * (1 - math.exp(-dt * EXPAND_SPEED))
        if self._frame_target is not None:
            center, axes, angle = self._frame_target
            if self._center is None:
                self._center, self._axes, self._angle = center.copy(), axes.copy(), angle
            k = 1 - math.exp(-dt * 12)
            self._center += (center - self._center) * k
            self._axes += (axes - self._axes) * k
            self._angle += (angle - self._angle) * k

        if self._center is None:
            self._core = self._ball
        else:
            self._core = self._ball + (self._center - self._ball) * self._expand

    def _update_particles(self, dt: float):
        breathing = 1 + 0.25 * np.sin(self._time * 2.4 + self._phase)
        home = self._core + self._compact * breathing[:, None]

        if self._center is not None and self._expand > 0.001:
            cloud = _rotate(self._spread, self._time * 0.18) * self._axes
            cloud = _rotate(cloud, self._angle) + self._center
            drift = np.stack(
                [np.sin(self._time * 0.9 + self._phase), np.cos(self._time * 0.7 + self._phase * 1.3)], axis=1
            ) * 6
            home = home * (1 - self._expand) + (cloud + drift) * self._expand

        if self._particles is None:
            self._particles = home.copy()
        else:
            self._particles += (home - self._particles) * (1 - np.exp(-dt * self._stiffness))

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
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        twinkle = 0.55 + 0.45 * np.sin(self._time * 5 + self._phase)
        for (x, y), size, shine in zip(self._particles, self._size, twinkle):
            draw_glow(p, x, y, size, visible * shine * 0.9)

        for x, y, _, _, life in self._sparks:
            draw_glow(p, x, y, 3.5, visible * min(life * 2, 1.0) * 0.8)

        if expand > 0.02 and self._center is not None:
            self._draw_ring(p, visible * expand)

        self._draw_labels(p, visible, expand)

        bloom = 70 + 6 * math.sin(self._time * 7)
        draw_glow(p, self._core[0], self._core[1], bloom, visible * 0.55)
        draw_glow(p, self._core[0], self._core[1], 26, visible)
        draw_glow(p, self._core[0], self._core[1], 12, visible)
        p.restore()

    def _draw_ring(self, p: QPainter, strength: float):
        p.save()
        p.setOpacity(strength)
        p.translate(point(self._center))
        p.rotate(math.degrees(self._angle))
        rx, ry = float(self._axes[0]), float(self._axes[1])
        for width, alpha in ((6, 45), (1.4, 230)):
            p.setPen(QPen(QColor(255, 255, 255, alpha), width))
            p.drawEllipse(QPointF(0, 0), rx, ry)
        p.restore()

    def _draw_labels(self, p: QPainter, visible: float, expand: float):
        p.setFont(mono_font(10))
        for order, index in enumerate(self._labeled):
            strength = visible * (1.0 if order < COMPACT_LABELS else expand) * 0.85
            if strength < 0.02:
                continue
            x, y = self._particles[index]
            size = float(self._size[index])
            p.setOpacity(strength)
            p.setPen(QPen(QColor(255, 255, 255, 200), 1))
            if size > 8:
                p.drawEllipse(QPointF(x, y), size * 0.9, size * 0.9)
            p.drawText(QPointF(x + size + 3, y + 3), self._labels[int(index)])
