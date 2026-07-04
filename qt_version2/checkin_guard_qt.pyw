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
from PySide6.QtGui import (QPainter, QColor, QFont,
                           QPainterPath, QIcon, QPixmap)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QMenu,
                               QPushButton, QHBoxLayout, QVBoxLayout,
                               QSystemTrayIcon)

# =========================================================================
# CAU HINH - user tu sua cac gia tri duoi day
# =========================================================================
CHECKIN_URL = "https://daohainam.com/"   # user tu thay URL that

# Khung gio nhac nho khi WIDGET_ALERT_MODE = "schedule". ("HH:MM","HH:MM"),
# tinh theo mui gio TZ_UTC_OFFSET (khong phu thuoc mui gio cua Windows).
ALERT_SCHEDULE = [
    ("08:00", "10:00"),   # nhac check-in buoi sang
    ("17:00", "19:00"),   # nhac check-out buoi chieu
]
TZ_UTC_OFFSET = 7         # UTC+7 (gio Viet Nam)

# Tieu de va noi dung popup nhac nho check-in / check-out.
POPUP_TITLE = "Check-in / Check-out Reminder"
POPUP_MESSAGE = "Have you checked in / checked out yet?"

BUTTON_OPEN_TEXT = "Not yet - open check-in website"
BUTTON_CONFIRM_TEXT = "Already done"

# Widget noi tren taskbar
WIDGET_LABEL = "MISA"                 # chu ben trai widget
WIDGET_BUTTON_TEXT = "Check-in"       # chu tren nut ben phai
WIDGET_BUTTON_DONE_TEXT = "✓ Done"    # chu tren nut sau khi user da xac nhan
WIDGET_TOOLTIP = "Check-in / Check-out - click to open, drag to move"
WIDGET_WIDTH = 180                    # kich thuoc widget (px) - du cho logo+MISA+Check-in
WIDGET_HEIGHT = 34
WIDGET_OFFSET_RIGHT = 310             # cach mep phai man hinh (ne vung khay he thong)
ACTION_SEGMENT_WIDTH = 88             # do rong doan "action" (Check-in/Done) ben phai pill

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
# So NHIP (option A: vong glow; option B: vong nhay) moi dot pulse. Do dai
# THUC TE cua 1 dot = PULSE_BURST_CYCLES * (nhip cua option dang active) -
# xem _state_tick._burst_cycle_seconds - nen doi GLOW_PERIOD/BOUNCE_PERIOD/
# BOUNCE_REST_SECONDS ben duoi KHONG lam thay doi SO LAN nhap nhay/nhay,
# chi doi TOC DO/do dai cua tung nhip.
PULSE_BURST_CYCLES = 10
PULSE_REST_SECONDS = 120     # nghi giua 2 dot - du dai de khong gay kho chiu


# Mau pill 2 tong (khop thiet ke trong reminder_widget_ux_options.html):
# doan "brand" (logo + MISA) nen xanh navy dam, doan "action" (Check-in)
# nen trang - CA 2 GIU NGUYEN, khong doi mau cung nua, xem 2 option gay chu
# y ben duoi. Mau chu nut sau khi da xac nhan xong.
COLOR_BRAND = QColor(0x12, 0x21, 0x3F)   # #12213F - khop .pill-brand trong HTML
COLOR_DONE = QColor(16, 124, 16)

# Widget: 2 hieu ung gay chu y luan phien theo dot pulse (xem
# reminder_widget_ux_options.html - option A va B). Pill KHONG doi mau cung
# nua o ca 2 option:
#   Option A - "soft glow pulse": vien pill phat sang mo dan/dam dan theo
#              nhip GLOW_PERIOD, pill giu nguyen mau.
#   Option B - "badge dot + bounce nhe": cham do nhap nhay LIEN TUC theo
#              nhip DOT_PERIOD suot dot pulse; pill thi nhay 1 VONG (nhip
#              BOUNCE_PERIOD, nhanh dut khoat - khop CSS keyframes
#              bounceOnce 0.6s) ROI DUNG YEN BOUNCE_REST_SECONDS moi lap
#              lai - khong nhay lien tuc khong nghi (de gay kho chiu).
# WIDGET_PULSE_STYLE chon option nao duoc dung cho cac dot pulse (theo lich
# PULSE_BURST_CYCLES/PULSE_REST_SECONDS o tren):
#   "both" - LUAN PHIEN A -> B -> A -> B... moi dot (mac dinh, nhu truoc gio)
#   "A"    - CHI dung Option A (soft glow pulse) cho moi dot
#   "B"    - CHI dung Option B (badge dot + bounce nhe) cho moi dot
WIDGET_PULSE_STYLE = "both"
# Mau glow Option A - SUA MA HEX o day de doi mau nhap nhay (vd doi sang
# xanh duong "#054AFF", do "#FF3B30", tim "#8E24AA"...).
WIDGET_GLOW_COLOR_HEX = "#FFC30E"      # vang cam (mac dinh)
COLOR_GLOW_A = QColor(WIDGET_GLOW_COLOR_HEX)
COLOR_DOT_B = QColor(255, 59, 48)     # #FF3B30 - mau cham do Option B
GLOW_PERIOD = 0.9       # option A: giay/nhip glow - khop CSS keyframes glowPulse
DOT_PERIOD = 0.9        # option B: giay/nhip cham do - khop CSS keyframes dotPulse
BOUNCE_PERIOD = 0.6     # option B: giay/1 VONG nhay - khop CSS keyframes bounceOnce
                        # (nhanh, dut khoat)
BOUNCE_REST_SECONDS = 1.5  # option B: dung yen giua 2 vong nhay (1-2 giay
                           # de khong gay kho chiu vi nhay lien tuc)
# Khoang trong (px) quanh pill de ve glow/nhay ma khong bi cat xen boi bien
# widget (widget nen trong suot nen phan ngoai pill khong hien gi neu tinh).
WIDGET_GLOW_MARGIN = 10

# Icon cho system tray - doc tu file SVG trong thu muc icons/ (canh file
# .pyw/.exe nay). 3 trang thai:
#   - mac dinh (ngoai khung gio, hoac khong bat che do "schedule")
#   - da check-in trong khung gio hien tai
#   - dang trong khung gio nhac nho MA CHUA check-in -> nhap nhay qua cac
#     frame duoi day de gay chu y (xem Controller._anim_tick).
TRAY_ICON_DEFAULT_FILE = "tray_default.svg"
TRAY_ICON_CHECKED_IN_FILE = "tray_checked_in.svg"
TRAY_ICON_PULSE_FILES = ["tray_pulse_1.svg", "tray_pulse_2.svg",
                         "tray_pulse_3.svg", "tray_pulse_4.svg"]
# Nhieu do phan giai cho cung 1 QIcon - Windows tu chon ban net nhat theo
# DPI cua man hinh (100%/125%/150%/200%...) thay vi phong to 1 anh nho ->
# do net cua icon tren khay he thong.
TRAY_ICON_SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
# Nhip doi frame nhap nhay cua tray (doc lap voi dot/nghi cua widget - xem
# ghi chu o Controller._tray_pulse_tick).
TRAY_PULSE_FRAME_MS = 150

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


# Keyframe (fraction 0..1, offset px) cua hieu ung bounceOnce trong
# reminder_widget_ux_options.html: 1 cu nhay len roi 1 cu nhay phu nho hon.
# Option B LAP LAI keyframe nay dung PULSE_BURST_CYCLES vong moi dot pulse
# (moi vong = BOUNCE_PERIOD giay nhay + BOUNCE_REST_SECONDS giay nghi) - xem
# Controller._anim_tick va Controller._burst_cycle_seconds.
_BOUNCE_KEYFRAMES = [(0.0, 0.0), (0.3, -6.0), (0.5, 0.0), (0.7, -3.0), (1.0, 0.0)]


def bounce_offset_at(fraction):
    """Noi suy tuyen tinh giua cac keyframe cua _BOUNCE_KEYFRAMES theo
    fraction (0..1 = vi tri trong 1 nhip BOUNCE_PERIOD hien tai)."""
    frac = max(0.0, min(1.0, fraction))
    for (f0, v0), (f1, v1) in zip(_BOUNCE_KEYFRAMES, _BOUNCE_KEYFRAMES[1:]):
        if frac <= f1:
            if f1 == f0:
                return v1
            t = (frac - f0) / (f1 - f0)
            return v0 + (v1 - v0) * t
    return _BOUNCE_KEYFRAMES[-1][1]


def _resource_path(*parts):
    """Duong dan toi resource (icons/...) - dung ca khi chay tu source lan
    khi da build exe bang PyInstaller (onefile giai nen vao sys._MEIPASS)."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


def load_tray_icon(filename, sizes=TRAY_ICON_SIZES):
    """Doc 1 file SVG trong thu muc icons/ va ve ra QIcon o NHIEU do phan
    giai (xem TRAY_ICON_SIZES) de Windows chon ban net nhat theo DPI thay
    vi phong to 1 bitmap nho ra (mo, trong "nho" hon thuc te).

    Dung QSvgRenderer + QPainter (thay vi QIcon(path) truc tiep) de khong
    phu thuoc iconengine plugin cua Qt luc dong goi PyInstaller - import
    QtSvg tuong minh dam bao PyInstaller nhan dien va dong goi Qt6Svg.
    Truyen targetRect tuong minh cho render() de SVG duoc VE LAI o dung
    kich thuoc moi pixmap (khong chi ve 1 lan roi scale bitmap).
    """
    path = _resource_path("icons", filename)
    icon = QIcon()
    for size in sizes:
        renderer = QSvgRenderer(path)
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        renderer.render(p, QRectF(0, 0, size, size))
        p.end()
        icon.addPixmap(pixmap)
    return icon


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
        self._done = False            # True = user da xac nhan trong khung gio
        self._glow_level = 0.0        # 0..1 - Option A: do sang cua vien glow
        self._dot_level = 0.0         # 0..1 - Option B: do "no" cua cham do
        self._bounce_offset = 0.0     # px - Option B: dich doc luc nhay 1 lan
        self._press_global = None     # vi tri chuot luc bam (phan biet click/keo)
        self._press_window = None
        self._moved = False

        # Logo canh chu WIDGET_LABEL - dung chung 1 anh voi icon tray mac
        # dinh (tray_default.svg) de dong bo nhan dien thuong hieu.
        # _logo_size la kich thuoc LOGICAL (doc lap DPI) dung de tinh layout;
        # _logo_pixmap.width() KHONG dung duoc cho viec nay vi QIcon.pixmap()
        # tra ve pixmap theo devicePixelRatio cua man hinh (vd man hinh scale
        # 225% se cho pixmap 54px cho size logical 24px) - lay nham se lam
        # sai lech toan bo layout (chu MISA bi day het cho / khong hien).
        self._logo_size = WIDGET_HEIGHT - 10
        self._logo_pixmap = load_tray_icon(TRAY_ICON_DEFAULT_FILE).pixmap(
            self._logo_size, self._logo_size)

        self.setAttribute(Qt.WA_TranslucentBackground)
        # Widget to hon kich thuoc pill thuc te WIDGET_GLOW_MARGIN moi ben,
        # de co cho ve glow (Option A) / nhay (Option B) ma khong bi bien
        # widget (trong suot) cat xen.
        self.setFixedSize(WIDGET_WIDTH + 2 * WIDGET_GLOW_MARGIN,
                          WIDGET_HEIGHT + 2 * WIDGET_GLOW_MARGIN)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(WIDGET_TOOLTIP)

    def set_done(self, done):
        if done != self._done:
            self._done = done
            self.update()

    def set_glow_level(self, level):
        """Option A - do sang cua vien glow quanh pill, 0.0-1.0."""
        if level != self._glow_level:
            self._glow_level = level
            self.update()

    def set_dot_level(self, level):
        """Option B - do "no" (scale+opacity) cua cham do bao hieu, 0.0-1.0."""
        if level != self._dot_level:
            self._dot_level = level
            self.update()

    def set_bounce_offset(self, offset):
        """Option B - dich doc (px, am = len tren) luc nhay 1 lan."""
        if offset != self._bounce_offset:
            self._bounce_offset = offset
            self.update()

    def _pill_rect(self):
        """Vung pill thuc te, khong tinh WIDGET_GLOW_MARGIN va bounce."""
        return QRectF(WIDGET_GLOW_MARGIN, WIDGET_GLOW_MARGIN,
                      WIDGET_WIDTH, WIDGET_HEIGHT)

    def _action_rect(self):
        """Vung doan 'action' (Check-in / Done, nen trang), tinh theo
        _pill_rect() - flush voi doan brand, khong con la nut noi rieng."""
        pill = self._pill_rect()
        return QRectF(pill.right() - ACTION_SEGMENT_WIDTH, pill.top(),
                     ACTION_SEGMENT_WIDTH, pill.height())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Option B nhay 1 lan: dich toan bo pill (khong dich glow benh A vi
        # A khong bounce) theo _bounce_offset.
        p.save()
        p.translate(0, self._bounce_offset)

        pill = self._pill_rect()
        radius = pill.height() / 2
        path = QPainterPath()
        path.addRoundedRect(pill, radius, radius)

        # Option A: glow mem quanh vien pill, do sang theo _glow_level thay
        # vi doi mau cung - ve 1 rounded-rect lon hon pill, mau glow trong
        # suot theo muc do, NAM DUOI pill nen chi phan "tran" ra ngoai la
        # thay duoc (giong box-shadow mo dan/dam dan cua CSS glowPulse).
        if self._glow_level > 0.0:
            extent = 2.0 + 6.0 * self._glow_level
            glow_rect = pill.adjusted(-extent, -extent, extent, extent)
            glow_path = QPainterPath()
            glow_path.addRoundedRect(glow_rect, glow_rect.height() / 2,
                                     glow_rect.height() / 2)
            glow_color = QColor(COLOR_GLOW_A)
            glow_color.setAlpha(int(150 * self._glow_level))
            p.fillPath(glow_path, glow_color)

        # Pill 2 tong mau (khop .pill-brand/.pill-action trong HTML): doan
        # "brand" (logo+MISA) nen navy dam, doan "action" (Check-in) nen
        # trang, ca 2 flush lien nhau trong CUNG 1 hinh bo tron - clip theo
        # duong bien pill de chi 2 dau NGOAI cung duoc bo tron, canh giua
        # (giua 2 doan) vuong goc.
        action = self._action_rect()
        p.save()
        p.setClipPath(path)
        p.fillRect(pill, QColor(255, 255, 255))       # nen doan action (trang)
        brand_rect = QRectF(pill.left(), pill.top(),
                            action.left() - pill.left(), pill.height())
        p.fillRect(brand_rect, COLOR_BRAND)             # nen doan brand (navy)
        p.restore()

        # Vien sang mo cho co chieu sau.
        p.setPen(QColor(255, 255, 255, 70))
        p.drawPath(path)

        # Logo (tray_default.svg) canh trai, tren nen navy.
        logo_size = self._logo_size
        logo_x = brand_rect.left() + 10
        logo_y = pill.top() + (pill.height() - logo_size) / 2
        p.drawPixmap(QRectF(logo_x, logo_y, logo_size, logo_size).toRect(),
                     self._logo_pixmap, self._logo_pixmap.rect())

        # Option B: cham do nho tren logo, "no" dan theo _dot_level (scale
        # 1->1.6, opacity 1->0.4 - khop CSS keyframes dotPulse). Vien trang
        # mong de noi bat tren logo nhieu mau.
        if self._dot_level > 0.0:
            base_r = 4.5
            dot_r = base_r * (1.0 + 0.6 * self._dot_level)
            dot_color = QColor(COLOR_DOT_B)
            dot_color.setAlpha(int(255 * (1.0 - 0.6 * self._dot_level)))
            dot_cx = logo_x + logo_size - 2
            dot_cy = logo_y + 2
            p.setPen(QColor(255, 255, 255, 220))
            p.setBrush(dot_color)
            p.drawEllipse(QRectF(dot_cx - dot_r, dot_cy - dot_r,
                                 dot_r * 2, dot_r * 2))

        # Label ben phai logo (chu trang tren nen navy - doan brand).
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        label_rect = QRectF(logo_x + logo_size + 6, pill.top(),
                            brand_rect.right() - (logo_x + logo_size + 6) - 4,
                            pill.height())
        p.drawText(label_rect, Qt.AlignVCenter | Qt.AlignLeft, WIDGET_LABEL)

        # Doan action (Check-in / Done): chu mau navy tren nen trang, hoac
        # xanh la khi da xac nhan xong.
        if self._done:
            p.setPen(COLOR_DONE)
            button_text = WIDGET_BUTTON_DONE_TEXT
        else:
            p.setPen(COLOR_BRAND)
            button_text = WIDGET_BUTTON_TEXT
        p.setFont(QFont("Segoe UI", 9, QFont.Bold))
        p.drawText(action, Qt.AlignCenter, button_text)
        p.restore()

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
        # "A" hoac "B" - dot pulse HIEN TAI/KE TIEP dung option nao (theo
        # WIDGET_PULSE_STYLE - xem _state_tick). Neu style = "both", khoi
        # tao "B" de dot dau tien (ngay khi vao khung gio) toggle thanh "A"
        # dung theo so do trang thai; neu style = "A"/"B" thi dung co dinh
        # option do ngay tu dau.
        self._active_option = ("B" if WIDGET_PULSE_STYLE == "both"
                                else WIDGET_PULSE_STYLE)
        # Option B: lich rieng cho tung VONG nhay cua pill (nhay
        # BOUNCE_PERIOD giay roi nghi BOUNCE_REST_SECONDS giay) - doc lap
        # voi lich dot/nghi PULSE_BURST_CYCLES/PULSE_REST_SECONDS o tren.
        self._bounce_start = 0.0        # vong nhay HIEN TAI bat dau luc (epoch)
        self._next_bounce_at = 0.0      # vong nhay KE TIEP duoc phep bat dau (epoch)

        self.widget = TaskbarWidget(self)
        self.place_widget()
        self.widget.show()

        # Icon system tray: CHI hien khi widget dang an (la duong quay lai).
        # Click trai -> mo CHECKIN_URL; click phai -> menu co "Show widget".
        # Chuan bi san icon mac dinh / da check-in / cac frame nhap nhay.
        self._tray_icon_default = load_tray_icon(TRAY_ICON_DEFAULT_FILE)
        self._tray_icon_checked_in = load_tray_icon(TRAY_ICON_CHECKED_IN_FILE)
        self._tray_icon_pulse = [load_tray_icon(f)
                                 for f in TRAY_ICON_PULSE_FILES]
        self._tray_icon_state = "default"  # "default" | "checked_in" | ("pulse", idx)
        self._tray_promote_scheduled = False
        self.tray = QSystemTrayIcon(self._tray_icon_default)
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
        # het dot tu dung de khong ton CPU. Dieu khien mau widget (lerp muot).
        self._anim_timer = QTimer()
        self._anim_timer.setInterval(40)
        self._anim_timer.timeout.connect(self._anim_tick)

        # Tray icon nhap nhay: chay LIEN TUC (khong theo dot/nghi cua widget)
        # suot khoang thoi gian con "canh bao" (vd trong khung gio ma chua
        # check-in) - vi tray nho, de bi bo qua, nen KHONG ap dung kieu
        # dot ngan + nghi dai nhu widget (nghi 120s se bi hieu nham la
        # "khong nhap nhay"). Chi dung khi het canh bao (da check-in / het
        # khung gio) thi dung han va tra ve icon tinh.
        self._tray_pulse_index = 0
        self._tray_pulse_timer = QTimer()
        self._tray_pulse_timer.setInterval(TRAY_PULSE_FRAME_MS)
        self._tray_pulse_timer.timeout.connect(self._tray_pulse_tick)

        # Bat su kien resume sau Sleep/Hibernate.
        self._power_filter = PowerEventFilter(self._on_resume)
        app.installNativeEventFilter(self._power_filter)

        # Popup ngay khi khoi dong (truong hop vua login vao Windows).
        QTimer.singleShot(500, self.show_popup)

    # --- vi tri widget: nam de len dai taskbar, ben trai khay he thong ----
    def place_widget(self):
        """Tinh vi tri sao cho PILL (khong phai toan bo widget - widget to
        hon pill WIDGET_GLOW_MARGIN moi ben de co cho ve glow/nhay) nam dung
        cho cu nhu truoc."""
        screen = QApplication.primaryScreen()
        full = screen.geometry()
        avail = screen.availableGeometry()
        taskbar_height = full.height() - avail.height()

        if taskbar_height >= WIDGET_HEIGHT and avail.y() == full.y():
            # Taskbar nam duoi -> dat pill vao giua dai taskbar.
            y_pill = avail.y() + avail.height() + (taskbar_height - WIDGET_HEIGHT) // 2
        else:
            # Taskbar an/tu dong an hoac nam canh khac -> dat sat mep duoi.
            y_pill = full.y() + full.height() - WIDGET_HEIGHT - 8
        x_pill = full.x() + full.width() - WIDGET_OFFSET_RIGHT - WIDGET_WIDTH
        self.widget.move(x_pill - WIDGET_GLOW_MARGIN, y_pill - WIDGET_GLOW_MARGIN)

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
            # Canh bat dau khung gio: reset trang thai "da xac nhan" cua
            # khung gio truoc, va dat lai de dot pulse DAU TIEN cua khung
            # gio nay la Option A khi WIDGET_PULSE_STYLE = "both" (xem so do
            # trang thai IDLE->ACTIVE_A); neu style co dinh "A"/"B" thi giu
            # nguyen option do. KHONG tu hien widget / khong mo popup - neu
            # user da chon Hide thi ton trong lua chon do, chi nhac bang
            # tray icon nhap nhay.
            self._ack_done = False
            self._active_option = ("B" if WIDGET_PULSE_STYLE == "both"
                                    else WIDGET_PULSE_STYLE)
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

        Widget (mau gradient, luon hien tren taskbar): pulse theo MO HINH
        DOT - chay dung PULSE_BURST_CYCLES nhip (vong glow o Option A / vong
        nhay o Option B) roi NGHI PULSE_REST_SECONDS, tranh gay kho chiu vi
        widget luon o trong tam mat. Do dai THUC TE cua 1 dot phu thuoc
        option dang active (xem _burst_cycle_seconds) de SO LAN nhap nhay/
        nhay luon dung bang PULSE_BURST_CYCLES bat ke GLOW_PERIOD/
        BOUNCE_PERIOD/BOUNCE_REST_SECONDS la bao nhieu. Tray icon (nho, de
        bi bo qua khi ẩn xuống khay) thi nhap nhay LIEN TUC suot luc con
        canh bao - xem _tray_pulse_tick. Sau khi user da check-in/xac nhan
        (ack) trong khung gio -> ca 2 im lang, nut chuyen "✓ Done" xanh la.
        """
        in_schedule = self._update_widget_state()
        alert_active = (
            WIDGET_ALERT_MODE == "always"
            or (WIDGET_ALERT_MODE == "popup" and self.popup_visible)
            or (WIDGET_ALERT_MODE == "schedule" and in_schedule
                and not self._ack_done))

        now = time.time()
        if alert_active:
            if now >= self._next_burst_at:
                # Bat dau 1 dot pulse MOI. Neu WIDGET_PULSE_STYLE = "both":
                # luan phien Option A <-> B (so do trang thai
                # ATTENTION_ACTIVE_A <-> ATTENTION_ACTIVE_B). Neu style co
                # dinh "A"/"B" thi luon dung option do, khong luan phien.
                if WIDGET_PULSE_STYLE == "both":
                    self._active_option = ("A" if self._active_option == "B"
                                            else "B")
                else:
                    self._active_option = WIDGET_PULSE_STYLE
                self._burst_until = now + (self._burst_cycle_seconds()
                                            * PULSE_BURST_CYCLES)
                self._next_burst_at = now + PULSE_REST_SECONDS
                if not self._anim_timer.isActive():
                    self._anim_timer.start()
        else:
            # Het canh bao (ack / het gio) -> cat dot dang chay va reset
            # lich de lan canh bao sau pulse ngay lap tuc.
            self._burst_until = 0.0
            self._next_burst_at = 0.0

        # Tray: nhap nhay LIEN TUC (khong theo dot/nghi) suot luc alert_active;
        # dung han va tra ve icon tinh ngay khi het canh bao.
        if alert_active:
            if not self._tray_pulse_timer.isActive():
                self._tray_pulse_index = 0
                self._tray_pulse_timer.start()
                self._tray_pulse_tick()  # hien frame dau ngay, khong doi 300ms
        else:
            if self._tray_pulse_timer.isActive():
                self._tray_pulse_timer.stop()
            self._set_tray_icon(self._tray_base_icon())

        # Nut "✓ Done" chi co y nghia trong khung gio da xac nhan.
        self.widget.set_done(WIDGET_ALERT_MODE == "schedule"
                             and in_schedule and self._ack_done)

    def _set_tray_icon(self, state):
        """Doi icon tray tinh ("default" / "checked_in") - chi setIcon khi doi."""
        if state != self._tray_icon_state:
            self._tray_icon_state = state
            self.tray.setIcon(self._tray_icon_checked_in if state == "checked_in"
                              else self._tray_icon_default)

    def _tray_pulse_tick(self):
        """Chay moi TRAY_PULSE_FRAME_MS suot luc alert_active: doi tray icon
        sang frame tray_pulse_{x} ke tiep, lap vong qua het cac frame - tao
        hieu ung nhap nhay lien tuc, de nhan biet hon ma khong "gat" (van la
        doi hinh SVG chu khong nhay bat/tat tho)."""
        idx = self._tray_pulse_index
        state = ("pulse", idx)
        if state != self._tray_icon_state:
            self._tray_icon_state = state
            self.tray.setIcon(self._tray_icon_pulse[idx])
        self._tray_pulse_index = (idx + 1) % len(self._tray_icon_pulse)

    def _tray_base_icon(self):
        """Trang thai TINH cua tray icon khi khong con canh bao (alert_active
        = False): trong khung gio DA check-in/xac nhan -> "checked_in",
        moi truong hop con lai -> "default". Chi ap dung y nghia "checked_in"
        cho mode "schedule"; cac mode khac giu icon mac dinh."""
        if WIDGET_ALERT_MODE == "schedule":
            if in_alert_schedule() and self._ack_done:
                return "checked_in"
            return "default"
        return "default"

    def _burst_cycle_seconds(self):
        """Do dai (giay) cua 1 NHIP thuoc option dang active (_active_option),
        dung de tinh do dai 1 dot pulse = PULSE_BURST_CYCLES * gia tri nay -
        xem _state_tick. Option A: 1 nhip = 1 vong glow (GLOW_PERIOD). Option
        B: 1 nhip = 1 vong nhay VA khoang nghi giua 2 vong (BOUNCE_PERIOD +
        BOUNCE_REST_SECONDS), vi do la chu ky thuc te cua _next_bounce_at
        trong _anim_tick."""
        if self._active_option == "A":
            return GLOW_PERIOD
        return BOUNCE_PERIOD + BOUNCE_REST_SECONDS

    def _anim_tick(self):
        """~25fps CHI trong luc co dot pulse cua WIDGET: dieu khien Option A
        (glow mem, nhip GLOW_PERIOD, lap lai lien tuc) hoac Option B (cham
        do nhip DOT_PERIOD lap lai lien tuc, pill thi nhay 1 VONG
        BOUNCE_PERIOD giay ROI NGHI BOUNCE_REST_SECONDS giay moi lap lai -
        xem lich rieng _bounce_start/_next_bounce_at) tuy _active_option.
        Khong dung anh huong tray - tray pulse rieng, xem _tray_pulse_tick."""
        now = time.time()
        if now < self._burst_until:
            if self._active_option == "A":
                phase = (now % GLOW_PERIOD) / GLOW_PERIOD
                level = 0.5 * (1.0 - math.cos(2.0 * math.pi * phase))
                self.widget.set_glow_level(level)
                self.widget.set_dot_level(0.0)
                self.widget.set_bounce_offset(0.0)
            else:
                dot_phase = (now % DOT_PERIOD) / DOT_PERIOD
                dot_level = 0.5 * (1.0 - math.cos(2.0 * math.pi * dot_phase))
                self.widget.set_dot_level(dot_level)
                self.widget.set_glow_level(0.0)

                if now >= self._next_bounce_at:
                    # Bat dau 1 VONG nhay moi, hen gio vong ke tiep sau khi
                    # vong nay xong VA nghi du BOUNCE_REST_SECONDS.
                    self._bounce_start = now
                    self._next_bounce_at = now + BOUNCE_PERIOD + BOUNCE_REST_SECONDS
                bounce_elapsed = now - self._bounce_start
                if bounce_elapsed <= BOUNCE_PERIOD:
                    self.widget.set_bounce_offset(
                        bounce_offset_at(bounce_elapsed / BOUNCE_PERIOD))
                else:
                    # Dang trong khoang nghi giua 2 vong nhay - dung yen.
                    self.widget.set_bounce_offset(0.0)
        else:
            self.widget.set_glow_level(0.0)
            self.widget.set_dot_level(0.0)
            self.widget.set_bounce_offset(0.0)
            self._anim_timer.stop()


# Handle mutex giu o bien global de khong bi giai phong (xem ban tkinter).
_single_instance_mutex = None


def main():
    global _single_instance_mutex
    kernel32 = ctypes.windll.kernel32
    _single_instance_mutex = kernel32.CreateMutexW(
        None, False, "CheckinGuardQt_SingleInstanceMutex")
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        sys.exit(0)

    # Khi chay tu source qua pythonw.exe, Windows mac dinh gom taskbar theo
    # AppUserModelID cua pythonw.exe (icon Python), BO QUA icon rieng cua
    # cua so du da goi setWindowIcon(). Dat 1 AppUserModelID rieng cho app
    # TRUOC KHI tao QApplication/cua so nao de Windows dung dung icon cua
    # app thay vi icon cua pythonw.exe. Ban exe da co danh tinh rieng nen
    # goi nay khong anh huong, chi can thiet cho truong hop chay tu source.
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "MISA.CheckinGuard.Qt")
    except (AttributeError, OSError):
        pass  # Windows cu (< 7) khong co API nay - bo qua, khong anh huong chuc nang

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # dong popup khong lam thoat app
    # Icon cua app (taskbar/Alt-Tab/title bar cho moi cua so) = tray_default.svg,
    # dam bao dong bo voi icon tray va logo tren widget. Khi chay tu exe da
    # build (PyInstaller), icon file (.ico, embed qua icon= trong .spec) da
    # lo icon cua CHINH file exe (Explorer/Task Manager) - dong QIcon nay chi
    # lo phan Qt tu ve (window icon luc app dang chay).
    app.setWindowIcon(load_tray_icon(TRAY_ICON_DEFAULT_FILE))
    controller = Controller(app)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
