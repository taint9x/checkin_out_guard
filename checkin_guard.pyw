"""
checkin_guard.pyw
------------------
Runs in the background, no console (.pyw). Shows a popup reminding the user
to check-in/check-out when:
  1. Just logged into Windows
  2. About to Shutdown / Restart (holds the shutdown until confirmed - note
     that Windows inserts its own fullscreen "app is preventing shutdown"
     screen here; the user must click Cancel on it to see this popup)
  3. The machine just woke up from Sleep / Hibernate (notification only, can't
     be blocked beforehand because Windows doesn't allow it - see README.md)

Controlled-shutdown mode: running `checkin_guard.exe --shutdown` (e.g. from
a desktop "Shutdown" shortcut) shows the popup FIRST with nothing else
happening; only "Confirmed" actually shuts the machine down. This is the
only way on Windows to get "popup before anything happens", because the
OS shutdown button always shows the system blocking screen first.

INSTALLATION: see the accompanying README.md.
TO EDIT: change CHECKIN_URL below to your actual URL.
"""

import ctypes
import datetime
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import traceback
import webbrowser
import winreg

import win32api
import win32con
import win32gui

# ============== CONFIGURATION - EDIT HERE ==============
CHECKIN_URL = "https://daohainam.com/"
POPUP_TITLE = "Check-in / Check-out Reminder"
POPUP_MESSAGE = "Have you checked in / checked out?"
# =========================================================

# Bump this on every change - it is written to the log at startup, so a log
# file always tells you exactly which build produced it.
BUILD_TAG = "2026-07-03.2"

LISTENER_WINDOW_CLASS = "CheckinGuardHiddenWindowClass"
# Private message: "the next WM_QUERYENDSESSION is pre-confirmed, let it
# through". Sent by a --shutdown instance to the resident instance right
# before it launches the real shutdown, so the resident guard doesn't
# re-block a shutdown the user just confirmed in the popup.
WM_ALLOW_ONE_SHUTDOWN = win32con.WM_APP + 1

# Log file next to the exe/script - this app has no console (.pyw/--noconsole),
# so this is the only way to see what happened (e.g. on the next shutdown).
_APP_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(_APP_DIR, "checkin_guard.log")


def log(msg: str):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat()} {msg}\n")
    except Exception:
        pass


def log_shutdown_policies():
    """Log registry values that control how Windows treats apps blocking
    shutdown. If AutoEndTasks is 1 (an IT policy / 'fast shutdown' tweak),
    Windows kills every app immediately at shutdown WITHOUT showing the
    'this app is preventing shutdown' screen - the popup can never appear
    no matter what this program does. Diagnosing that requires seeing these
    values, so record them at every startup."""
    for hive, hive_name, key_path in (
        (winreg.HKEY_CURRENT_USER, "HKCU", r"Control Panel\Desktop"),
        (winreg.HKEY_LOCAL_MACHINE, "HKLM", r"SYSTEM\CurrentControlSet\Control"),
    ):
        for name in ("AutoEndTasks", "WaitToKillAppTimeout", "HungAppTimeout", "WaitToKillServiceTimeout"):
            try:
                with winreg.OpenKey(hive, key_path) as k:
                    val, _ = winreg.QueryValueEx(k, name)
                log(f"policy {hive_name}\\{key_path}\\{name} = {val!r}")
            except FileNotFoundError:
                pass
            except Exception:
                pass


event_queue: "queue.Queue[tuple[str, threading.Event | None]]" = queue.Queue()


# ---------- PART 1: HIDDEN WINDOW CATCHING WINDOWS EVENTS (runs on its own thread) ----------
class SystemEventListener:
    """Creates a normally-hidden window to receive WM_QUERYENDSESSION
    (shutdown/restart) and WM_POWERBROADCAST (sleep/resume).

    Two hard Win32 requirements shape this class:
    - Windows message queues are per-thread, so the window and its message
      pump must live on the SAME dedicated thread.
    - Since Vista, Windows only shows the "this app is preventing shutdown"
      screen for processes that have a VISIBLE top-level window at the moment
      shutdown is blocked; a process with only hidden windows is force-killed
      after a few seconds with no UI at all. So while blocking, this window is
      made technically visible (WS_POPUP sized 0x0 - nothing is drawn on
      screen, but IsWindowVisible() becomes TRUE) and hidden again afterwards.
    """

    def __init__(self):
        self.hwnd = None
        self._ready = threading.Event()
        self._shutdown_event = None  # set while a shutdown confirmation is in flight
        self._allow_next = False  # True = next WM_QUERYENDSESSION passes through unblocked
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait()

    def _run(self):
        try:
            hinstance = win32api.GetModuleHandle(None)
            wc = win32gui.WNDCLASS()
            wc.lpfnWndProc = self._wnd_proc
            wc.lpszClassName = LISTENER_WINDOW_CLASS
            wc.hInstance = hinstance
            class_atom = win32gui.RegisterClass(wc)
            # WS_POPUP with 0x0 size: can be shown (WS_VISIBLE) without
            # actually drawing anything. The title is what the Windows
            # shutdown screen displays for this app, so make it meaningful.
            self.hwnd = win32gui.CreateWindow(
                class_atom, POPUP_TITLE, win32con.WS_POPUP, 0, 0, 0, 0, 0, 0,
                hinstance, None,
            )
            log(f"listener window created, hwnd={self.hwnd}")
        except Exception:
            log("FAILED to create listener window:\n" + traceback.format_exc())
            raise
        finally:
            self._ready.set()

        win32gui.PumpMessages()
        log("PumpMessages() returned (WM_QUIT received) - listener stopped")

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_ALLOW_ONE_SHUTDOWN:
            log("allow-one-shutdown message received (user confirmed via --shutdown popup)")
            self._allow_next = True
            return 1

        if msg == win32con.WM_QUERYENDSESSION:
            is_logoff = bool(lparam & 0x80000000)  # ENDSESSION_LOGOFF
            if self._allow_next:
                self._allow_next = False  # one-shot: only the confirmed shutdown passes
                log(f"WM_QUERYENDSESSION received (logoff={is_logoff}) - pre-confirmed, allowing")
                return True  # True = allow the session to end
            # The machine is about to shutdown/restart/logoff -> BLOCK until
            # the user presses the confirm button in the popup. This handler
            # MUST return immediately and keep pumping messages - if it blocks
            # here, Windows sees an unresponsive window (not one that's
            # deliberately delaying via ShutdownBlockReason) and proceeds with
            # shutdown anyway instead of showing the "waiting for apps" screen.
            # The actual wait-for-confirmation happens on a separate thread.
            if self._shutdown_event is None:
                log(f"WM_QUERYENDSESSION received (logoff={is_logoff})")
                # Must be visible BEFORE returning False, or Windows treats
                # this process as windowless and kills it without showing
                # the shutdown-blocked screen (see class docstring).
                win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
                log(f"listener window made visible, IsWindowVisible={win32gui.IsWindowVisible(hwnd)}")
                # This text is shown on Windows' fullscreen blocking screen -
                # it is the only message the user sees there, so it must tell
                # them what to do next.
                ok = ctypes.windll.user32.ShutdownBlockReasonCreate(
                    hwnd, "Check-in/check-out not confirmed. Click 'Cancel' to go back and confirm."
                )
                log(f"ShutdownBlockReasonCreate returned {ok}")
                self._shutdown_event = threading.Event()
                event_queue.put(("shutdown", self._shutdown_event))
                threading.Thread(
                    target=self._release_when_confirmed, args=(hwnd, self._shutdown_event), daemon=True
                ).start()
            else:
                log("WM_QUERYENDSESSION received again, still waiting for confirmation")
            return False  # False = block the shutdown

        if msg == win32con.WM_ENDSESSION:
            # wparam TRUE = the session really is ending (either our block was
            # ignored/overridden, or the user clicked "Shut down anyway").
            log(f"WM_ENDSESSION received, session_ending={bool(wparam)}")
            return 0

        if msg == win32con.WM_POWERBROADCAST:
            if wparam in (win32con.PBT_APMRESUMEAUTOMATIC, win32con.PBT_APMRESUMESUSPEND):
                log("WM_POWERBROADCAST resume received")
                event_queue.put(("resume", None))
            return True

        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _release_when_confirmed(self, hwnd, done_event):
        done_event.wait()  # wait until the popup is closed (user pressed Confirm)
        log("shutdown confirmed by user, releasing block")
        ctypes.windll.user32.ShutdownBlockReasonDestroy(hwnd)
        win32gui.ShowWindow(hwnd, win32con.SW_HIDE)  # back to fully hidden
        self._shutdown_event = None


def start_listener_thread():
    return SystemEventListener()


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
            "shutdown_request": "(The computer will shut down after you confirm)",
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
        if self.kind == "shutdown_request":
            initiate_confirmed_shutdown()


def initiate_confirmed_shutdown():
    """User confirmed in a --shutdown popup: tell the resident guard instance
    (if any) to let the next end-session through, then really shut down."""
    log("confirmed shutdown request - initiating real shutdown")
    try:
        resident_hwnd = win32gui.FindWindow(LISTENER_WINDOW_CLASS, None)
        if resident_hwnd:
            win32gui.SendMessage(resident_hwnd, WM_ALLOW_ONE_SHUTDOWN, 0, 0)
            log(f"notified resident instance (hwnd={resident_hwnd}) to allow the shutdown")
        else:
            log("no resident instance found, shutting down directly")
    except Exception:
        log("could not notify resident instance:\n" + traceback.format_exc())
    subprocess.Popen(["shutdown", "/s", "/t", "0"])
    sys.exit(0)


def poll_queue(root: tk.Tk):
    try:
        while True:
            kind, done_event = event_queue.get_nowait()
            CheckinPopup(root, kind, done_event)
    except queue.Empty:
        pass
    root.after(300, poll_queue, root)


def main():
    shutdown_mode = "--shutdown" in sys.argv[1:]
    log(f"=== main() started (build {BUILD_TAG}{', --shutdown mode' if shutdown_mode else ''}) ===")
    log_shutdown_policies()
    root = tk.Tk()
    root.withdraw()  # hide the root window, only use Toplevel popups

    if shutdown_mode:
        # Controlled-shutdown entry point (desktop "Shutdown" shortcut):
        # show the popup and do nothing else. "Confirmed" runs the real
        # shutdown. No listener here - the resident instance owns the
        # listener window, and FindWindow must locate IT, not us.
        event_queue.put(("shutdown_request", None))
    else:
        start_listener_thread()
        # Show the popup as soon as the script runs (i.e. right after login,
        # since the Task Scheduler trigger "At log on" runs this file).
        event_queue.put(("startup", None))

    root.after(300, poll_queue, root)
    root.mainloop()
    log("=== main() exited normally ===")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # No console in .pyw/--noconsole mode, so an uncaught exception would
        # otherwise fail completely silently - log it instead.
        log("FATAL uncaught exception:\n" + traceback.format_exc())
        raise
