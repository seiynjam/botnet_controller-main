# -*- coding: utf-8 -*-
"""
EnhancedNetworkChart — Smooth scrolling network-traffic sparkline chart.

Methods expected by main.py:
  EnhancedNetworkChart()
  .step()          — called every second to advance the chart
"""

import math
import random
import time
from collections import deque
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont,
    QPainterPath, QLinearGradient
)
from PySide6.QtWidgets import QWidget


# ── palette ───────────────────────────────────────────────────────────────────
C_BG        = QColor("#0a0a0d")
C_GRID      = QColor("#16161e")
C_TX        = QColor("#ff3030")    # TX line (send)
C_RX        = QColor("#00ff88")    # RX line (receive)
C_TX_FILL   = QColor(255, 48, 48, 35)
C_RX_FILL   = QColor(0, 255, 136, 30)
C_AXIS      = QColor("#2a2a38")
C_LABEL     = QColor("#888898")
C_VALUE     = QColor("#cccccc")


def _smooth(series: deque, window: int = 3) -> list:
    """Simple moving-average smoothing."""
    data = list(series)
    out  = []
    for i, v in enumerate(data):
        lo  = max(0, i - window)
        hi  = min(len(data), i + window + 1)
        out.append(sum(data[lo:hi]) / (hi - lo))
    return out


class EnhancedNetworkChart(QWidget):
    """
    Dual-line (TX / RX) scrolling chart with:
    - smooth interpolated curves (QPainterPath cubic)
    - gradient fill under each line
    - sub-frame animation so the chart scrolls smoothly between .step() calls
    - grid, axis labels, live value readouts
    """

    HISTORY = 60          # seconds of history kept
    SCROLL_FPS = 60       # sub-frame scroll animation rate

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(150, 80)

        self._tx: deque = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)
        self._rx: deque = deque([0.0] * self.HISTORY, maxlen=self.HISTORY)

        # sub-frame scroll offset (0.0 → 1.0 per second)
        self._scroll_phase = 0.0
        self._last_step_t  = time.monotonic()

        # peak for auto-scale (with slow decay)
        self._peak = 1000.0

        # animation timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(1000 // self.SCROLL_FPS)

        # shimmer phase
        self._shimmer = 0.0

    # ── public API ────────────────────────────────────────────────────────────

    def step(self):
        """Called every ~1 s from main.py to push a new sample."""
        import psutil
        try:
            counters = psutil.net_io_counters()
            if not hasattr(self, '_prev_net'):
                self._prev_net = counters
            tx_bps = max(0, counters.bytes_sent - self._prev_net.bytes_sent)
            rx_bps = max(0, counters.bytes_recv - self._prev_net.bytes_recv)
            self._prev_net = counters
        except Exception:
            # fallback: random demo data
            tx_bps = random.uniform(100, 3000) * 1024
            rx_bps = random.uniform(50,  2000) * 1024

        # convert to KB/s
        tx_kb = tx_bps / 1024
        rx_kb = rx_bps / 1024

        self._tx.append(tx_kb)
        self._rx.append(rx_kb)

        # slowly decay peak so scale adapts
        cur_peak = max(max(self._tx), max(self._rx), 1.0)
        self._peak = max(self._peak * 0.95, cur_peak * 1.15)

        self._last_step_t = time.monotonic()
        self._scroll_phase = 0.0   # reset sub-frame phase

    # ── animation ─────────────────────────────────────────────────────────────

    def _animate(self):
        elapsed = time.monotonic() - self._last_step_t
        self._scroll_phase = min(elapsed, 1.0)
        self._shimmer = (self._shimmer + 0.04) % (2 * math.pi)
        self.update()

    # ── paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        W, H = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 46, 12, 14, 28

        plot_x = pad_l
        plot_y = pad_t
        plot_w = W - pad_l - pad_r
        plot_h = H - pad_t - pad_b

        if plot_w < 10 or plot_h < 10:
            painter.end()
            return

        painter.fillRect(self.rect(), C_BG)

        self._draw_grid(painter, plot_x, plot_y, plot_w, plot_h)
        self._draw_series(painter, plot_x, plot_y, plot_w, plot_h,
                          list(self._tx), C_TX, C_TX_FILL, "TX")
        self._draw_series(painter, plot_x, plot_y, plot_w, plot_h,
                          list(self._rx), C_RX, C_RX_FILL, "RX")
        self._draw_axes(painter, plot_x, plot_y, plot_w, plot_h)
        self._draw_legend(painter, plot_x, plot_y, plot_w)
        self._draw_live_values(painter, W, H)

        painter.end()

    def _draw_grid(self, p, px, py, pw, ph):
        pen = QPen(C_GRID, 1, Qt.SolidLine)
        p.setPen(pen)
        n_h = 4
        for i in range(1, n_h):
            y = py + ph * i / n_h
            p.drawLine(QPointF(px, y), QPointF(px + pw, y))
        # vertical grid lines
        n_v = 6
        for i in range(1, n_v):
            # offset by scroll phase so lines glide
            frac = (i / n_v - self._scroll_phase / n_v) % 1.0
            x = px + pw * frac
            p.drawLine(QPointF(x, py), QPointF(x, py + ph))

    def _draw_axes(self, p, px, py, pw, ph):
        p.setPen(QPen(C_AXIS, 1))
        p.drawLine(QPointF(px, py), QPointF(px, py + ph))
        p.drawLine(QPointF(px, py + ph), QPointF(px + pw, py + ph))

        # Y-axis labels (KB/s)
        font = QFont("Consolas", 7)
        p.setFont(font)
        p.setPen(QPen(C_LABEL, 1))
        n_labels = 4
        for i in range(n_labels + 1):
            frac = i / n_labels
            val  = self._peak * (1 - frac)
            y    = py + ph * frac
            label = f"{int(val)}" if val < 10000 else f"{val/1024:.1f}M"
            p.drawText(QRectF(0, y - 8, px - 4, 16),
                       Qt.AlignRight | Qt.AlignVCenter, label)

        # X-axis label
        p.drawText(QRectF(px, py + ph + 4, pw, 14),
                   Qt.AlignRight, "60s")
        p.drawText(QRectF(px, py + ph + 4, pw, 14),
                   Qt.AlignLeft, "0s")

    def _draw_series(self, p, px, py, pw, ph,
                     data: list, color: QColor, fill: QColor, _tag: str):
        n = len(data)
        if n < 2:
            return

        peak = max(self._peak, 1.0)
        # sub-pixel scroll: shift data by scroll_phase columns
        shift = self._scroll_phase

        def to_widget(i, v):
            # i=0 is oldest, i=n-1 is newest
            # with scroll, newest is at right edge minus (1-shift) fraction
            x = px + pw * ((i + shift) / (n - 1 + shift))
            y = py + ph * (1.0 - v / peak)
            return QPointF(x, y)

        smooth_data = _smooth(deque(data), window=2)

        # build path with cubic bezier segments
        path = QPainterPath()
        pts  = [to_widget(i, v) for i, v in enumerate(smooth_data)]
        path.moveTo(pts[0])
        for k in range(1, len(pts)):
            c1x = (pts[k - 1].x() + pts[k].x()) / 2
            path.cubicTo(
                QPointF(c1x, pts[k - 1].y()),
                QPointF(c1x, pts[k].y()),
                pts[k]
            )

        # fill
        fill_path = QPainterPath(path)
        fill_path.lineTo(QPointF(pts[-1].x(), py + ph))
        fill_path.lineTo(QPointF(pts[0].x(),  py + ph))
        fill_path.closeSubpath()

        grad = QLinearGradient(QPointF(px, py), QPointF(px, py + ph))
        top_fill = QColor(fill)
        top_fill.setAlpha(70)
        grad.setColorAt(0.0, top_fill)
        bot_fill = QColor(fill)
        bot_fill.setAlpha(0)
        grad.setColorAt(1.0, bot_fill)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPath(fill_path)

        # line — glow pass
        glow_color = QColor(color)
        glow_color.setAlpha(50)
        glow_pen = QPen(glow_color, 4, Qt.SolidLine)
        glow_pen.setCapStyle(Qt.RoundCap)
        glow_pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(glow_pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # line — solid pass
        line_pen = QPen(color, 1.5, Qt.SolidLine)
        line_pen.setCapStyle(Qt.RoundCap)
        line_pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(line_pen)
        p.drawPath(path)

        # live endpoint dot
        end_pt = pts[-1]
        pulse  = 0.5 + 0.5 * math.sin(self._shimmer)
        dot_r  = 3.5 + 1.5 * pulse
        glow3  = QColor(color); glow3.setAlpha(int(80 * pulse))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(glow3))
        p.drawEllipse(end_pt, dot_r * 2, dot_r * 2)
        p.setBrush(QBrush(color))
        p.drawEllipse(end_pt, dot_r * 0.7, dot_r * 0.7)

    def _draw_legend(self, p, px, py, pw):
        font = QFont("Consolas", 7)
        font.setBold(True)
        p.setFont(font)
        items = [("▲ TX", C_TX), ("▼ RX", C_RX)]
        x = px + pw - 6
        for label, color in reversed(items):
            p.setPen(QPen(color, 1))
            p.drawText(QRectF(x - 36, py, 36, 12), Qt.AlignRight, label)
            x -= 44

    def _draw_live_values(self, p, W, H):
        tx_now = self._tx[-1] if self._tx else 0
        rx_now = self._rx[-1] if self._rx else 0

        def fmt(v):
            if v >= 1024:
                return f"{v/1024:.1f} MB/s"
            return f"{v:.0f} KB/s"

        font = QFont("Consolas", 8)
        font.setBold(True)
        p.setFont(font)

        p.setPen(QPen(C_TX, 1))
        p.drawText(QRectF(4, H - 18, W // 2 - 4, 14),
                   Qt.AlignLeft | Qt.AlignVCenter, f"↑ {fmt(tx_now)}")
        p.setPen(QPen(C_RX, 1))
        p.drawText(QRectF(W // 2, H - 18, W // 2 - 4, 14),
                   Qt.AlignRight | Qt.AlignVCenter, f"↓ {fmt(rx_now)}")
