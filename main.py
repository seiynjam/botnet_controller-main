# -*- coding: utf-8 -*-
import sys
import os
import subprocess
import re
import json
from typing import Optional, List
from PySide6.QtCore import QTimer, Qt, QLocale, QRectF, QPointF, Signal, QObject, QRunnable, QThreadPool, QThread
from PySide6.QtGui import QFont, QFontDatabase, QAction, QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QApplication, QWidget, QGridLayout, QGroupBox, QLabel, QLineEdit,
    QPushButton, QProgressBar, QPlainTextEdit, QHBoxLayout, QVBoxLayout, QComboBox,
    QListWidget, QListWidgetItem
)
from config import BOTS
from models import Bus
from workers import AttackWorker  # Use the robust worker from workers.py
from widgets.network_topology import NetworkTopologyView
from widgets.modern_gauge import ModernGauge
from widgets.network_chart import EnhancedNetworkChart
import psutil
import time
import paramiko
import random
import math

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

class ScanWorker(QObject):
    log = Signal(str)
    scan_completed = Signal(list)

class NmapScanWorker(QRunnable):
    def __init__(self, network: str, bus: Bus, scanner_bot):
        super().__init__()
        self.network = network
        self.bus = bus
        self.bot = scanner_bot  # รับข้อมูลบอทที่จะใช้สแกนเข้ามา
        self.signals = ScanWorker()

    def run(self):
        try:
            cmd = f"nmap -sn {self.network}"
            self.signals.log.emit(f"[{time.strftime('%H:%M:%S')}] 🕵️‍♂️ Ordering Bot ({self.bot.host}) to scan network: {cmd}")

            # มุด SSH ไปหา Bot (Kali)
            import paramiko
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.bot.host, username=self.bot.user, password=self.bot.password, timeout=15)

            # สั่งรัน nmap บน Kali
            stdin, stdout, stderr = ssh.exec_command(cmd)
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')
            ssh.close()

            # ถ้ามี Error ที่ไม่ได้เกิดจากการทำงานปกติของ Nmap
            if error and "Nmap done" not in output:
                self.signals.log.emit(f"[{time.strftime('%H:%M:%S')}] ❌ Nmap scan error on {self.bot.host}: {error}")
                self.signals.scan_completed.emit([])
                return

            # ดึง IP จากผลลัพธ์ที่ได้มาจาก Kali
            hosts = []
            ip_pattern = r'Nmap scan report for (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
            import re
            ips = re.findall(ip_pattern, output)
            
            for ip in ips:
                hosts.append({"ip": ip, "status": "up"})
                
            self.signals.log.emit(f"[{time.strftime('%H:%M:%S')}] ✅ Scan completed by {self.bot.host}. Found {len(hosts)} hosts: {', '.join([h['ip'] for h in hosts])}")
            self.signals.scan_completed.emit(hosts)

        except Exception as e:
            self.signals.log.emit(f"[{time.strftime('%H:%M:%S')}] ❌ SSH Nmap scan error: {e}")
            self.signals.scan_completed.emit([])
class AttackAnimationWidget(QWidget):
    """Custom widget for DDoS attack animation background"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: rgba(0, 0, 0, 0.5);")  # Semi-transparent background
        self.particles = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_particles)
        self.is_animating = False

        # Initialize particles
        self.init_particles()

    def init_particles(self):
        """Initialize particles for animation"""
        self.particles = []
        for _ in range(50):  # Number of particles
            self.particles.append({
                'pos': QPointF(random.uniform(0, self.width()), random.uniform(0, self.height())),
                'speed': random.uniform(2, 5),
                'angle': random.uniform(0, 2 * math.pi),
                'color': QColor(random.choice(['#ff4500', '#00ff88', '#ff0000'])),
                'size': random.uniform(2, 5),
                'blink': random.random()
            })

    def start_animation(self):
        """Start the animation"""
        self.is_animating = True
        self.timer.start(16)  # ~60 FPS
        self.show()

    def stop_animation(self):
        """Stop the animation"""
        self.is_animating = False
        self.timer.stop()
        self.hide()

    def update_particles(self):
        """Update particle positions and trigger repaint"""
        if not self.is_animating:
            return
        for particle in self.particles:
            # Update position
            particle['pos'] += QPointF(
                particle['speed'] * math.cos(particle['angle']),
                particle['speed'] * math.sin(particle['angle'])
            )
            # Bounce off edges
            if particle['pos'].x() < 0 or particle['pos'].x() > self.width():
                particle['angle'] = math.pi - particle['angle']
            if particle['pos'].y() < 0 or particle['pos'].y() > self.height():
                particle['angle'] = -particle['angle']
            # Update blink
            particle['blink'] = (particle['blink'] + 0.05) % 1
        self.update()

    def resizeEvent(self, event):
        """Reinitialize particles on resize to match new dimensions"""
        self.init_particles()
        super().resizeEvent(event)

    def paintEvent(self, event):
        """Paint particles to simulate DDoS attack"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for particle in self.particles:
            # Apply blinking effect
            alpha = int(255 * (0.5 + 0.5 * math.sin(particle['blink'] * 2 * math.pi)))
            color = particle['color']
            color.setAlpha(alpha)
            painter.setPen(QPen(color, 1))
            painter.setBrush(QBrush(color))
            painter.drawEllipse(particle['pos'], particle['size'], particle['size'])
            # Draw trailing line for packet effect
            end_pos = particle['pos'] - QPointF(
                particle['speed'] * math.cos(particle['angle']) * 5,
                particle['speed'] * math.sin(particle['angle']) * 5
            )
            painter.setPen(QPen(color, 1))
            painter.drawLine(particle['pos'], end_pos)
        painter.end()

class Main(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Botnet Controller Dashboard (Cyberpunk)")
        self.resize(1200, 700)  # Adjusted size to avoid screen limit issues
        self.setMinimumSize(1162, 902)  # Set minimum size based on warning
        self.inputs = {}

        # Initialize attack animation widget
        self.attack_animation = AttackAnimationWidget(self)
        self.attack_animation.hide()  # Hidden by default

        # Initialize digital font
        self.dig_font = None
        for f in ("Digital-7.ttf", "DSEG7Classic-Bold.ttf", "calculator.ttf"):
            if os.path.exists(f):
                try:
                    fid = QFontDatabase.addApplicationFont(f)
                    fams = QFontDatabase.applicationFontFamilies(fid)
                    if fams:
                        self.dig_font = fams[0]
                        break
                except Exception as e:
                    print(f"Failed to load font {f}: {e}")

        # Event bus
        self.bus = Bus()

        self.connected_bots = []
        self.scanned_hosts = []  # List of {'ip': str, 'status': str}
        self.selected_target = ""  # Currently selected target IP

        # Layout
        grid = QGridLayout(self)
        grid.setSpacing(10)
        grid.setContentsMargins(10, 10, 10, 10)

        # Left column (topology, gauges, network)
        left_col = self.create_left_column()
        center_col = self.create_center_column()
        right_col = self.create_right_column()

        grid.addWidget(left_col, 0, 0)
        grid.addWidget(center_col, 0, 1)
        grid.addWidget(right_col, 0, 2)

        grid.setColumnStretch(0, 5)
        grid.setColumnStretch(1, 5)
        grid.setColumnStretch(2, 3)

        # Connect bus signals after UI is initialized
        self.bus.log.connect(self.append_log)
        self.bus.progress.connect(self.update_progress)
        self.bus.countdown.connect(self.update_countdown)
        self.bus.status.connect(self.on_worker_status)
        self.bus.metrics.connect(self.update_metrics)

        # Check if background image exists
        # In Main.__init__
        bg_path = os.path.join("logo.jpg").replace("\\", "/")
        current_dir = os.getcwd().replace("\\", "/")
        self.append_log(f"[{time.strftime('%H:%M:%S')}] Current working directory: {current_dir}")
        self.append_log(f"[{time.strftime('%H:%M:%S')}] Checking for background image at: {bg_path}")
        if not os.path.exists(bg_path):
            self.append_log(f"[{time.strftime('%H:%M:%S')}] Error: Could not find background image at {bg_path}")
            self.bg_style_normal = """
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0a0a0a, stop:1 #1a237e
                );
            """
        else:
            try:
                file_size = os.path.getsize(bg_path)
                if PIL_AVAILABLE:
                    with Image.open(bg_path) as img:
                        width, height = img.size
                        format = img.format
                    self.append_log(f"[{time.strftime('%H:%M:%S')}] Background image found: {bg_path} ({file_size} bytes, {width}x{height}, format: {format})")
                else:
                    self.append_log(f"[{time.strftime('%H:%M:%S')}] Background image found: {bg_path} ({file_size} bytes, Pillow not installed)")
                self.bg_style_normal = f"""
                    background-image: url({bg_path});
                    background-position: center;
                    background-repeat: no-repeat;
                    background-attachment: fixed;
                    background-color: #0a0a0a;
                """
            except Exception as e:
                self.append_log(f"[{time.strftime('%H:%M:%S')}] Error loading background image: {e}")
                self.bg_style_normal = """
                    background: qlineargradient(
                        x1:0, y1:0, x2:0, y2:1,
                        stop:0 #0a0a0a, stop:1 #1a237e
                    );
                """

        # Modern Red Team theme — sharp, symmetric, high-contrast
        self.base_stylesheet = f"""
            Main {{
                background: #131316;
            }}

            /* ── Group Boxes ─────────────────────────────────────────── */
            QGroupBox {{
                border: 1px solid #3a1a1a;
                border-top: 2px solid #ff3030;
                margin-top: 18px;
                padding-top: 6px;
                background: #1a1a1f;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 0px;
                top: 0px;
                padding: 4px 16px 4px 12px;
                color: #ffffff;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #cc0000, stop:0.7 #ff3030, stop:1 #1a1a1f
                );
                font-family: 'Consolas', monospace;
                font-weight: bold;
                font-size: 11px;
                letter-spacing: 2px;
                text-transform: uppercase;
                border: none;
                margin-left: 0px;
            }}

            /* ── Inputs ─────────────────────────────────────────────── */
            QLineEdit {{
                background: #0e0e12;
                border: 1px solid #3d1010;
                border-bottom: 2px solid #ff3030;
                padding: 7px 10px;
                color: #f8fa5b;
                font-family: 'Consolas', monospace;
                font-size: 12px;
                selection-background-color: #ff3030;
                selection-color: #ffffff;
            }}
            QLineEdit:focus {{
                border-bottom: 2px solid #f8fa5b;
                background: #141418;
                color: #f8fa5b;
            }}
            QLineEdit:disabled {{
                background: #1c1c20;
                color: #555560;
                border: 1px solid #2a2a30;
                border-bottom: 2px solid #444;
            }}

            /* ── ComboBox ───────────────────────────────────────────── */
            QComboBox {{
                background: #0e0e12;
                border: 1px solid #3d1010;
                border-bottom: 2px solid #ff3030;
                padding: 7px 10px;
                color: #f8fa5b;
                font-family: 'Consolas', monospace;
                font-size: 12px;
            }}
            QComboBox:hover {{
                border-bottom: 2px solid #f8fa5b;
                background: #141418;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox::down-arrow {{
                width: 10px;
                height: 10px;
            }}
            QComboBox QAbstractItemView {{
                background: #1a1a1f;
                border: 1px solid #ff3030;
                color: #f8fa5b;
                selection-background-color: #cc0000;
                selection-color: #ffffff;
                outline: none;
            }}

            /* ── List Widget ────────────────────────────────────────── */
            QListWidget {{
                background: #0e0e12;
                border: 1px solid #3d1010;
                border-left: 2px solid #ff3030;
                color: #00ff88;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                outline: none;
            }}
            QListWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid #1e1e24;
            }}
            QListWidget::item:hover {{
                background: #1e0a0a;
                color: #f8fa5b;
            }}
            QListWidget::item:selected {{
                background: #cc0000;
                color: #ffffff;
                border-left: 3px solid #f8fa5b;
            }}

            /* ── Log / Plain Text Edit ──────────────────────────────── */
            QPlainTextEdit {{
                background: #0a0a0d;
                border: 1px solid #1e1e24;
                border-left: 2px solid #ff3030;
                padding: 8px 10px;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                color: #00ff88;
                selection-background-color: #ff3030;
            }}

            /* ── Scrollbars ─────────────────────────────────────────── */
            QScrollBar:vertical {{
                background: #0e0e12;
                width: 6px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: #ff3030;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar:horizontal {{
                background: #0e0e12;
                height: 6px;
            }}
            QScrollBar::handle:horizontal {{
                background: #ff3030;
                min-width: 20px;
            }}

            /* ── Buttons ────────────────────────────────────────────── */
            QPushButton {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #cc0000, stop:1 #8a0000
                );
                color: #ffffff;
                border: 1px solid #ff3030;
                border-top: 1px solid #ff6060;
                padding: 10px 16px;
                font-family: 'Consolas', monospace;
                font-weight: bold;
                font-size: 11px;
                letter-spacing: 1px;
                text-transform: uppercase;
            }}
            QPushButton:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ff3030, stop:1 #aa0000
                );
                border: 1px solid #f8fa5b;
                color: #f8fa5b;
            }}
            QPushButton:pressed {{
                background: #660000;
                border: 1px solid #ff3030;
                color: #ffffff;
                padding-top: 12px;
                padding-bottom: 8px;
            }}
            QPushButton:disabled {{
                background: #1e1e24;
                color: #444450;
                border: 1px solid #2a2a34;
            }}

            /* ── Labels ─────────────────────────────────────────────── */
            QLabel.big {{ 
                font-family: 'Consolas', monospace;
                font-size: 56px; 
                color: #ff3030;
            }}
            QLabel.timer {{ 
                font-family: 'Consolas', monospace;
                font-size: 48px; 
                color: #f8fa5b; 
                font-weight: bold;
            }}
            QLabel.status {{ 
                color: #f8fa5b; 
                font-family: 'Consolas', monospace;
                font-size: 12px; 
                font-weight: 500;
            }}
            QLabel.metric {{ 
                color: #ff3030; 
                font-family: 'Consolas', monospace;
                font-weight: bold;
                font-size: 12px;
            }}
            QLabel.attack_status {{ 
                font-family: 'Consolas', monospace;
                font-size: 16px; 
                font-weight: bold;
                letter-spacing: 1px;
            }}
        """
        self.setStyleSheet(self.base_stylesheet)
        self.worker: Optional[AttackWorker] = None
        self.duration_total = 0
        self.seconds_left = 0
        self.attack_status_color = True

        # Timers
        self.timer_perf = QTimer(self)
        self.timer_perf.timeout.connect(self.update_perf)
        self.timer_perf.start(1000)
        self.timer_count = QTimer(self)
        self.timer_count.timeout.connect(self.tick_countdown)
        self.timer_status_blink = QTimer(self)
        self.timer_status_blink.timeout.connect(self.update_attack_status_color)
        self.timer_status_blink.start(500)

        # Thread pool for scanning
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(1)

        # Defaults
        self.inputs["network"].setText("192.168.1.0/24")
        self.inputs["duration"].setText("60")
        self.inputs["port"].setText("5000")
        self.inputs["sockets"].setText("250")
        self.inputs["bots"].setText(str(len(BOTS)))
        self.inputs["attack_type"].setCurrentText("Slowloris")

        # Context stop action
        self.addAction(QAction("Stop Attack", self, triggered=self.stop_attack))
        self.setContextMenuPolicy(Qt.ActionsContextMenu)

        # Connect to bots on startup
        self.connect_bots()

    def resizeEvent(self, event):
        """Resize the attack animation widget to match the main window"""
        self.attack_animation.resize(self.size())
        super().resizeEvent(event)

    def connect_bots(self):
        """Connect to all bots on startup and store connected ones."""
        self.connected_bots = []
        for bot in BOTS:
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(bot.host, username=bot.user, password=bot.password, timeout=5)
                self.connected_bots.append(bot)
                self.append_log(f"[{time.strftime('%H:%M:%S')}] Connected to {bot.host}")
                ssh.close()
            except paramiko.AuthenticationException:
                self.append_log(f"[{time.strftime('%H:%M:%S')}] Authentication failed for {bot.host}")
            except paramiko.SSHException as e:
                self.append_log(f"[{time.strftime('%H:%M:%S')}] SSH error for {bot.host}: {e}")
            except Exception as e:
                self.append_log(f"[{time.strftime('%H:%M:%S')}] Failed to connect to {bot.host}: {e}")
        self.append_log(f"[{time.strftime('%H:%M:%S')}] Total connected bots: {len(self.connected_bots)}")
        self.topo_view.set_bots(self.connected_bots)
        self.update_bot_count()

    def create_left_column(self):
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setSpacing(10)

        # Topology group
        gb_topo = QGroupBox("BOTNET TOPOLOGY")
        ltop = QVBoxLayout(gb_topo)
        ltop.setContentsMargins(8, 10, 8, 8)
        self.topo_view = NetworkTopologyView(BOTS)
        ltop.addWidget(self.topo_view)

        # Gauges
        gb_gauges = QGroupBox("SYSTEM METRICS")
        lg = QHBoxLayout(gb_gauges)
        lg.setContentsMargins(10, 12, 10, 10)
        self.cpu_gauge = ModernGauge("CPU", QColor("#00e09d"))
        self.ram_gauge = ModernGauge("RAM", QColor("#ff6b6b"))
        lg.addWidget(self.cpu_gauge)
        lg.addWidget(self.ram_gauge)

        # Network chart
        gb_net = QGroupBox("NETWORK TRAFFIC")
        ln = QVBoxLayout(gb_net)
        ln.setContentsMargins(8, 10, 8, 8)
        self.net_chart = EnhancedNetworkChart()
        ln.addWidget(self.net_chart)

        v.addWidget(gb_topo, 3)
        v.addWidget(gb_gauges, 1)
        v.addWidget(gb_net, 1)

        return wrap

    def create_center_column(self):
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setSpacing(10)

        # Timer group
        gb_time = QGroupBox("ATTACK DURATION")
        lt = QVBoxLayout(gb_time)
        lt.setContentsMargins(18, 18, 18, 14)
        self.lbl_time = QLabel("00:00:00", alignment=Qt.AlignCenter)
        self.lbl_time.setProperty("class", "timer")
        if self.dig_font:
            self.lbl_time.setFont(QFont(self.dig_font, 48, QFont.Bold))
        lt.addWidget(self.lbl_time)

        # Attack status and bot count
        status_layout = QHBoxLayout()
        self.lbl_attack_status = QLabel("IDLE")
        self.lbl_attack_status.setProperty("class", "attack_status")
        self.lbl_bot_count = QLabel(f"Active Bots: {len(self.connected_bots)}")
        self.lbl_bot_count.setProperty("class", "metric")
        status_layout.addWidget(self.lbl_attack_status)
        status_layout.addStretch()
        status_layout.addWidget(self.lbl_bot_count)
        lt.addLayout(status_layout)

        # Progress
        gb_proc = QGroupBox("ATTACK PROGRESS")
        lp = QVBoxLayout(gb_proc)
        lp.setContentsMargins(18, 18, 18, 18)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(100)
        self.progress.setLocale(QLocale(QLocale.English, QLocale.UnitedStates))
        self.progress.setFormat("%p%")
        self.progress.setStyleSheet("""
            QProgressBar {
                border: none;
                border-bottom: 2px solid #ff3030;
                text-align: center;
                background-color: #0a0a0d;
                font-family: 'Consolas', monospace;
                font-size: 48px;
                color: #f8fa5b;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    spread:pad,
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #660000, stop:0.5 #cc0000, stop:1 #ff3030
                );
            }
        """)
        lp.addWidget(self.progress)

        # Log
        gb_log = QGroupBox("EVENT LOG")
        lg = QVBoxLayout(gb_log)
        lg.setContentsMargins(10, 12, 10, 8)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        lg.addWidget(self.log)

        # Status row
        status_row = QHBoxLayout()
        self.lbl_rps = QLabel("Requests/sec: 0")
        self.lbl_lat = QLabel("Latency: 0 ms")
        self.lbl_state = QLabel("● Idle")
        self.lbl_state.setStyleSheet("color:#00ff88; font-family: 'Consolas', monospace; font-size: 11px; letter-spacing: 1px;")
        status_row.addWidget(self.lbl_rps)
        status_row.addSpacing(24)
        status_row.addWidget(self.lbl_lat)
        status_row.addStretch()
        status_row.addWidget(self.lbl_state)
        lg.addLayout(status_row)

        v.addWidget(gb_time, 1)
        v.addWidget(gb_proc, 1)
        v.addWidget(gb_log, 2)

        return wrap

    def create_right_column(self):
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setSpacing(10)

        # Scan section
        gb_scan = QGroupBox("NETWORK SCAN")
        gs = QVBoxLayout(gb_scan)
        gs.setContentsMargins(14, 14, 14, 14)
        gs.setSpacing(8)

        lbl_network = QLabel("NETWORK RANGE")
        lbl_network.setStyleSheet("color: #888898; font-family: 'Consolas', monospace; font-size: 10px; letter-spacing: 2px;")
        gs.addWidget(lbl_network)

        self.inputs["network"] = QLineEdit()
        self.inputs["network"].setPlaceholderText("192.168.1.0/24")
        gs.addWidget(self.inputs["network"]) 

        self.btn_scan = QPushButton("⬡  SCAN NETWORK")
        self.btn_scan.clicked.connect(self.start_scan)
        self.btn_scan.setFixedHeight(40)
        gs.addWidget(self.btn_scan)

        # Hosts list
        lbl_hosts = QLabel("DISCOVERED HOSTS  —  click to select target")
        lbl_hosts.setStyleSheet("color: #888898; font-family: 'Consolas', monospace; font-size: 10px; letter-spacing: 1px;")
        gs.addWidget(lbl_hosts)

        self.hosts_list = QListWidget()
        self.hosts_list.itemClicked.connect(self.select_target)
        gs.addWidget(self.hosts_list)

        v.addWidget(gb_scan)

        gb_ctrl = QGroupBox("ATTACK CONFIGURATION")
        g = QVBoxLayout(gb_ctrl)
        g.setContentsMargins(14, 14, 14, 14)
        g.setSpacing(10)

        fields = [
            ("TARGET IP", "target", "", QLineEdit),
            ("ATTACK TYPE", "attack_type", "Slowloris", QComboBox),
            ("PORT", "port", "5000", QLineEdit),
            ("DURATION (s)", "duration", "60", QLineEdit),
            ("SOCKETS", "sockets", "250", QLineEdit),
            ("BOT COUNT", "bots", str(len(BOTS)), QLineEdit),
        ]

        for label, key, default, widget_cls in fields:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #888898; font-family: 'Consolas', monospace; font-size: 10px; letter-spacing: 1px; min-width: 100px;")
            row.addWidget(lbl)

            if widget_cls == QComboBox:
                w = QComboBox()
                w.addItems(["Slowloris", "hping3"])
                w.setCurrentText(default)
            else:
                w = widget_cls()
                w.setText(default)

            self.inputs[key] = w
            row.addWidget(w)
            g.addLayout(row)

        # Initialize input fields state
        self.update_input_fields("Slowloris")

        g.addSpacing(12)
        self.btn_start = QPushButton("▶  LAUNCH ATTACK")
        self.btn_start.clicked.connect(self.start_attack)
        self.btn_start.setFixedHeight(42)
        g.addWidget(self.btn_start)

        self.btn_stop = QPushButton("■  ABORT ATTACK")
        self.btn_stop.clicked.connect(self.stop_attack)
        self.btn_stop.setFixedHeight(42)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #ff3030;
                border: 1px solid #ff3030;
                border-left: 3px solid #ff3030;
                padding: 10px 16px;
                font-family: 'Consolas', monospace;
                font-weight: bold;
                font-size: 11px;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background: #1a0000;
                color: #ff6060;
                border: 1px solid #ff6060;
                border-left: 3px solid #ff6060;
            }
            QPushButton:disabled {
                background: transparent;
                color: #333340;
                border: 1px solid #252530;
                border-left: 3px solid #333340;
            }
        """)
        g.addWidget(self.btn_stop)
        g.addStretch()

        # DDos-Control box
        v.addWidget(gb_ctrl, 2)

        return wrap

    def start_scan(self):
        network = self.inputs["network"].text().strip()
        if not network:
            self.append_log("[!] Network range is empty")
            return
            
        # เช็กก่อนว่ามีบอทเชื่อมต่ออยู่ไหม ถ้าไม่มีก็สั่งใครไปสแกนไม่ได้
        if not self.connected_bots:
            self.append_log("[!] ❌ No connected bots available to perform scan. Check your botnet connection.")
            return

        self.btn_scan.setDisabled(True)
        self.hosts_list.clear()
        self.scanned_hosts = []
        self.selected_target = ""
        self.inputs["target"].setText("")
        self.btn_start.setEnabled(False)

        # เลือกบอทตัวแรกในลิสต์ให้เป็นหน่วยสอดแนม
        scanner_bot = self.connected_bots[0]

        # โยน IP วงแลน กับ ตัวบอท เข้าไปให้ Worker จัดการผ่าน SSH
        scan_worker = NmapScanWorker(network, self.bus, scanner_bot)
        scan_worker.signals.log.connect(self.append_log)
        scan_worker.signals.scan_completed.connect(self.on_scan_completed)
        self.threadpool.start(scan_worker)

    def on_scan_completed(self, hosts: List[dict]):
        self.btn_scan.setDisabled(False)
        self.scanned_hosts = hosts
        for host in hosts:
            item = QListWidgetItem(f"Host: {host['ip']} - Status: {host['status']}")
            self.hosts_list.addItem(item)

    def select_target(self, item: QListWidgetItem):
        self.selected_target = item.text().split(" - ")[0].replace("Host: ", "")
        self.inputs["target"].setText(self.selected_target)
        self.inputs["target"].setEnabled(True)
        self.btn_start.setEnabled(True)
        self.append_log(f"[{time.strftime('%H:%M:%S')}] Selected target: {self.selected_target}")

    def update_input_fields(self, attack_type: str):
        """Enable/disable input fields and update target based on attack type."""
        if attack_type == "Slowloris":
            self.inputs["sockets"].setEnabled(True)
            self.inputs["port"].setEnabled(True)
            if self.selected_target:
                self.inputs["target"].setText(self.selected_target)
        elif attack_type == "hping3":
            self.inputs["sockets"].setEnabled(False)
            self.inputs["port"].setEnabled(True)
            if self.selected_target:
                self.inputs["target"].setText(self.selected_target)

    def start_attack(self):
        target = self.inputs["target"].text().strip()
        try:
            duration = int(self.inputs["duration"].text().strip() or "60")
        except Exception:
            duration = 60
        try:
            port = int(self.inputs["port"].text().strip() or "80")
        except Exception:
            port = 80
        try:
            sockets = int(self.inputs["sockets"].text().strip() or "250")
        except Exception:
            sockets = 250
        attack_type = self.inputs["attack_type"].currentText()
        try:
            num_bots = int(self.inputs["bots"].text().strip() or "0")
        except Exception:
            num_bots = 0

        if not target:
            self.append_log("[!] No target selected. Please scan and select a host first.")
            return

        try:
            # Reset progress
            self.progress.setValue(0)
            self.duration_total = duration
            self.seconds_left = duration

            # Update status
            self.lbl_attack_status.setText(f"ATTACKING {target}:{port} [{attack_type}]")
            self.lbl_attack_status.setStyleSheet("color:#ff3030;")

            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)

            # Start countdown timer
            self.timer_count.start(1000)

            # Start attack animation
            self.attack_animation.start_animation()

            # Start topology animation and set target
            self.topo_view.set_target(target)  # ตั้งค่าเป้าหมายให้ topology view
            self.topo_view.start_animation()   # เริ่มอนิเมชันใน topology

            # Spawn worker using the robust AttackWorker from workers.py
            self.worker = AttackWorker(
                bus=self.bus,
                target=target,
                workers=1,
                sockets=sockets,
                duration=duration,
                num_bots=max(1, num_bots),
                attack_type=attack_type,
                port=port,
                connected_bots=self.connected_bots[:max(0, num_bots)]
            )
            self.worker.start()

            self.append_log(f"[{time.strftime('%H:%M:%S')}] Attack started: {attack_type} -> {target}:{port} for {duration}s with {num_bots} bots")

        except Exception as e:
            self.append_log(f"[!] Failed to start attack: {e}")
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)

    def stop_attack(self):
        if self.worker:
            try:
                self.worker.stop()
            except Exception as e:
                self.append_log(f"[!] Error stopping worker: {e}")
            self.worker = None
        self.timer_count.stop()
        self.attack_animation.stop_animation()
        self.topo_view.stop_animation()  # หยุดอนิเมชันใน topology
        self.progress.setValue(0)
        self.lbl_time.setText("00:00:00")
        self.lbl_attack_status.setText("IDLE")
        self.lbl_attack_status.setStyleSheet("color:#00ff88;")
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.append_log(f"[{time.strftime('%H:%M:%S')}] Attack stopped")

    def append_log(self, s: str):
        self.log.appendPlainText(s)
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def update_progress(self, v: int):
        self.progress.setValue(v)

    def update_countdown(self, left: int):
        self.seconds_left = left
        self._render_countdown()

    def on_worker_status(self, st: str):
        if st == "idle":
            self.btn_start.setDisabled(False)
            self.btn_stop.setEnabled(False)
            self.timer_count.stop()
            self.lbl_state.setText("● Idle")
            self.lbl_state.setStyleSheet("color:#00ff88; font-family: 'Consolas', monospace; font-size: 11px; letter-spacing: 1px;")
            self.lbl_attack_status.setText("IDLE")
            self.topo_view.set_target("")
            self.topo_view.stop_animation()
            # Stop attack animation
            self.attack_animation.stop_animation()

    def update_metrics(self, metrics: dict):
        self.lbl_rps.setText(f"Requests/sec: {metrics.get('rps', 0)}")
        self.lbl_lat.setText(f"Latency: {metrics.get('latency', 0)} ms")

    def tick_countdown(self):
        if self.seconds_left > 0:
            self.seconds_left -= 1
        self._render_countdown()
        if self.duration_total > 0:
            pct = int(100 * (self.duration_total - self.seconds_left) / self.duration_total)
            if pct > self.progress.value():
                self.progress.setValue(min(100, pct))

    def _render_countdown(self):
        sec = max(0, int(self.seconds_left))
        h = sec // 3600
        m = (sec % 3600) // 60
        s = sec % 60
        if self.dig_font:
            self.lbl_time.setFont(QFont(self.dig_font, 48, QFont.Bold))
        self.lbl_time.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def update_perf(self):
        try:
            self.cpu_gauge.setValue(int(psutil.cpu_percent()))
            self.ram_gauge.setValue(int(psutil.virtual_memory().percent))
            self.net_chart.step()
            self.lbl_rps.setText(f"Requests/sec: {int(1200 + psutil.cpu_percent()*3)}")
            self.lbl_lat.setText(f"Latency: {int(90 + psutil.virtual_memory().percent/2)} ms")
        except Exception:
            pass

    def update_bot_count(self):
        self.lbl_bot_count.setText(f"Active Bots: {len(self.connected_bots)}")

    def update_attack_status_color(self):
        """Toggle color of attack status label for blinking effect."""
        if self.lbl_attack_status.text().startswith("ATTACKING"):
            self.attack_status_color = not self.attack_status_color
            color = "#00ff88" if self.attack_status_color else "#ff3030"
            self.lbl_attack_status.setStyleSheet(f"color: {color}; font-family: 'Consolas', monospace; font-size: 16px; font-weight: bold; letter-spacing: 1px;")
        else:
            self.lbl_attack_status.setStyleSheet("color: #00ff88; font-family: 'Consolas', monospace; font-size: 16px; font-weight: bold; letter-spacing: 1px;")

    def closeEvent(self, event):
        try:
            if self.worker and getattr(self.worker, 'is_alive', lambda: False)():
                self.worker.stop()
        except Exception:
            pass
        self.attack_animation.stop_animation()
        event.accept()

if __name__ == "__main__":
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"  # Enable auto-scaling for high DPI
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    w = Main()
    w.showFullScreen()  # Change to full screen mode
    sys.exit(app.exec())
