# -*- coding: utf-8 -*-
"""
NetworkTopologyView — Zoomable / pannable botnet topology widget.

Methods expected by main.py:
  NetworkTopologyView(bots)
  .set_bots(connected_bots)
  .set_target(ip_str)
  .start_animation()
  .stop_animation()
"""

import math
import random
from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath,
    QWheelEvent, QMouseEvent, QTransform
)
from PySide6.QtWidgets import QWidget


# ── Palette ──────────────────────────────────────────────────────────────────
C_BG        = QColor("#0a0a0d")
C_GRID      = QColor("#1a1a22")
C_C2        = QColor("#ff3030")          # C2 node
C_C2_GLOW   = QColor(255, 48, 48, 60)
C_BOT_ON    = QColor("#00ff88")          # connected bot
C_BOT_OFF   = QColor("#555560")          # disconnected bot
C_TARGET    = QColor("#f8fa5b")          # target node
C_EDGE_IDLE = QColor("#2a2a38")
C_EDGE_ATCK = QColor(255, 48, 48, 180)  # attack packet path
C_PKT       = QColor("#f8fa5b")          # flying packet dot
C_TEXT      = QColor("#cccccc")
C_TEXT_DIM  = QColor("#555560")
C_TICK      = QColor("#333340")


class _Packet:
    """A single flying dot along an edge during attack."""
    def __init__(self, src: QPointF, dst: QPointF):
        self.src = src
        self.dst = dst
        self.t = random.uniform(0.0, 1.0)   # position along path 0→1
        self.speed = random.uniform(0.008, 0.022)
        self.size = random.uniform(2.5, 4.5)
        self.alpha = random.randint(160, 255)

    def step(self):
        self.t += self.speed
        if self.t > 1.0:
            self.t = 0.0

    def pos(self) -> QPointF:
        return self.src + (self.dst - self.src) * self.t


class NetworkTopologyView(QWidget):
    """
    Star topology: C2 server in the centre, bots around it, optional target node.
    Supports mouse-wheel zoom and middle-button / left-drag pan.
    """

    MIN_ZOOM = 0.25
    MAX_ZOOM = 4.0

    def __init__(self, bots, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 180)
        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)

        # ── state ─────────────────────────────────────────────────────
        self._all_bots       = list(bots)       # from config
        self._connected_bots = []
        self._target_ip      = ""
        self._animating      = False
        self._packets: list[_Packet] = []

        # ── viewport transform ────────────────────────────────────────
        self._zoom       = 1.0
        self._pan        = QPointF(0, 0)
        self._drag_start = None                 # for left-drag pan
        self._pan_start  = None

        # ── animation timer (~60 fps) ─────────────────────────────────
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

        # pulse for glow rings
        self._pulse = 0.0

    # ── public API ────────────────────────────────────────────────────────────

    def set_bots(self, connected_bots):
        self._connected_bots = list(connected_bots)
        self._rebuild_packets()
        self.update()

    def set_target(self, ip: str):
        self._target_ip = ip
        self._rebuild_packets()
        self.update()

    def start_animation(self):
        self._animating = True
        self._rebuild_packets()

    def stop_animation(self):
        self._animating = False
        self._packets.clear()
        self.update()

    # ── internal helpers ──────────────────────────────────────────────────────

    def _rebuild_packets(self):
        self._packets.clear()
        if not self._animating:
            return
        c2 = self._c2_pos()
        tgt = self._target_pos()
        # packets: each connected bot → C2 → target
        for bot_pos in self._bot_positions():
            for _ in range(2):
                self._packets.append(_Packet(bot_pos, c2))
        if tgt is not None:
            for _ in range(4):
                self._packets.append(_Packet(c2, tgt))

    def _tick(self):
        self._pulse = (self._pulse + 0.03) % (2 * math.pi)
        if self._animating:
            for p in self._packets:
                p.step()
        self.update()

    # ── geometry helpers (in scene coords, centre = widget centre) ────────────

    def _scene_centre(self) -> QPointF:
        return QPointF(self.width() / 2, self.height() / 2)

    def _c2_pos(self) -> QPointF:
        return QPointF(0, 0)   # scene origin

    def _target_pos(self):
        if not self._target_ip:
            return None
        return QPointF(0, -200)

    def _bot_positions(self) -> list[QPointF]:
        n = max(len(self._all_bots), 1)
        radius = 130
        positions = []
        for i in range(n):
            angle = (2 * math.pi * i / n) - math.pi / 2
            positions.append(QPointF(radius * math.cos(angle),
                                     radius * math.sin(angle)))
        return positions

    # ── coordinate transforms ─────────────────────────────────────────────────

    def _to_widget(self, scene_pt: QPointF) -> QPointF:
        """Scene → widget pixels (applies zoom + pan)."""
        sc = self._scene_centre()
        return QPointF(
            sc.x() + (scene_pt.x() + self._pan.x()) * self._zoom,
            sc.y() + (scene_pt.y() + self._pan.y()) * self._zoom,
        )

    def _to_scene(self, widget_pt: QPointF) -> QPointF:
        sc = self._scene_centre()
        return QPointF(
            (widget_pt.x() - sc.x()) / self._zoom - self._pan.x(),
            (widget_pt.y() - sc.y()) / self._zoom - self._pan.y(),
        )

    # ── paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # background
        painter.fillRect(self.rect(), C_BG)
        self._draw_grid(painter)

        c2w   = self._to_widget(self._c2_pos())
        bwpos = [self._to_widget(p) for p in self._bot_positions()]
        tgtw  = self._to_widget(self._target_pos()) if self._target_ip else None

        # edges
        self._draw_edges(painter, c2w, bwpos, tgtw)

        # packets
        if self._animating:
            self._draw_packets(painter)

        # nodes
        if tgtw:
            self._draw_target(painter, tgtw)
        self._draw_bots(painter, bwpos)
        self._draw_c2(painter, c2w)

        # zoom hint
        self._draw_hint(painter)

        painter.end()

    def _draw_grid(self, painter: QPainter):
        spacing = max(20, int(40 * self._zoom))
        pen = QPen(C_GRID, 1)
        pen.setStyle(Qt.SolidLine)
        painter.setPen(pen)
        sc = self._scene_centre()
        # offset grid with pan
        ox = int((sc.x() + self._pan.x() * self._zoom) % spacing)
        oy = int((sc.y() + self._pan.y() * self._zoom) % spacing)
        for x in range(ox, self.width(), spacing):
            painter.drawLine(x, 0, x, self.height())
        for y in range(oy, self.height(), spacing):
            painter.drawLine(0, y, self.width(), y)

    def _draw_edges(self, painter, c2w, bwpos, tgtw):
        for i, bw in enumerate(bwpos):
            connected = i < len(self._connected_bots)
            if self._animating and connected:
                pen = QPen(C_EDGE_ATCK, 1.2, Qt.DashLine)
                pen.setDashPattern([4, 6])
            else:
                pen = QPen(C_EDGE_IDLE, 1, Qt.SolidLine)
            painter.setPen(pen)
            painter.drawLine(c2w, bw)

        if tgtw:
            pen = QPen(C_TARGET, 1.5, Qt.DashLine)
            pen.setDashPattern([6, 4])
            painter.setPen(pen)
            painter.drawLine(c2w, tgtw)

    def _draw_packets(self, painter: QPainter):
        for pkt in self._packets:
            scene_pos = pkt.pos()
            w_pos = self._to_widget(scene_pos)
            alpha = int(pkt.alpha * (0.6 + 0.4 * math.sin(self._pulse)))
            color = QColor(C_PKT)
            color.setAlpha(alpha)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color))
            r = pkt.size * self._zoom
            painter.drawEllipse(w_pos, r, r)

    def _draw_c2(self, painter: QPainter, pos: QPointF):
        r = max(16, int(18 * self._zoom))
        # glow pulse
        glow_r = r + int(10 * (0.5 + 0.5 * math.sin(self._pulse)))
        glow = QColor(C_C2_GLOW)
        glow.setAlpha(int(80 * (0.5 + 0.5 * math.sin(self._pulse))))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(pos, glow_r, glow_r)

        painter.setPen(QPen(C_C2, 2))
        painter.setBrush(QBrush(QColor("#1a0505")))
        painter.drawEllipse(pos, r, r)

        # cross-hair inner
        painter.setPen(QPen(C_C2, 1.5))
        painter.drawLine(QPointF(pos.x() - r * 0.5, pos.y()),
                         QPointF(pos.x() + r * 0.5, pos.y()))
        painter.drawLine(QPointF(pos.x(), pos.y() - r * 0.5),
                         QPointF(pos.x(), pos.y() + r * 0.5))

        if self._zoom > 0.5:
            painter.setPen(QPen(C_C2, 1))
            font = QFont("Consolas", max(7, int(8 * self._zoom)))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRectF(pos.x() - 40, pos.y() + r + 4, 80, 16),
                             Qt.AlignCenter, "C2 SERVER")

    def _draw_bots(self, painter: QPainter, positions: list[QPointF]):
        for i, pos in enumerate(positions):
            connected = i < len(self._connected_bots)
            color = C_BOT_ON if connected else C_BOT_OFF
            r = max(10, int(12 * self._zoom))

            # glow for connected + animating
            if connected and self._animating:
                glow = QColor(color)
                glow.setAlpha(int(50 * (0.5 + 0.5 * math.sin(self._pulse + i))))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(glow))
                painter.drawEllipse(pos, r + 6, r + 6)

            painter.setPen(QPen(color, 1.5))
            painter.setBrush(QBrush(QColor("#0a0a0d")))
            painter.drawEllipse(pos, r, r)

            # dot inside
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(pos, max(3, int(4 * self._zoom)),
                                 max(3, int(4 * self._zoom)))

            if self._zoom > 0.6 and i < len(self._all_bots):
                label = getattr(self._all_bots[i], 'host', f"BOT-{i+1}")
                font = QFont("Consolas", max(6, int(7 * self._zoom)))
                painter.setFont(font)
                painter.setPen(QPen(color if connected else C_TEXT_DIM, 1))
                painter.drawText(
                    QRectF(pos.x() - 50, pos.y() + r + 3, 100, 14),
                    Qt.AlignCenter, label)

    def _draw_target(self, painter: QPainter, pos: QPointF):
        r = max(13, int(15 * self._zoom))
        pulse = 0.5 + 0.5 * math.sin(self._pulse * 2)

        # warning rings
        for ring in range(3):
            ring_r = r + (ring + 1) * int(7 * self._zoom * pulse)
            alpha = int(100 * (1 - ring / 3) * pulse)
            rc = QColor(C_TARGET)
            rc.setAlpha(alpha)
            painter.setPen(QPen(rc, 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(pos, ring_r, ring_r)

        painter.setPen(QPen(C_TARGET, 2))
        painter.setBrush(QBrush(QColor("#1a1800")))
        painter.drawEllipse(pos, r, r)

        # X mark
        d = int(r * 0.55)
        painter.setPen(QPen(C_TARGET, 2))
        painter.drawLine(QPointF(pos.x() - d, pos.y() - d),
                         QPointF(pos.x() + d, pos.y() + d))
        painter.drawLine(QPointF(pos.x() + d, pos.y() - d),
                         QPointF(pos.x() - d, pos.y() + d))

        if self._zoom > 0.5:
            font = QFont("Consolas", max(7, int(8 * self._zoom)))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QPen(C_TARGET, 1))
            painter.drawText(
                QRectF(pos.x() - 60, pos.y() + r + 4, 120, 16),
                Qt.AlignCenter, self._target_ip)

    def _draw_hint(self, painter: QPainter):
        """Zoom level indicator bottom-right."""
        font = QFont("Consolas", 8)
        painter.setFont(font)
        painter.setPen(QPen(C_TEXT_DIM, 1))
        hint = f"×{self._zoom:.1f}  scroll=zoom  drag=pan"
        painter.drawText(self.rect().adjusted(0, 0, -6, -5),
                         Qt.AlignBottom | Qt.AlignRight, hint)

    # ── interaction ───────────────────────────────────────────────────────────

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        factor = 1.12 if delta > 0 else 1 / 1.12
        new_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self._zoom * factor))

        # zoom towards mouse cursor
        cursor_scene = self._to_scene(QPointF(event.position()))
        self._zoom = new_zoom
        # adjust pan so the point under cursor stays fixed
        sc = self._scene_centre()
        new_widget = QPointF(
            sc.x() + (cursor_scene.x() + self._pan.x()) * self._zoom,
            sc.y() + (cursor_scene.y() + self._pan.y()) * self._zoom,
        )
        diff = QPointF(event.position()) - new_widget
        self._pan += QPointF(diff.x() / self._zoom, diff.y() / self._zoom)

        self._rebuild_packets()
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._drag_start = QPointF(event.position())
            self._pan_start  = QPointF(self._pan)
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_start is not None:
            delta = QPointF(event.position()) - self._drag_start
            self._pan = self._pan_start + QPointF(delta.x() / self._zoom,
                                                   delta.y() / self._zoom)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_start = None
        self._pan_start  = None
        self.setCursor(Qt.OpenHandCursor)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Double-click to reset zoom/pan."""
        self._zoom = 1.0
        self._pan  = QPointF(0, 0)
        self._rebuild_packets()
        self.update()
