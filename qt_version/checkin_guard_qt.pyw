# -*- coding: utf-8 -*-
"""
Checkin Guard (ban PySide6/Qt) - Tool nhac nho check-in / check-out.

Khac biet so voi ban tkinter + pystray (new_version):
  - KHONG dung tray icon. Thay vao do la 1 WIDGET noi always-on-top de len
    taskbar (canh khay he thong), ve custom bang QPainter: nen gradient bo
    tron, label + nut Check-in. Click -> mo CHECKIN_URL. Keo tha de doi cho.
  - Toan bo chay 1 thread duy nhat voi Qt event loop (khong can thread rieng
    cho message pump hay icon nhu ban tkinter).
  - Bat su kien resume sau Sleep/Hibernate bang QAbstractNativeEventFilter
    (Qt nhan WM_POWERBROADCAST truc tiep) -> khong can pywin32.
  - Chi phu thuoc dung 1 thu vien: PySide6.

Chuc nang giu nguyen:
  - Popup modal always-on-top khi login / resume, khong co nut X, khong dong
    duoc bang Alt+F4. Chi dong khi bam "Xac nhan roi".
  - Nut mo website KHONG dong popup.
  - Gay chu y bang PULSE muot theo dot (khong nhap nhay gat) trong khung gio
    (UTC+7); tu im lang sau khi user da check-in/xac nhan (acknowledge).
  - Chong chay trung 2 instance (mutex, qua ctypes).

Khong yeu cau quyen Admin.
"""

import ctypes
import math
import os
import sys
import time
import webbrowser
import winreg
from ctypes import wintypes
from datetime import datetime, timedelta, timezone

from PySide6.QtCore import (Qt, QTimer, QPoint, QRectF,
                            QAbstractNativeEventFilter)
from PySide6.QtGui import (QPainter, QColor, QFont, QLinearGradient,
                           QPainterPath, QIcon, QPixmap)
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QMenu,
                               QPushButton, QHBoxLayout, QVBoxLayout,
                               QSystemTrayIcon)

# =========================================================================
# CAU HINH - user tu sua cac gia tri duoi day
# =========================================================================
CHECKIN_URL = "https://daohainam.com/"   # user tu thay URL that
POPUP_TITLE = "Check-in / Check-out Reminder"
POPUP_MESSAGE = "Have you checked in / checked out yet?"

BUTTON_OPEN_TEXT = "Not yet - open check-in website"
BUTTON_CONFIRM_TEXT = "Already done"

# Widget noi tren taskbar
WIDGET_LABEL = "MISA"                 # chu ben trai widget
WIDGET_BUTTON_TEXT = "Check-in"       # chu tren nut ben phai
WIDGET_BUTTON_DONE_TEXT = "✓ Done"    # chu tren nut sau khi user da xac nhan
WIDGET_TOOLTIP = "Check-in / Check-out - click to open, drag to move"
WIDGET_WIDTH = 152                    # kich thuoc widget (px)
WIDGET_HEIGHT = 34
WIDGET_OFFSET_RIGHT = 310             # cach mep phai man hinh (ne vung khay he thong)

# Hieu ung gay chu y: PULSE muot (chuyen mau dan theo hinh sin) theo tung
# DOT ngan roi nghi dai, thay vi nhap nhay bat/tat lien tuc.
# Ly do (UX research):
#   - Nhap nhay lien tuc vi pham WCAG 2.2.2 (noi dung nhay > 5s phai co cach
#     tat), gay met mat va bi nao "loc" ra sau vai phut (habituation/alarm
#     fatigue) -> vua kho chiu vua MAT tac dung nhac nho.
#   - Chuyen dong o ria man hinh (peripheral motion) rat manh trong viec keo
#     su chu y -> chi can vai giay chuyen dong la du, sau do nen im lang
#     va lap lai sau mot quang nghi de "danh thuc" lai su chu y.
#   - Trang thai can nho (chua check-in) the hien bang MAU NEN do on dinh,
#     khong can chuyen dong lien tuc.
# Cac che do:
#   "off"      - khong pulse
#   "popup"    - chi pulse khi popup nhac nho dang mo
#   "always"   - pulse lien tuc theo nhip dot/nghi
#   "schedule" - pulse trong khung gio ALERT_SCHEDULE va TU TAT sau khi user
#                bam Check-in / xac nhan (den khung gio sau moi bao lai)
WIDGET_ALERT_MODE = "schedule"
PULSE_PERIOD = 1.2          # do dai 1 nhip pulse (giay) - cham, em
PULSE_BURST_CYCLES = 10      # so nhip moi dot (10 nhip ~ 12s chuyen dong)
PULSE_REST_SECONDS = 120     # nghi giua 2 dot - du dai de khong gay kho chiu

# Khung gio nhac nho khi WIDGET_ALERT_MODE = "schedule". ("HH:MM","HH:MM"),
# tinh theo mui gio TZ_UTC_OFFSET (khong phu thuoc mui gio cua Windows).
ALERT_SCHEDULE = [
    ("08:00", "10:00"),   # nhac check-in buoi sang
    ("17:00", "19:00"),   # nhac check-out buoi chieu
]
TZ_UTC_OFFSET = 7         # UTC+7 (gio Viet Nam)

# Mau gradient cua widget: binh thuong (xanh), canh bao (do - dich cua pulse),
# va mau chu nut sau khi da xac nhan xong (xanh la).
COLOR_NORMAL = (QColor(0, 130, 220), QColor(0, 85, 155))
COLOR_ALERT = (QColor(235, 30, 45), QColor(160, 12, 25))
COLOR_DONE = QColor(16, 124, 16)

# Sau resume, 2 message PBT co the ban lien tiep cho cung 1 lan thuc day.
RESUME_DEBOUNCE_SECONDS = 15
# =========================================================================

WM_POWERBROADCAST = 0x0218
PBT_APMRESUMESUSPEND = 0x0007
PBT_APMRESUMEAUTOMATIC = 0x0012
ERROR_ALREADY_EXISTS = 183

# SetWindowPos: dung de ep widget noi len TREN taskbar. Taskbar cua Windows
# cung la cua so topmost nen Qt.WindowStaysOnTopHint chua du - Explorer dinh
# ky keo taskbar len tren, phai ep lai dinh ky.
HWND_TOP = 0
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010

# BAT BUOC khai bao argtypes: khong co thi ctypes truyen HWND_TOPMOST (-1)
# thanh int 32-bit khong sign-extend -> handle 0xFFFFFFFF khong hop le tren
# Windows 64-bit -> SetWindowPos fail AM THAM, widget khong bao gio duoc
# keo len lai sau khi bi taskbar de.
_user32 = ctypes.windll.user32
_user32.SetWindowPos.argtypes = [
    wintypes.HWND, wintypes.HWND,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_uint]
_user32.SetWindowPos.restype = wintypes.BOOL


def in_alert_schedule():
    """Gio hien tai (theo TZ_UTC_OFFSET) co nam trong khung gio nhac khong."""
    tz = timezone(timedelta(hours=TZ_UTC_OFFSET))
    now = datetime.now(tz)
    now_minutes = now.hour * 60 + now.minute
    for start, end in ALERT_SCHEDULE:
        start_h, start_m = map(int, start.split(":"))
        end_h, end_m = map(int, end.split(":"))
        if start_h * 60 + start_m <= now_minutes < end_h * 60 + end_m:
            return True
    return False


def lerp_color(c1, c2, t):
    """Tron 2 mau theo ty le t (0.0 = c1, 1.0 = c2) - dung cho pulse muot."""
    return QColor(
        round(c1.red() + (c2.red() - c1.red()) * t),
        round(c1.green() + (c2.green() - c1.green()) * t),
        round(c1.blue() + (c2.blue() - c1.blue()) * t))


def make_tray_qicon(colors=COLOR_NORMAL):
    """Ve icon cho system tray bang QPainter: nen gradient bo goc + chu
    WIDGET_LABEL (label >= 4 ky tu tu tach 2 hang de chu to hon).

    colors: cap mau gradient - COLOR_NORMAL (xanh) hoac COLOR_ALERT (do,
    dung cho hieu ung nhay cua tray icon khi widget dang an).
    """
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)

    rect = QRectF(0, 0, size, size)
    path = QPainterPath()
    path.addRoundedRect(rect, 12, 12)
    gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    gradient.setColorAt(0.0, colors[0])
    gradient.setColorAt(1.0, colors[1])
    p.fillPath(path, gradient)

    label = WIDGET_LABEL
    if len(label) >= 4:
        half = (len(label) + 1) // 2
        lines = [label[:half], label[half:]]
    else:
        lines = [label]

    p.setPen(QColor(255, 255, 255))
    font = QFont("Segoe UI", 0, QFont.Bold)
    font.setPixelSize(26 if len(lines) > 1 else 38)
    p.setFont(font)
    band_h = size / len(lines)
    for i, text in enumerate(lines):
        p.drawText(QRectF(0, i * band_h, size, band_h), Qt.AlignCenter, text)
    p.end()
    return QIcon(pixmap)


class PowerEventFilter(QAbstractNativeEventFilter):
    """Bat WM_POWERBROADCAST tu native event cua Qt - khong can pywin32.

    Qt tu nhan message nay cho moi top-level window cua process, nen chi
    can 1 filter cai vao QApplication.
    """

    def __init__(self, on_resume):
        super().__init__()
        self._on_resume = on_resume

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if (msg.message == WM_POWERBROADCAST and
                    msg.wParam in (PBT_APMRESUMESUSPEND,
                                   PBT_APMRESUMEAUTOMATIC)):
                self._on_resume()
        return False, 0


class TaskbarWidget(QWidget):
    """Widget noi de len taskbar: nen gradient bo tron + label + nut Check-in.

    - Click trai (khong keo) -> mo CHECKIN_URL.
    - Giu chuot keo -> di chuyen widget den vi tri khac.
    - Click phai -> menu: Check-in / Dat lai vi tri / Thoat.
    """

    def __init__(self, controller):
        # Qt.Tool: khong hien nut rieng tren taskbar/Alt-Tab.
        super().__init__(None, Qt.FramelessWindowHint |
                         Qt.WindowStaysOnTopHint | Qt.Tool)
        self._controller = controller
        self._alert_level = 0.0       # 0.0 = mau binh thuong, 1.0 = mau canh bao
        self._done = False            # True = user da xac nhan trong khung gio
        self._press_global = None     # vi tri chuot luc bam (phan biet click/keo)
        self._press_window = None
        self._moved = False

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(WIDGET_WIDTH, WIDGET_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(WIDGET_TOOLTIP)

    def set_alert_level(self, level):
        """Muc canh bao 0.0-1.0, dieu khien boi animation pulse."""
        if level != self._alert_level:
            self._alert_level = level
            self.update()  # ve lai voi mau da tron

    def set_done(self, done):
        if done != self._done:
            self._done = done
            self.update()

    def _button_rect(self):
        """Vung nut Check-in (pill trang ben phai)."""
        h = self.height()
        btn_w = 88
        return QRectF(self.width() - btn_w - 5, 5, btn_w, h - 10)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Nen pill gradient: tron muot giua mau binh thuong va mau canh bao
        # theo _alert_level (0..1) de tao pulse em thay vi nhay bat/tat.
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = rect.height() / 2
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        level = self._alert_level
        top_color = lerp_color(COLOR_NORMAL[0], COLOR_ALERT[0], level)
        bottom_color = lerp_color(COLOR_NORMAL[1], COLOR_ALERT[1], level)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0.0, top_color)
        gradient.setColorAt(1.0, bottom_color)
        p.fillPath(path, gradient)

        # Vien sang mo cho co chieu sau.
        p.setPen(QColor(255, 255, 255, 70))
        p.drawPath(path)

        # Label ben trai.
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        btn = self._button_rect()
        label_rect = QRectF(16, 0, btn.left() - 20, self.height())
        p.drawText(label_rect, Qt.AlignVCenter | Qt.AlignLeft, WIDGET_LABEL)

        # Nut Check-in: pill trang, chu mau theo trang thai.
        btn_path = QPainterPath()
        btn_path.addRoundedRect(btn, btn.height() / 2, btn.height() / 2)
        p.fillPath(btn_path, QColor(255, 255, 255, 240))
        # Sau khi user da xac nhan trong khung gio: nut chuyen "✓ Done" xanh
        # la - tin hieu trang thai ro rang, khong can chuyen dong.
        if self._done:
            p.setPen(COLOR_DONE)
            button_text = WIDGET_BUTTON_DONE_TEXT
        else:
            p.setPen(lerp_color(COLOR_NORMAL[1], COLOR_ALERT[1], level))
            button_text = WIDGET_BUTTON_TEXT
        p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        p.drawText(btn, Qt.AlignCenter, button_text)

    # --- chuot: phan biet click (mo URL) va keo (di chuyen widget) --------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_global = event.globalPosition().toPoint()
            self._press_window = self.pos()
            self._moved = False

    def mouseMoveEvent(self, event):
        if self._press_global is not None and (event.buttons() & Qt.LeftButton):
            delta = event.globalPosition().toPoint() - self._press_global
            if self._moved or delta.manhattanLength() > 6:
                self._moved = True
                self.move(self._press_window + delta)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self._moved:
                self._controller.open_url()
            self._press_global = None

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("Check-in / Check-out", self._controller.open_url)
        menu.addAction("Reset position", self._controller.place_widget)
        # "Hide": an widget NGAY LAP TUC (ke ca dang trong khung gio nhac),
        # dong thoi hien icon o system tray de co duong "Show widget".
        # Widget giu nguyen trang thai an cho den khi user tu bam "Show
        # widget" - toi khung gio nhac, CHI tray icon nhap nhay, khong tu
        # hien widget hay mo popup.
        menu.addAction("Hide to system tray",
                       lambda: self._controller.set_user_hidden(True))
        menu.addSeparator()
        menu.addAction("Exit", self._controller.quit)
        menu.exec(event.globalPos())


class ReminderPopup(QWidget):
    """Popup modal nhac nho: khong co X, khong dong duoc bang Alt+F4.

    Chi dong khi bam "Xac nhan roi". Nut mo website KHONG dong popup.
    """

    def __init__(self, controller):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self._controller = controller
        self._allow_close = False

        # ApplicationModal: chan tuong tac voi cac cua so khac cua app
        # (tuong duong grab_set ben tkinter).
        self.setWindowModality(Qt.ApplicationModal)
        self.setAttribute(Qt.WA_TranslucentBackground)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QWidget(objectName="card")
        outer.addWidget(card)

        v = QVBoxLayout(card)
        v.setContentsMargins(34, 26, 34, 26)
        v.setSpacing(14)

        title = QLabel(POPUP_TITLE, objectName="title")
        title.setAlignment(Qt.AlignCenter)
        message = QLabel(POPUP_MESSAGE, objectName="message")
        message.setAlignment(Qt.AlignCenter)
        v.addWidget(title)
        v.addWidget(message)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        btn_open = QPushButton(BUTTON_OPEN_TEXT, objectName="open")
        btn_open.setCursor(Qt.PointingHandCursor)
        # Di qua controller.open_url de duoc tinh la "da hanh dong"
        # (acknowledge) -> tat pulse trong khung gio hien tai.
        btn_open.clicked.connect(controller.open_url)
        btn_confirm = QPushButton(BUTTON_CONFIRM_TEXT, objectName="confirm")
        btn_confirm.setCursor(Qt.PointingHandCursor)
        btn_confirm.clicked.connect(self._confirm)
        buttons.addWidget(btn_open)
        buttons.addWidget(btn_confirm)
        v.addLayout(buttons)

        self.setStyleSheet("""
            #card { background: #ffffff; border: 1px solid #c8c8c8;
                    border-radius: 14px; }
            #title { font: bold 15pt "Segoe UI"; color: #c0392b;
                     background: transparent; border: none; }
            #message { font: 12pt "Segoe UI"; color: #202020;
                       background: transparent; border: none; }
            QPushButton { color: white; border: none; border-radius: 8px;
                          padding: 11px 20px; font: bold 10.5pt "Segoe UI"; }
            #open { background: #0078d4; }
            #open:hover { background: #005a9e; }
            #confirm { background: #107c10; }
            #confirm:hover { background: #0b5c0b; }
        """)

        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - QPoint(self.width() // 2,
                                           self.height() // 2))

        # Dinh ky keo popup len tren cung phong khi app khac chiem topmost.
        self._raise_timer = QTimer(self)
        self._raise_timer.timeout.connect(self._keep_on_top)
        self._raise_timer.start(1000)

    def _keep_on_top(self):
        self.raise_()
        self.activateWindow()

    def _confirm(self):
        self._allow_close = True
        self.close()

    def closeEvent(self, event):
        # Chan Alt+F4 va moi lenh close khac - chi cho dong qua _confirm().
        if not self._allow_close:
            event.ignore()
            return
        self._raise_timer.stop()
        self._controller.on_popup_closed()
        event.accept()


class Controller:
    """Ket noi cac thanh phan: widget taskbar, popup, blink timer, resume."""

    def __init__(self, app):
        self.app = app
        self.popup = None
        self.popup_visible = False
        self.last_popup_time = 0.0
        self.user_hidden = False        # True = user da chon "Hide" trong menu
        self._prev_in_schedule = False  # de phat hien THOI DIEM vao khung gio
        self._ack_done = False          # user da check-in/xac nhan trong khung gio
        self._burst_until = 0.0         # dot pulse hien tai ket thuc luc (epoch)
        self._next_burst_at = 0.0       # dot pulse ke tiep bat dau luc (epoch)

        self.widget = TaskbarWidget(self)
        self.place_widget()
        self.widget.show()

        # Icon system tray: CHI hien khi widget dang an (la duong quay lai).
        # Click trai -> mo CHECKIN_URL; click phai -> menu co "Show widget".
        # Chuan bi san 2 icon (xanh/do) cho hieu ung nhay cua tray.
        self._tray_icon_normal = make_tray_qicon(COLOR_NORMAL)
        self._tray_icon_alert = make_tray_qicon(COLOR_ALERT)
        self._tray_icon_state = "normal"   # icon dang hien: "normal" | "alert"
        self._tray_promote_scheduled = False
        self.tray = QSystemTrayIcon(self._tray_icon_normal)
        self.tray.setToolTip(WIDGET_TOOLTIP)
        self._tray_menu = QMenu()  # giu reference de khong bi GC
        self._tray_menu.addAction("Show widget",
                                  lambda: self.set_user_hidden(False))
        self._tray_menu.addAction("Check-in / Check-out", self.open_url)
        self._tray_menu.addSeparator()
        self._tray_menu.addAction("Exit", self.quit)
        self.tray.setContextMenu(self._tray_menu)
        self.tray.activated.connect(self._on_tray_activated)

        # Ep widget len tren taskbar va lap lai lien tuc - neu khong, Explorer
        # se keo taskbar de len widget moi khi user tuong tac voi taskbar
        # (ca 2 deu la topmost, cai nao duoc raise sau se thang).
        # Chu ky 150ms de widget bat len lai gan nhu tuc thi sau khi bi de;
        # SetWindowPos voi NOACTIVATE/NOMOVE/NOSIZE rat nhe, khong cuop focus.
        self._assert_widget_topmost()
        self._topmost_timer = QTimer()
        self._topmost_timer.timeout.connect(self._assert_widget_topmost)
        self._topmost_timer.start(150)

        # Timer trang thai (0.5s): an/hien theo schedule + lap lich dot pulse.
        self._state_timer = QTimer()
        self._state_timer.timeout.connect(self._state_tick)
        self._state_timer.start(500)

        # Timer animation pulse (~25fps): CHI chay trong luc co dot pulse,
        # het dot tu dung de khong ton CPU.
        self._anim_timer = QTimer()
        self._anim_timer.setInterval(40)
        self._anim_timer.timeout.connect(self._anim_tick)

        # Bat su kien resume sau Sleep/Hibernate.
        self._power_filter = PowerEventFilter(self._on_resume)
        app.installNativeEventFilter(self._power_filter)

        # Popup ngay khi khoi dong (truong hop vua login vao Windows).
        QTimer.singleShot(500, self.show_popup)

    # --- vi tri widget: nam de len dai taskbar, ben trai khay he thong ----
    def place_widget(self):
        screen = QApplication.primaryScreen()
        full = screen.geometry()
        avail = screen.availableGeometry()
        taskbar_height = full.height() - avail.height()

        if taskbar_height >= WIDGET_HEIGHT and avail.y() == full.y():
            # Taskbar nam duoi -> dat widget vao giua dai taskbar.
            y = avail.y() + avail.height() + (taskbar_height - WIDGET_HEIGHT) // 2
        else:
            # Taskbar an/tu dong an hoac nam canh khac -> dat sat mep duoi.
            y = full.y() + full.height() - WIDGET_HEIGHT - 8
        x = full.x() + full.width() - WIDGET_OFFSET_RIGHT - WIDGET_WIDTH
        self.widget.move(x, y)

    def _assert_widget_topmost(self):
        if not self.widget.isVisible():
            return  # dang an theo schedule - khong can ep z-order
        hwnd = int(self.widget.winId())
        flags = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
        # HWND_TOPMOST: dam bao co topmost. Voi cua so DA topmost thi lenh nay
        # la no-op ve z-order, nen can them HWND_TOP de day len DAU nhom
        # topmost (tren ca taskbar vua duoc Explorer raise).
        _user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        _user32.SetWindowPos(hwnd, HWND_TOP, 0, 0, 0, 0, flags)

    def _promote_tray_icon(self):
        """Ghim icon tray ra NGOAI taskbar (canh dong ho/wifi) thay vi bi
        Windows giau vao khay an sau nut mui ten.

        Windows 11 (22H2+) luu cai dat nay o registry user-scope:
          HKCU\\Control Panel\\NotifyIconSettings\\<id>\\IsPromoted = 1
        Khong can Admin. Windows 10 khong co key nay -> bo qua.

        QUAN TRONG cho ban build exe: so sanh theo TEN FILE cua
        sys.executable - khi chay tu source la "pythonw.exe", khi build
        PyInstaller la "checkin_reminder.exe" - nen hoat dong cho ca 2.
        (ExecutablePath trong registry co the o dang GUID known-folder,
        vi du "{6D809377-...}\\Python313\\pythonw.exe", nen KHONG the so
        sanh duong dan day du.)
        """
        my_exe = os.path.basename(sys.executable).lower()
        try:
            base = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                  r"Control Panel\NotifyIconSettings")
        except OSError:
            return  # Windows 10 hoac key chua ton tai
        try:
            index = 0
            while True:
                try:
                    sub_name = winreg.EnumKey(base, index)
                except OSError:
                    break  # het subkey
                index += 1
                try:
                    sub = winreg.OpenKey(
                        base, sub_name, 0,
                        winreg.KEY_READ | winreg.KEY_SET_VALUE)
                except OSError:
                    continue
                try:
                    exe_path, _ = winreg.QueryValueEx(sub, "ExecutablePath")
                    if os.path.basename(str(exe_path)).lower() == my_exe:
                        winreg.SetValueEx(sub, "IsPromoted", 0,
                                          winreg.REG_DWORD, 1)
                except OSError:
                    pass
                finally:
                    winreg.CloseKey(sub)
        finally:
            winreg.CloseKey(base)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # click trai
            self.open_url()

    # --- cac action ---------------------------------------------------
    def open_url(self):
        webbrowser.open(CHECKIN_URL)
        # User da hanh dong (mo trang check-in) -> coi nhu acknowledge,
        # tat pulse cho het khung gio hien tai.
        self._ack_done = True

    def quit(self):
        self.app.quit()

    def _on_resume(self):
        # Debounce: 1 lan resume co the ban 2 message PBT lien tiep.
        if time.time() - self.last_popup_time >= RESUME_DEBOUNCE_SECONDS:
            self.show_popup()
        elif self.popup is not None:
            self.popup.raise_()

    def show_popup(self):
        if self.popup is not None:
            self.popup.raise_()
            self.popup.activateWindow()
            return
        self.last_popup_time = time.time()
        self.popup_visible = True
        self.popup = ReminderPopup(self)
        self.popup.show()
        self.popup.raise_()
        self.popup.activateWindow()

    def on_popup_closed(self):
        # Bam "Already done" = user khang dinh da check-in -> acknowledge.
        self.popup = None
        self.popup_visible = False
        self._ack_done = True

    # --- an/hien theo trang thai user + schedule --------------------------
    def set_user_hidden(self, hidden):
        self.user_hidden = hidden
        self._update_widget_state()

    def _update_widget_state(self):
        """An/hien widget theo trang thai user + schedule.

        Quy tac:
          - Bam "An" -> an NGAY, ke ca dang trong khung gio.
          - Vao THOI DIEM BAT DAU 1 khung gio (chuyen tu ngoai -> trong,
            vi du 08:00 / 17:00) -> xoa trang thai an, tu hien widget lai.
          - Ra khoi khung gio KHONG lam thay doi hien/an (widget dang hien
            thi van hien tiep, chi tat nhap nhay).

        Vi du: 09:05 bam An -> an; 17:00 tu hien + nhay; 17:05 bam An -> an
        tiep den 08:00 sang hom sau.

        Tra ve in_schedule de _blink_tick dung tiep.
        """
        in_schedule = in_alert_schedule()
        if in_schedule and not self._prev_in_schedule:
            # Canh bat dau khung gio: chi reset trang thai "da xac nhan"
            # cua khung gio truoc. KHONG tu hien widget / khong mo popup -
            # neu user da chon Hide thi ton trong lua chon do, chi nhac
            # bang tray icon nhap nhay (xem _anim_tick).
            self._ack_done = False
        self._prev_in_schedule = in_schedule

        desired_visible = not self.user_hidden
        if desired_visible and not self.widget.isVisible():
            self.widget.show()
            self._assert_widget_topmost()
        elif not desired_visible and self.widget.isVisible():
            self.widget.hide()

        # Tray icon la "duong quay lai" khi widget an -> hien nguoc voi widget.
        tray_visible = not desired_visible
        self.tray.setVisible(tray_visible)
        # Lan dau tray icon xuat hien: doi vai giay cho Windows tao entry
        # registry cua icon roi "ghim" no ra ngoai taskbar (canh wifi/pin).
        if tray_visible and not self._tray_promote_scheduled:
            self._tray_promote_scheduled = True
            QTimer.singleShot(4000, self._promote_tray_icon)

        return in_schedule

    # --- pulse gay chu y --------------------------------------------------
    def _state_tick(self):
        """Moi 0.5s: cap nhat an/hien, trang thai done, va lap lich dot pulse.

        Mo hinh pulse: khi can gay chu y, chay 1 DOT gom PULSE_BURST_CYCLES
        nhip muot (~3.6s) roi NGHI PULSE_REST_SECONDS. Sau khi user da
        check-in/xac nhan (ack) trong khung gio -> im lang hoan toan, nut
        chuyen "✓ Done" xanh la.
        """
        in_schedule = self._update_widget_state()
        # Khong phu thuoc widget dang hien hay an: khi widget an xuong tray,
        # tray icon se nhay thay (cung rule) - xem _anim_tick.
        alert_active = (
            WIDGET_ALERT_MODE == "always"
            or (WIDGET_ALERT_MODE == "popup" and self.popup_visible)
            or (WIDGET_ALERT_MODE == "schedule" and in_schedule
                and not self._ack_done))

        now = time.time()
        if alert_active:
            if now >= self._next_burst_at:
                self._burst_until = now + PULSE_PERIOD * PULSE_BURST_CYCLES
                self._next_burst_at = now + PULSE_REST_SECONDS
                if not self._anim_timer.isActive():
                    self._anim_timer.start()
        else:
            # Het canh bao (ack / het gio) -> cat dot dang chay va reset
            # lich de lan canh bao sau pulse ngay lap tuc.
            self._burst_until = 0.0
            self._next_burst_at = 0.0

        # Khi khong co dot pulse dang chay, tray icon hien mau TINH theo
        # trang thai: ngoai gio -> do, trong gio da check-in -> xanh.
        if not self._anim_timer.isActive():
            self._set_tray_icon(self._tray_base_icon())

        # Nut "✓ Done" chi co y nghia trong khung gio da xac nhan.
        self.widget.set_done(WIDGET_ALERT_MODE == "schedule"
                             and in_schedule and self._ack_done)

    def _set_tray_icon(self, state):
        """Doi icon tray ("normal"=xanh / "alert"=do) - chi setIcon khi doi."""
        if state != self._tray_icon_state:
            self._tray_icon_state = state
            self.tray.setIcon(self._tray_icon_alert if state == "alert"
                              else self._tray_icon_normal)

    def _tray_base_icon(self):
        """Mau TINH cua tray icon khi khong co nhip nhay de len:

          - Trong khung gio, DA check-in/xac nhan -> XANH ("normal")
          - Moi truong hop con lai -> DO ("alert"):
              + ngoai khung gio (bat ke da check-in hay chua)
              + trong khung gio nhung CHUA check-in (ke ca luc dang nghi
                giua 2 dot pulse - PULSE_REST_SECONDS)

        Chi ap dung cho mode "schedule"; cac mode khac giu icon xanh.
        """
        if WIDGET_ALERT_MODE == "schedule":
            if in_alert_schedule() and self._ack_done:
                return "normal"
            return "alert"
        return "normal"

    def _anim_tick(self):
        """~25fps trong luc co dot pulse: tinh muc canh bao theo hinh sin
        (0 -> 1 -> 0 moi PULSE_PERIOD giay) de mau chuyen em, khong giat.

        Ap dung cho ca widget (mau tron muot) lan tray icon (doi xanh/do
        theo nhip - tray khong lam muot duoc vi setIcon la roi rac).
        """
        now = time.time()
        if now < self._burst_until:
            phase = (now % PULSE_PERIOD) / PULSE_PERIOD
            level = 0.5 * (1.0 - math.cos(2.0 * math.pi * phase))
            self.widget.set_alert_level(level)
            self._set_tray_icon("alert" if level >= 0.5 else "normal")
        else:
            self.widget.set_alert_level(0.0)
            self._anim_timer.stop()
            # Het dot -> tra tray icon ve mau tinh theo trang thai.
            self._set_tray_icon(self._tray_base_icon())


# Handle mutex giu o bien global de khong bi giai phong (xem ban tkinter).
_single_instance_mutex = None


def main():
    global _single_instance_mutex
    kernel32 = ctypes.windll.kernel32
    _single_instance_mutex = kernel32.CreateMutexW(
        None, False, "CheckinGuardQt_SingleInstanceMutex")
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # dong popup khong lam thoat app
    controller = Controller(app)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
