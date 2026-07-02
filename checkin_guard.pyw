"""
checkin_guard.pyw
------------------
Runs in the background, no console (.pyw). Shows a popup reminding the user
to check-in/check-out when:
  1. Just logged into Windows
  2. About to Shutdown / Restart (actually blocks until the button is pressed)
  3. The machine just woke up from Sleep / Hibernate (notification only, can't
     be blocked beforehand because Windows doesn't allow it - see README.md)

INSTALLATION: see the accompanying README.md.
TO EDIT: change CHECKIN_URL below to your actual URL.
"""

import ctypes
import queue
import threading
import tkinter as tk
import webbrowser

import win32api
import win32con
import win32gui

# ============== CONFIGURATION - EDIT HERE ==============
CHECKIN_URL = "https://daohainam.com/"
POPUP_TITLE = "Check-in / Check-out Reminder"
POPUP_MESSAGE = "Have you checked in / checked out?"
# =========================================================

event_queue: "queue.Queue[tuple[str, threading.Event | None]]" = queue.Queue()


# ---------- PART 1: HIDDEN WINDOW CATCHING WINDOWS EVENTS (runs on its own thread) ----------
class SystemEventListener:
    """Creates a hidden window to receive WM_QUERYENDSESSION (shutdown/restart)
    and WM_POWERBROADCAST (sleep/resume)."""

    def __init__(self):
        self.hinstance = win32api.GetModuleHandle(None)
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._wnd_proc
        wc.lpszClassName = "CheckinGuardHiddenWindowClass"
        wc.hInstance = self.hinstance
        self.class_atom = win32gui.RegisterClass(wc)
        self.hwnd = win32gui.CreateWindow(
            self.class_atom, "CheckinGuardHiddenWindow", 0, 0, 0, 0, 0, 0, 0,
            self.hinstance, None,
        )

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_QUERYENDSESSION:
            # The machine is about to shutdown/restart/logoff -> BLOCK until
            # the user presses the confirm button in the popup.
            ctypes.windll.user32.ShutdownBlockReasonCreate(
                hwnd, "Please confirm check-in / check-out before shutting down"
            )
            done_event = threading.Event()
            event_queue.put(("shutdown", done_event))
            done_event.wait()  # wait until the popup is closed (user pressed Confirm)
            ctypes.windll.user32.ShutdownBlockReasonDestroy(hwnd)
            return True

        if msg == win32con.WM_POWERBROADCAST:
            if wparam in (win32con.PBT_APMRESUMEAUTOMATIC, win32con.PBT_APMRESUMESUSPEND):
                event_queue.put(("resume", None))
            return True

        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def pump_forever(self):
        win32gui.PumpMessages()


def start_listener_thread():
    listener = SystemEventListener()
    t = threading.Thread(target=listener.pump_forever, daemon=True)
    t.start()
    return listener


# ---------- PART 2: TKINTER POPUP (runs on the main thread) ----------
class CheckinPopup:
    def __init__(self, root: tk.Tk, kind: str, done_event: threading.Event | None):
        self.root = root
        self.kind = kind
        self.done_event = done_event

        self.win = tk.Toplevel(root)
        self.win.title(POPUP_TITLE)
        self.win.attributes("-topmost", True)
        self.win.overrideredirect(True)  # remove title bar + close (X) button
        self.win.protocol("WM_DELETE_WINDOW", lambda: None)  # block Alt+F4/close

        # Size + center on screen
        w, h = 480, 220
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 2
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self.win.configure(bg="#1f2937")

        subtitle = {
            "startup": "(Just started up)",
            "shutdown": "(About to shut down / restart)",
            "resume": "(Just woke up)",
        }.get(kind, "")

        tk.Label(
            self.win, text=POPUP_MESSAGE, font=("Segoe UI", 16, "bold"),
            fg="white", bg="#1f2937", wraplength=440,
        ).pack(pady=(30, 6))
        tk.Label(
            self.win, text=subtitle, font=("Segoe UI", 10),
            fg="#9ca3af", bg="#1f2937",
        ).pack()

        btn_frame = tk.Frame(self.win, bg="#1f2937")
        btn_frame.pack(pady=30)

        tk.Button(
            btn_frame, text="Not yet, go to check-in/check-out website",
            font=("Segoe UI", 10), bg="#f59e0b", fg="black", relief="flat",
            padx=14, pady=8, command=self._go_checkin,
        ).grid(row=0, column=0, padx=10)

        tk.Button(
            btn_frame, text="Confirmed", font=("Segoe UI", 10, "bold"),
            bg="#22c55e", fg="black", relief="flat", padx=20, pady=8,
            command=self._confirm,
        ).grid(row=0, column=1, padx=10)

        # Keep focus, block interaction with other windows of this app
        self.win.grab_set()
        self.win.focus_force()
        # Block Alt+F4
        self.win.bind("<Alt-F4>", lambda e: "break")

    def _go_checkin(self):
        webbrowser.open(CHECKIN_URL)
        # Do NOT close the popup - as required, only the "Confirmed" button closes it

    def _confirm(self):
        self.win.grab_release()
        self.win.destroy()
        if self.done_event is not None:
            self.done_event.set()  # notify the listener thread to release the shutdown block


def poll_queue(root: tk.Tk):
    try:
        while True:
            kind, done_event = event_queue.get_nowait()
            CheckinPopup(root, kind, done_event)
    except queue.Empty:
        pass
    root.after(300, poll_queue, root)


def main():
    root = tk.Tk()
    root.withdraw()  # hide the root window, only use Toplevel popups

    start_listener_thread()

    # Show the popup as soon as the script runs (i.e. right after login,
    # since the Task Scheduler trigger "At log on" runs this file).
    event_queue.put(("startup", None))

    root.after(300, poll_queue, root)
    root.mainloop()


if __name__ == "__main__":
    main()
