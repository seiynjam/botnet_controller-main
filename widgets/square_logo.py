# widgets/round_logo.py
# -*- coding: utf-8 -*-
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel

class SquareLogo(QLabel):
    def __init__(self, image_path: str, size=220, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setStyleSheet("background:white;")  # ไม่มี border-radius แล้ว
        pm = QPixmap(image_path)
        if not pm.isNull():
            self.setPixmap(pm)
        self.setScaledContents(True)  # ยืดภาพให้เต็มกรอบ
