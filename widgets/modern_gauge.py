# -*- coding: utf-8 -*-
"""
ModernGauge — Smooth animated arc gauge.

Methods expected by main.py:
  ModernGauge(label, color)
  .setValue(int 0-100)
"""

import math
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont
from PySide6.QtWidgets import QWidget


class ModernGauge(QWidget):
    """
    Circular arc gauge with smooth eased animation.
    Arc sweeps from ~210° (bottom-left) clockwise to ~-30° (bottom-right).
    Total sweep = 240°.
    """

    def __init__(self, label: str, color: QColor, parent=None):
        super().__init__(parent)
        self.setMinimumSize(100, 100)

        self._label  = label
        self._color  = color
        self._target = 0.0       # target value  0-100
        self._value  = 0.0       # animated value 0-100

        # smooth animation
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)    # ~60 fps

        # tick counter for idle shimmer
        self._tick_count = 0

    # ── public API ────────────────────────────────────────────────────────────

    def setValue(self, v: int):
        self._target = max(0.0, min(100.0, float(v)))

    # ── animation ─────────────────────────────────────────────────────────────

    def _tick(self):
        self._tick_count += 1
        diff = self._target - self._value
        if abs(diff) > 0.05:
            # ease-out factor — fast approach, smooth landing
            self._value += diff * 0.12
            self.update()
        elif abs(diff) > 0.001:
            self._value = self._target
            self.update()
        # idle shimmer pulse (even when value is stable)
        if self._tick_count % 2 == 0:
            self.update()

    # ── paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        side   = min(self.width(), self.height())
        margin = side * 0.10
        rect   = QRectF(
            (self.width()  - side) / 2 + margin,
            (self.height() - side) / 2 + margin,
            side - 2 * margin,
            side - 2 * margin,
        )
        cx = rect.center().x()
        cy = rect.center().y()
        r  = rect.width() / 2

        START_DEG = 225    # Qt angles: 0=3 o'clock, counter-clockwise positive
        SPAN_DEG  = -270   # we sweep 270° clockwise (negative in Qt)

        frac = self._value / 100.0

        # ── track (background arc) ────────────────────────────────────
        track_pen = QPen(QColor("#1c1c28"), int(side * 0.065), Qt.SolidLine)
        track_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(track_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(rect, int(START_DEG * 16), int(SPAN_DEG * 16))

        # ── tick marks ───────────────────────────────────────────────
        self._draw_ticks(painter, cx, cy, r, side)

        # ── filled arc ───────────────────────────────────────────────
        if frac > 0.001:
            arc_pen = QPen(self._color, int(side * 0.065), Qt.SolidLine)
            arc_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(arc_pen)
            painter.drawArc(rect, int(START_DEG * 16),
                            int(SPAN_DEG * frac * 16))

            # glow layer — slightly wider, very transparent
            glow_color = QColor(self._color)
            glow_color.setAlpha(40)
            glow_pen = QPen(glow_color, int(side * 0.13), Qt.SolidLine)
            glow_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(glow_pen)
            painter.drawArc(rect, int(START_DEG * 16),
                            int(SPAN_DEG * frac * 16))

        # ── needle tip dot ────────────────────────────────────────────
        needle_angle_deg = START_DEG + SPAN_DEG * frac
        needle_angle_rad = math.radians(needle_angle_deg)
        tip_x = cx + r * math.cos(needle_angle_rad)
        tip_y = cy - r * math.sin(needle_angle_rad)
        dot_r = side * 0.045
        painter.setPen(Qt.NoPen)
        # glow
        glow2 = QColor(self._color)
        glow2.setAlpha(80)
        painter.setBrush(QBrush(glow2))
        painter.drawEllipse(QPointF(tip_x, tip_y), dot_r * 2.2, dot_r * 2.2)
        # solid dot
        painter.setBrush(QBrush(self._color))
        painter.drawEllipse(QPointF(tip_x, tip_y), dot_r, dot_r)

        # ── centre value text ─────────────────────────────────────────
        val_font = QFont("Consolas", int(side * 0.18))
        val_font.setBold(True)
        painter.setFont(val_font)
        painter.setPen(QPen(self._color, 1))
        painter.drawText(
            QRectF(cx - r, cy - r * 0.35, r * 2, r * 0.7),
            Qt.AlignCenter,
            f"{int(self._value)}"
        )

        # ── label & percent sign ──────────────────────────────────────
        lbl_font = QFont("Consolas", int(side * 0.085))
        painter.setFont(lbl_font)
        painter.setPen(QPen(QColor("#888898"), 1))
        painter.drawText(
            QRectF(cx - r, cy + r * 0.22, r * 2, r * 0.4),
            Qt.AlignCenter,
            f"{self._label}  %"
        )

        # ── 0 / 100 markers ───────────────────────────────────────────
        mark_font = QFont("Consolas", max(6, int(side * 0.07)))
        painter.setFont(mark_font)
        painter.setPen(QPen(QColor("#444455"), 1))
        # 0 marker: angle = START_DEG
        a0 = math.radians(START_DEG)
        x0 = cx + (r + side * 0.09) * math.cos(a0)
        y0 = cy - (r + side * 0.09) * math.sin(a0)
        painter.drawText(QRectF(x0 - 12, y0 - 8, 24, 16), Qt.AlignCenter, "0")
        # 100 marker: angle = START_DEG + SPAN_DEG
        a1 = math.radians(START_DEG + SPAN_DEG)
        x1 = cx + (r + side * 0.09) * math.cos(a1)
        y1 = cy - (r + side * 0.09) * math.sin(a1)
        painter.drawText(QRectF(x1 - 16, y1 - 8, 32, 16), Qt.AlignCenter, "100")

        painter.end()

    def _draw_ticks(self, painter: QPainter, cx, cy, r, side):
        """Draw subtle tick marks around the arc."""
        START_DEG = 225
        SPAN_DEG  = -270
        n_major = 10
        n_minor = 5   # minor ticks between each major

        total_ticks = n_major * n_minor
        for i in range(total_ticks + 1):
            frac   = i / total_ticks
            angle  = math.radians(START_DEG + SPAN_DEG * frac)
            is_major = (i % n_minor == 0)

            outer_r = r - side * 0.07
            inner_r = outer_r - (side * 0.055 if is_major else side * 0.025)

            ox = cx + outer_r * math.cos(angle)
            oy = cy - outer_r * math.sin(angle)
            ix = cx + inner_r * math.cos(angle)
            iy = cy - inner_r * math.sin(angle)

            color = QColor("#333345" if is_major else "#222230")
            painter.setPen(QPen(color, 1 if is_major else 0.5))
            painter.drawLine(QPointF(ox, oy), QPointF(ix, iy))
