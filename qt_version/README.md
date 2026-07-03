# Checkin Reminder — widget nhắc Check-in / Check-out trên taskbar

## Ứng dụng này làm gì

Tool chạy nền trên Windows giúp bạn **không quên check-in / check-out** giờ
làm. Toàn bộ hoạt động ở quyền user thường — **không cần Admin**.

**Widget nổi trên taskbar** (cạnh khay hệ thống):

- Hiển thị nhãn (mặc định `MISA`) + nút **Check-in**. Click bất kỳ chỗ nào
  trên widget → mở trang check-in trong trình duyệt mặc định.
- Giữ chuột **kéo** để di chuyển widget đến vị trí khác.
- Click **phải** → menu: `Check-in / Check-out` · `Reset position` ·
  `Hide to system tray` · `Exit`.
- Trong **khung giờ nhắc** (mặc định 08:00–10:00 và 17:00–19:00, giờ UTC+7),
  widget **pulse** đổi màu xanh → đỏ theo đợt để gây chú ý. Sau khi bạn bấm
  Check-in hoặc xác nhận trên popup, nút chuyển **✓ Done** xanh lá và widget
  im lặng cho tới khung giờ sau.

**Popup nhắc nhở** (modal, luôn nổi trên cùng, không có nút X, không đóng
được bằng Alt+F4) xuất hiện khi:

- Vừa đăng nhập Windows (nếu cài tự động chạy).
- Máy thức dậy sau Sleep / Hibernate.

Popup có đúng 2 nút: mở trang check-in (popup vẫn giữ) và "Already done"
(đóng popup).

**Ẩn xuống system tray:** chọn `Hide to system tray` → widget biến mất,
một icon xuất hiện ở khay hệ thống (cạnh đồng hồ). Icon này click trái mở
trang check-in, click phải có `Show widget` / `Exit`. Widget giữ nguyên
trạng thái ẩn cho tới khi bạn tự bấm `Show widget` — khi tới khung giờ nhắc,
**chỉ icon tray nhấp nháy xanh/đỏ** theo cùng nhịp pulse (không tự hiện
widget, không bật popup).

## Công nghệ sử dụng

| Thành phần | Dùng để |
|---|---|
| Python 3.10+ / PySide6 (Qt 6) | Toàn bộ UI: widget vẽ bằng QPainter, popup, tray icon, timer — chạy 1 thread duy nhất |
| Win32 API qua `ctypes` (built-in) | `SetWindowPos` giữ widget nổi trên taskbar; mutex chống chạy trùng 2 instance |
| `QAbstractNativeEventFilter` | Bắt `WM_POWERBROADCAST` để biết máy vừa thức dậy sau Sleep/Hibernate |
| Registry `HKCU\Control Panel\NotifyIconSettings` | Ghim icon tray ra ngoài taskbar (Windows 11), tự chạy khi icon xuất hiện lần đầu |

Chỉ cần cài đúng 1 thư viện: `PySide6`.

## Quyền hạn & chính sách (policy)

- **Không cần quyền Admin** ở mọi bước: chạy, cài thư viện (`pip --user`),
  đăng ký tự khởi động (Task Scheduler scope user / Startup folder / HKCU Run).
- **Không thu thập, không gửi dữ liệu**: tool không gọi mạng — việc duy nhất
  liên quan internet là mở trình duyệt tới `CHECKIN_URL` khi bạn bấm nút.
- Những gì tool đụng vào hệ thống (tất cả trong phạm vi user hiện tại):
  - Ghi registry `HKCU\Control Panel\NotifyIconSettings\...\IsPromoted = 1`
    (ghim icon tray — Windows 11).
  - Tạo 1 mutex tên `CheckinGuardQt_SingleInstanceMutex` (chống chạy trùng).
  - Nếu cài tự khởi động: 1 scheduled task scope user, HOẶC 1 shortcut trong
    Startup folder, HOẶC 1 giá trị trong `HKCU\...\Run`.
- Môi trường công ty: GPO có thể chặn Task Scheduler hoặc PowerShell script
  (đã có phương án thay thế bên dưới); AppLocker/EDR có thể chặn exe lạ —
  trường hợp đó liên hệ IT xin whitelist, không nên tự lách.

## Khi nào dùng

- Công ty yêu cầu check-in/check-out trên web nhưng hay quên.
- Muốn được nhắc đúng khung giờ (sáng vào + chiều về), nhắc lại khi mở máy
  và sau khi máy ngủ dậy, mà không bị làm phiền cả ngày.

---

## Cài đặt

### Cách 1 — Chạy từ source (cần Python)

1. **Cài Python** (bỏ qua nếu đã có): tải bản 3.10+ tại
   <https://www.python.org/downloads/>. Khi cài **nhớ tick "Add python.exe
   to PATH"** ở màn hình đầu. Không cần "Install for all users".
2. **Cài thư viện** — mở PowerShell (Start → gõ `powershell` → Enter):

   ```powershell
   pip install --user PySide6
   ```

3. **Sửa cấu hình**: mở `checkin_guard_qt.pyw` bằng Notepad, sửa dòng
   `CHECKIN_URL = "..."` thành địa chỉ trang check-in của công ty. Các tuỳ
   chọn khác xem bảng [Cấu hình](#cấu-hình) bên dưới. Lưu file.
4. **Chạy thử**:

   ```powershell
   pythonw .\checkin_guard_qt.pyw
   ```

   Widget xuất hiện trên taskbar + popup nhắc hiện ra. Thoát: click phải
   widget → `Exit`.

### Cách 2 — Build & chạy file .exe (máy đích không cần Python)

Build 1 lần trên máy có Python:

```powershell
pip install --user pyinstaller
pyinstaller checkin_reminder.spec
```

File kết quả: `dist\checkin_reminder.exe` — copy sang máy nào cũng chạy
được, không cần cài gì thêm. Thông tin hiển thị trong Properties của exe
(tên, version, mô tả) lấy từ `version_info.txt` — sửa file đó rồi build lại
nếu muốn đổi.

> Lưu ý: exe tự build không có chữ ký số nên SmartScreen có thể cảnh báo
> lần chạy đầu (More info → Run anyway). Antivirus/EDR công ty nghiêm ngặt
> có thể chặn — khi đó dùng Cách 1 hoặc nhờ IT whitelist.

### Cách 3 — Tự động chạy khi đăng nhập Windows

Mở PowerShell **tại thư mục tool** (gõ `powershell` vào thanh địa chỉ của
File Explorer) rồi chạy:

```powershell
.\setup_task.ps1
```

Script tự phát hiện: nếu đã build `dist\checkin_reminder.exe` thì đăng ký
chạy exe, chưa build thì chạy qua `pythonw`. Task tên `CheckinGuardQt`,
scope user, **không cần Admin**. Test ngay không cần đăng nhập lại:

```powershell
Start-ScheduledTask -TaskName CheckinGuardQt
```

Gỡ bỏ:

```powershell
Unregister-ScheduledTask -TaskName CheckinGuardQt -Confirm:$false
```

**Nếu PowerShell báo "running scripts is disabled":** chạy lệnh sau 1 lần
(chỉ áp dụng cho tài khoản của bạn, không cần Admin) rồi thử lại:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

#### Nếu `setup_task.ps1` vẫn fail (GPO chặn Task Scheduler) — 2 cách thay thế

**Cách B — Startup folder** (cơ chế lõi của Windows, gần như không bị chặn):

```powershell
.\setup_startup.ps1            # tao shortcut tu dong
.\setup_startup.ps1 -Remove    # go bo
```

Hoặc làm tay không cần PowerShell:

1. Bấm `Win + R`, gõ `shell:startup`, Enter.
2. Chuột phải trong thư mục vừa mở → New → Shortcut.
3. Ô location: dán đường dẫn tới `dist\checkin_reminder.exe` (bản exe),
   hoặc `pythonw.exe "D:\...\checkin_guard_qt.pyw"` (bản source).
4. Đặt tên `Checkin Reminder` → Finish. Xong — lần đăng nhập sau tự chạy.

**Cách C — Registry Run key** (1 lệnh duy nhất, không cần Admin, không đụng
Task Scheduler lẫn Startup folder):

```powershell
# ban exe:
reg add HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v CheckinReminder /d "D:\duong\dan\dist\checkin_reminder.exe" /f

# go bo:
reg delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v CheckinReminder /f
```

Cả 3 cách đều ở scope user — chọn cách nào chạy được trong môi trường của
bạn. Tool có chống chạy trùng, lỡ cài 2 cách cùng lúc cũng chỉ 1 bản chạy.

---

## Cấu hình

Tất cả ở đầu file `checkin_guard_qt.pyw` (bản exe: sửa xong phải build lại):

| Biến | Ý nghĩa |
|---|---|
| `CHECKIN_URL` | Địa chỉ trang check-in — **bắt buộc sửa** |
| `POPUP_TITLE` / `POPUP_MESSAGE` / `BUTTON_*_TEXT` | Chữ trên popup |
| `WIDGET_LABEL` / `WIDGET_BUTTON_TEXT` / `WIDGET_BUTTON_DONE_TEXT` | Chữ trên widget |
| `WIDGET_WIDTH` / `WIDGET_HEIGHT` / `WIDGET_OFFSET_RIGHT` | Kích thước, khoảng cách từ mép phải màn hình |
| `WIDGET_ALERT_MODE` | Khi nào gây chú ý: `"schedule"` (theo khung giờ — mặc định), `"always"`, `"popup"`, `"off"` |
| `ALERT_SCHEDULE` | Các khung giờ nhắc `("HH:MM", "HH:MM")` |
| `TZ_UTC_OFFSET` | Múi giờ của khung giờ (mặc định `7` = UTC+7, không phụ thuộc múi giờ Windows) |
| `PULSE_PERIOD` / `PULSE_BURST_CYCLES` / `PULSE_REST_SECONDS` | Nhịp pulse: mỗi đợt N nhịp × chu kỳ, nghỉ giữa các đợt |
| `COLOR_NORMAL` / `COLOR_ALERT` / `COLOR_DONE` | Màu bình thường / cảnh báo / màu "✓ Done" |
| `RESUME_DEBOUNCE_SECONDS` | Gộp các sự kiện thức dậy liên tiếp (mặc định 15s) |

## Sử dụng hàng ngày

| Thao tác | Kết quả |
|---|---|
| Click widget / nút Check-in | Mở trang check-in; trong khung giờ → tính là đã làm, hiện ✓ Done, ngừng pulse |
| Bấm "Already done" trên popup | Đóng popup, tính là đã làm |
| Click phải widget → Hide to system tray | Widget ẩn, icon hiện ở khay hệ thống (icon nháy nếu đang trong khung giờ) |
| Click trái icon tray | Mở trang check-in |
| Click phải icon tray → Show widget | Widget hiện lại ngay |
| Đầu khung giờ kế tiếp (đang ẩn) | Widget vẫn ẩn — chỉ icon tray nhấp nháy nhắc |
| Click phải → Exit | Thoát hẳn tool |

## Giới hạn cần biết & Troubleshooting

- **Start menu / Task View che widget khi đang mở**: menu Start thuộc lớp
  cửa sổ hệ thống cao hơn mọi app thường — Windows không cho app nào nổi
  lên trên nó (thiết kế bảo mật của HĐH). Đóng Start là widget tự nổi lại
  trong ~0.15 giây. Tương tự với app fullscreen (game, video toàn màn hình).
- **Win + L (khoá màn hình) không kích hoạt popup** — khoá màn hình không
  phải sự kiện sleep. Chỉ login / Sleep / Hibernate / khung giờ mới nhắc.
- **Không chặn được Shutdown/Restart** — tool chỉ nhắc, không ngăn tắt máy.
- **Icon tray bị giấu sau nút `^` (Windows 10 hoặc lần đầu)**: tool tự ghim
  icon ra ngoài trên Windows 11 (22H2+); nếu vẫn bị giấu, kéo-thả icon từ
  khay ẩn ra taskbar, hoặc Settings → Personalization → Taskbar → Other
  system tray icons → bật cho `checkin_reminder` / `Python`.
- **Chạy 2 lần không thấy gì**: đã có 1 instance đang chạy (mutex chống
  trùng) — tìm icon/widget đang có, hoặc Task Manager → tắt process cũ.
- **Sửa config không thấy đổi**: bản exe phải build lại; bản source phải
  thoát tool (Exit) rồi chạy lại.
