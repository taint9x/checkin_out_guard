"""
Floating Weather Widget - Rainmeter-style overlay bằng PySide6
Window borderless, transparent, always-on-top, tự vẽ (custom paint), giống 1 Rainmeter skin.

Requirements:
    pip install PySide6 requests

Chạy: python weather_overlay.py
Kéo thả bằng chuột trái để di chuyển vị trí. Click phải để thoát.
"""

import sys
import requests
from PySide6.QtCore import Qt, QTimer, QPoint, QRectF
from PySide6.QtGui import QPainter, QColor, QFont, QLinearGradient, QPainterPath
from PySide6.QtWidgets import QApplication, QWidget

API_KEY = "YOUR_OPENWEATHERMAP_KEY"
CITY = "Ho Chi Minh City"
UPDATE_INTERVAL_MS = 10 * 60 * 1000  # 10 phút

WIDTH, HEIGHT = 220, 100
CORNER_RADIUS = 18


def fetch_weather() -> dict:
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": CITY, "appid": API_KEY, "units": "metric", "lang": "vi"}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return {
        "temp": round(data["main"]["temp"]),
        "desc": data["weather"][0]["description"].capitalize(),
        "city": data["name"],
    }


class WeatherOverlay(QWidget):
    def __init__(self):
        super().__init__()
        # --- Borderless + transparent + always-on-top, giống skin Rainmeter ---
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool  # không hiện trong taskbar/alt-tab
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(WIDTH, HEIGHT)
        self.move(50, 50)  # vị trí ban đầu trên màn hình

        self.weather = {"temp": "--", "desc": "Đang tải...", "city": CITY}
        self._drag_pos = None

        # Timer refresh data (không block UI)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(UPDATE_INTERVAL_MS)
        self.refresh()

    def refresh(self):
        try:
            self.weather = fetch_weather()
        except Exception:
            self.weather["desc"] = "Lỗi kết nối"
        self.update()  # trigger repaint

    # ---- Custom paint: đây là phần tạo ra visual đẹp giống Rainmeter ----
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Nền bo góc, gradient mờ (glassmorphism-style)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()),
                             CORNER_RADIUS, CORNER_RADIUS)

        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(20, 20, 30, 200))
        gradient.setColorAt(1, QColor(20, 20, 30, 160))
        painter.fillPath(path, gradient)

        # Nhiệt độ (font lớn)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI", 26, QFont.Bold))
        painter.drawText(QRectF(16, 8, self.width() - 32, 50),
                          Qt.AlignLeft | Qt.AlignVCenter,
                          f"{self.weather['temp']}°C")

        # Mô tả + city (font nhỏ, mờ hơn)
        painter.setPen(QColor(200, 200, 210))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(QRectF(16, 55, self.width() - 32, 20),
                          Qt.AlignLeft, self.weather["desc"])
        painter.drawText(QRectF(16, 75, self.width() - 32, 20),
                          Qt.AlignLeft, self.weather["city"])

    # ---- Cho phép kéo thả di chuyển widget bằng chuột trái ----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
        elif event.button() == Qt.RightButton:
            QApplication.quit()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    widget = WeatherOverlay()
    widget.show()
    sys.exit(app.exec())