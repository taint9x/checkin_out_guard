# -*- coding: utf-8 -*-
"""
Checkin Guard - Tool nhac nho check-in / check-out cong ty.

Hoat dong:
  - Khi script khoi dong (chay luc login qua Task Scheduler / Startup folder)
    -> hien popup nhac nho ngay.
  - Khi may thuc day sau Sleep / Hibernate (bat qua WM_POWERBROADCAST)
    -> hien popup nhac nho.
  - Popup modal, luon noi tren cung, khong co nut X, khong dong duoc bang
    Alt+F4 hay click ra ngoai. Chi dong khi bam "Xac nhan roi".
  - Tray icon ton tai suot vong doi process: click trai mo CHECKIN_URL,
    click phai co menu "Check-in / Check-out" va "Thoat".

Kien truc thread:
  - Main thread : tkinter mainloop, poll queue moi 300ms, quan ly popup.
  - Thread 2    : hidden win32 window + message pump, bat WM_POWERBROADCAST,
                  day event "resume" vao queue.
  - Thread 3    : pystray icon (icon ve bang Pillow, khong can file anh).

Khong yeu cau quyen Admin o bat ky buoc nao.
"""

import os
import queue
import sys
import threading
import time
import webbrowser
import winreg
import tkinter as tk
from datetime import datetime, timedelta, timezone

import win32api
import win32con
import win32event
import win32gui
import winerror

import pystray
from PIL import Image, ImageDraw, ImageFont

# =========================================================================
# CAU HINH - user tu sua cac gia tri duoi day
# =========================================================================
CHECKIN_URL = "https://example.com/checkin"   # user tu thay URL that
POPUP_TITLE = "Nhắc nhở Check-in / Check-out"
POPUP_MESSAGE = "Bạn đã check-in / check-out chưa?"
TRAY_TOOLTIP = "Check-in / Check-out - Click để mở trang"

BUTTON_OPEN_TEXT = "Chưa, tới website checkin checkout"
BUTTON_CONFIRM_TEXT = "Xác nhận rồi"

# Chu hien tren icon tray. Windows KHONG cho hien text label that canh icon
# (chi co tooltip khi hover) nen chu duoc VE truc tiep len icon.
# Icon tray rat nho (16x16 tren man hinh) -> chu cang ngan cang ro.
# Label tu 4 ky tu tro len se TU DONG xep thanh 2 hang de chu to hon
# (vi du "MISA" -> "MI" tren, "SA" duoi). Cung co the tu ep xuong dong
# bang "\n", vi du TRAY_LABEL = "MI\nSA".
TRAY_LABEL = "MISA"

# Nhap nhay icon de gay chu y. Cac gia tri:
#   "off"      - khong nhap nhay
#   "popup"    - chi nhap nhay khi popup nhac nho dang mo
#   "always"   - nhap nhay lien tuc suot phien lam viec
#   "schedule" - nhap nhay theo cac khung gio trong TRAY_BLINK_SCHEDULE
TRAY_BLINK = "schedule"
TRAY_BLINK_INTERVAL = 0.6          # chu ky nhay (giay)
TRAY_COLOR_NORMAL = (0, 120, 212)  # mau nen icon binh thuong (xanh)
TRAY_COLOR_ALERT = (232, 17, 35)   # mau nen khi nhay (do)

# Khung gio nhap nhay khi TRAY_BLINK = "schedule". Dinh dang ("HH:MM", "HH:MM"),
# tinh theo mui gio TRAY_TZ_UTC_OFFSET (khong phu thuoc mui gio cua Windows).
TRAY_BLINK_SCHEDULE = [
    ("08:00", "10:00"),   # nhac check-in buoi sang
    ("17:00", "19:00"),   # nhac check-out buoi chieu
]
TRAY_TZ_UTC_OFFSET = 7   # UTC+7 (gio Viet Nam)

# Sau khi resume, cac message PBT_APMRESUMEAUTOMATIC va PBT_APMRESUMESUSPEND
# co the ban ra lien tiep cho cung 1 lan thuc day -> gop lai trong khoang nay.
RESUME_DEBOUNCE_SECONDS = 15
# =========================================================================


class CheckinGuardApp:
    """Giu toan bo state cua app: root tkinter, popup, tray icon, queue."""

    def __init__(self):
        # Queue giao tiep giua cac thread. Cac gia tri: "resume", "quit".
        self.event_queue = queue.Queue()

        self.popup = None                # Toplevel dang hien (None neu khong co)
        self.popup_visible = False       # flag cho blink thread doc (thread-safe)
        self.last_popup_time = 0.0       # thoi diem popup gan nhat (debounce)
        self.balloon_shown = False       # chi hien balloon huong dan 1 lan
        self.tray_icon = None
        self.hidden_hwnd = None          # handle cua hidden window (de dong khi thoat)

        # Ve san 2 phien ban icon (binh thuong + canh bao) dung cho hieu ung nhay.
        self._icon_normal = self._make_icon_image(TRAY_LABEL, TRAY_COLOR_NORMAL)
        self._icon_alert = self._make_icon_image(TRAY_LABEL, TRAY_COLOR_ALERT)

        # Root tkinter an - chi dung lam host cho popup Toplevel.
        self.root = tk.Tk()
        self.root.withdraw()

    # ------------------------------------------------------------------
    # Hidden win32 window: bat su kien resume sau Sleep/Hibernate
    # ------------------------------------------------------------------
    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_POWERBROADCAST:
            if wparam in (win32con.PBT_APMRESUMEAUTOMATIC,
                          win32con.PBT_APMRESUMESUSPEND):
                self.event_queue.put("resume")
            return True
        if msg == win32con.WM_DESTROY:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _power_listener_thread(self):
        """Chay o thread rieng: tao hidden window roi pump messages.

        Window phai duoc tao trong chinh thread se pump message cho no.
        """
        wc = win32gui.WNDCLASS()
        wc.hInstance = win32api.GetModuleHandle(None)
        wc.lpszClassName = "CheckinGuardHiddenWindow"
        wc.lpfnWndProc = self._wnd_proc
        class_atom = win32gui.RegisterClass(wc)

        self.hidden_hwnd = win32gui.CreateWindow(
            class_atom, "CheckinGuard", 0, 0, 0, 0, 0,
            0, 0, wc.hInstance, None)

        # Block cho toi khi nhan WM_QUIT (do WM_DESTROY post ra khi thoat).
        win32gui.PumpMessages()

    # ------------------------------------------------------------------
    # Tray icon (pystray + Pillow)
    # ------------------------------------------------------------------
    @staticmethod
    def _make_icon_image(label, bg_color):
        """Ve icon tray bang code: nen tron mau + chu (TRAY_LABEL) mau trang.

        Windows khong ho tro text label trong tray, nen chu duoc ve thanh
        chinh cai icon. Icon chi hien 16x16 -> label cang ngan cang ro.

        Label >= 4 ky tu tu dong tach lam 2 hang (nua dau tren, nua sau duoi)
        de moi hang it ky tu hon -> chu to hon. Co the tu ep xuong dong
        bang "\\n" trong label.
        """
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, size - 1, size - 1), radius=12,
                            fill=bg_color + (255,))

        # Tach label thanh cac hang.
        if "\n" in label:
            lines = [s for s in label.split("\n") if s]
        elif len(label) >= 4:
            half = (len(label) + 1) // 2
            lines = [label[:half], label[half:]]
        else:
            lines = [label]

        # Chon co chu theo so hang va hang dai nhat de lap day icon.
        longest = max(len(s) for s in lines)
        if len(lines) == 1:
            font_size = {1: 48, 2: 40, 3: 28}.get(longest, 22)
        else:
            font_size = {1: 38, 2: 38, 3: 24}.get(longest, 18)

        font = None
        for font_file in ("segoeuib.ttf", "arialbd.ttf", "arial.ttf"):
            try:
                font = ImageFont.truetype(font_file, font_size)
                break
            except OSError:
                continue
        if font is None:
            font = ImageFont.load_default()

        # Do kich thuoc that cua tung hang roi can giua theo ca 2 chieu.
        boxes = [d.textbbox((0, 0), s, font=font) for s in lines]
        heights = [b[3] - b[1] for b in boxes]
        line_gap = 3 if len(lines) > 1 else 0
        total_h = sum(heights) + line_gap * (len(lines) - 1)
        y = (size - total_h) / 2
        for text, box, h in zip(lines, boxes, heights):
            w = box[2] - box[0]
            d.text(((size - w) / 2 - box[0], y - box[1]),
                   text, font=font, fill=(255, 255, 255, 255))
            y += h + line_gap
        return img

    @staticmethod
    def _in_blink_schedule():
        """Kiem tra gio hien tai (theo TRAY_TZ_UTC_OFFSET, khong phu thuoc
        mui gio Windows) co nam trong khung gio nao cua TRAY_BLINK_SCHEDULE.
        """
        tz = timezone(timedelta(hours=TRAY_TZ_UTC_OFFSET))
        now = datetime.now(tz)
        now_minutes = now.hour * 60 + now.minute
        for start, end in TRAY_BLINK_SCHEDULE:
            start_h, start_m = map(int, start.split(":"))
            end_h, end_m = map(int, end.split(":"))
            if start_h * 60 + start_m <= now_minutes < end_h * 60 + end_m:
                return True
        return False

    def _blink_thread(self):
        """Chay o thread rieng: dao icon giua 2 mau de tao hieu ung nhay.

        Doc self.popup_visible (bool, ghi tu main thread) - doc bool
        cross-thread la an toan, khong duoc dong vao tkinter tu day.
        """
        is_alert_frame = False
        while True:
            time.sleep(TRAY_BLINK_INTERVAL)
            if self.tray_icon is None:
                continue
            should_blink = (
                TRAY_BLINK == "always"
                or (TRAY_BLINK == "popup" and self.popup_visible)
                or (TRAY_BLINK == "schedule" and self._in_blink_schedule()))
            if should_blink:
                is_alert_frame = not is_alert_frame
                self.tray_icon.icon = (self._icon_alert if is_alert_frame
                                       else self._icon_normal)
            elif is_alert_frame:
                # Het nhay -> tra icon ve trang thai binh thuong.
                is_alert_frame = False
                self.tray_icon.icon = self._icon_normal

    def _on_tray_open(self, icon=None, item=None):
        webbrowser.open(CHECKIN_URL)

    def _on_tray_quit(self, icon=None, item=None):
        # Dung tray icon, dong hidden window (ket thuc pump thread),
        # roi bao main thread thoat qua queue.
        if self.tray_icon is not None:
            self.tray_icon.stop()
        if self.hidden_hwnd:
            win32gui.PostMessage(self.hidden_hwnd, win32con.WM_CLOSE, 0, 0)
        self.event_queue.put("quit")

    def _promote_tray_icon(self):
        """Yeu cau Windows 11 hien icon truc tiep tren taskbar (canh dong ho)
        thay vi giau trong khay an sau nut mui ten.

        Windows 11 (22H2+) luu cai dat nay o registry user-scope:
          HKCU\\Control Panel\\NotifyIconSettings\\<id>\\IsPromoted = 1
        Khong can Admin. Tren Windows 10 khong co key nay -> bo qua.

        Luu y: ExecutablePath trong registry co the dung dang GUID known-folder
        (vi du "{6D809377-...}\\Python313\\pythonw.exe") nen phai so sanh theo
        ten file, khong so sanh duong dan day du.
        """
        my_exe = os.path.basename(sys.executable).lower()  # "pythonw.exe"
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

    def _tray_thread(self):
        menu = pystray.Menu(
            # default=True -> click trai vao icon cung chay action nay.
            pystray.MenuItem("Check-in / Check-out", self._on_tray_open,
                             default=True),
            pystray.MenuItem("Thoát", self._on_tray_quit),
        )
        self.tray_icon = pystray.Icon(
            "checkin_guard", self._icon_normal, TRAY_TOOLTIP, menu)
        self.tray_icon.run()

    # ------------------------------------------------------------------
    # Popup modal
    # ------------------------------------------------------------------
    def show_popup(self):
        """Tao popup modal. Neu popup dang mo thi chi keo len tren cung."""
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.lift()
            self.popup.focus_force()
            return

        self.last_popup_time = time.time()
        self.popup_visible = True  # bat hieu ung nhay icon (neu TRAY_BLINK="popup")

        popup = tk.Toplevel(self.root)
        self.popup = popup
        popup.title(POPUP_TITLE)

        # overrideredirect: bo toan bo title bar -> khong co nut X,
        # khong keo tha, khong resize.
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)

        # Chan moi duong dong ngoai nut "Xac nhan roi":
        # - WM_DELETE_WINDOW (Alt+F4 / lenh close tu he thong) -> bo qua.
        # - Phim Alt+F4 bind truc tiep -> "break".
        popup.protocol("WM_DELETE_WINDOW", lambda: None)
        popup.bind("<Alt-F4>", lambda e: "break")
        popup.bind("<Escape>", lambda e: "break")

        # Layout
        frame = tk.Frame(popup, bg="#ffffff", bd=2, relief="solid",
                         padx=30, pady=25)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=POPUP_TITLE, bg="#ffffff",
                 font=("Segoe UI", 14, "bold"), fg="#c0392b").pack(pady=(0, 10))
        tk.Label(frame, text=POPUP_MESSAGE, bg="#ffffff",
                 font=("Segoe UI", 12)).pack(pady=(0, 20))

        btn_frame = tk.Frame(frame, bg="#ffffff")
        btn_frame.pack()

        # Nut mo website: KHONG dong popup sau khi bam.
        tk.Button(
            btn_frame, text=BUTTON_OPEN_TEXT,
            font=("Segoe UI", 11), bg="#0078d4", fg="white",
            activebackground="#005a9e", activeforeground="white",
            padx=14, pady=8, cursor="hand2",
            command=lambda: webbrowser.open(CHECKIN_URL),
        ).pack(side="left", padx=8)

        # Nut xac nhan: dong popup ngay.
        tk.Button(
            btn_frame, text=BUTTON_CONFIRM_TEXT,
            font=("Segoe UI", 11, "bold"), bg="#107c10", fg="white",
            activebackground="#0b5c0b", activeforeground="white",
            padx=14, pady=8, cursor="hand2",
            command=self._confirm_popup,
        ).pack(side="left", padx=8)

        # Can giua man hinh.
        popup.update_idletasks()
        w, h = popup.winfo_reqwidth(), popup.winfo_reqheight()
        x = (popup.winfo_screenwidth() - w) // 2
        y = (popup.winfo_screenheight() - h) // 2
        popup.geometry(f"{w}x{h}+{x}+{y}")

        # Modal: grab toan bo input cua app, ep focus ve popup.
        popup.grab_set()
        popup.focus_force()

        # Dinh ky keo popup len tren cung phong khi app khac chiem topmost.
        self._keep_popup_on_top()

    def _keep_popup_on_top(self):
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.attributes("-topmost", True)
            self.popup.lift()
            self.popup.after(1000, self._keep_popup_on_top)

    def _confirm_popup(self):
        """Nut 'Xac nhan roi': dong popup, hien balloon huong dan 1 lan."""
        if self.popup is not None:
            try:
                self.popup.grab_release()
                self.popup.destroy()
            except tk.TclError:
                pass
            self.popup = None
        self.popup_visible = False  # tat hieu ung nhay icon

        if not self.balloon_shown and self.tray_icon is not None:
            self.balloon_shown = True
            try:
                self.tray_icon.notify(
                    "Ban co the check-in / check-out bat ky luc nao bang cach "
                    "click vao icon nay o khay he thong.",
                    "Checkin Guard")
            except Exception:
                # notify co the fail tren mot so he thong - khong nghiem trong.
                pass

    # ------------------------------------------------------------------
    # Main loop: poll queue tu cac thread khac
    # ------------------------------------------------------------------
    def _poll_queue(self):
        try:
            while True:
                event = self.event_queue.get_nowait()
                if event == "quit":
                    self.root.destroy()
                    return
                if event == "resume":
                    # Debounce: 1 lan resume co the ban 2 message lien tiep.
                    if time.time() - self.last_popup_time >= RESUME_DEBOUNCE_SECONDS:
                        self.show_popup()
                    elif self.popup is not None and self.popup.winfo_exists():
                        self.popup.lift()
        except queue.Empty:
            pass
        self.root.after(300, self._poll_queue)

    def run(self):
        # Thread bat su kien resume (daemon: tu chet khi main thread thoat).
        threading.Thread(target=self._power_listener_thread,
                         daemon=True).start()
        # Thread tray icon - tao 1 lan duy nhat, ton tai suot vong doi process.
        threading.Thread(target=self._tray_thread, daemon=True).start()
        # Thread hieu ung nhay icon (chi chay khi co bat trong config).
        if TRAY_BLINK in ("popup", "always", "schedule"):
            threading.Thread(target=self._blink_thread, daemon=True).start()

        # Hien popup ngay khi khoi dong (truong hop vua login vao Windows).
        self.root.after(500, self.show_popup)
        self.root.after(300, self._poll_queue)
        # Doi vai giay cho Windows tao xong entry registry cua tray icon
        # roi moi "ghim" icon ra ngoai taskbar.
        self.root.after(5000, self._promote_tray_icon)
        self.root.mainloop()


# Handle cua mutex phai duoc giu o bien global - neu de local trong main(),
# Python se giai phong (dong handle) ngay va co che chong chay trung mat tac dung.
_single_instance_mutex = None


def main():
    # Chan chay trung 2 instance (vi du Task Scheduler + Startup folder
    # cung kich hoat) -> tranh duplicate tray icon va popup chong nhau.
    global _single_instance_mutex
    _single_instance_mutex = win32event.CreateMutex(
        None, False, "CheckinGuard_SingleInstanceMutex")
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        sys.exit(0)

    CheckinGuardApp().run()


if __name__ == "__main__":
    main()
