# Checkin Guard — Tool nhắc Check-in / Check-out

Tool chạy nền trên Windows, **không cần quyền Admin**, giúp bạn không quên
check-in / check-out:

- **Hiện popup nhắc nhở** (luôn nổi trên cùng, không có nút X) khi:
  - Vừa đăng nhập vào Windows.
  - Máy vừa thức dậy sau Sleep / Hibernate.
- Popup chỉ có 2 nút:
  - **"Chưa, tới website checkin checkout"** → mở trình duyệt tới trang
    check-in (popup vẫn giữ nguyên).
  - **"Xác nhận rồi"** → đóng popup.
- **Icon ở khay hệ thống** (System Tray, cạnh đồng hồ góc phải taskbar) tồn
  tại suốt phiên làm việc:
  - Click **trái** → mở trang check-in.
  - Click **phải** → menu: "Check-in / Check-out" và "Thoát".

---

## Cài đặt từng bước

### Bước 1 — Cài Python

1. Tải Python tại: <https://www.python.org/downloads/> (bản 3.10 trở lên).
2. Chạy file cài đặt. **QUAN TRỌNG: tick vào ô "Add python.exe to PATH"**
   ở màn hình đầu tiên trước khi bấm Install.
3. Không cần chọn "Install for all users" — cài cho riêng bạn là đủ
   (không cần Admin).

### Bước 2 — Cài thư viện

Mở **PowerShell** (bấm Start, gõ `powershell`, Enter) rồi chạy:

```powershell
pip install --user pywin32 pystray pillow
```

### Bước 3 — Sửa địa chỉ trang check-in

1. Mở file `checkin_guard.pyw` bằng Notepad (chuột phải → Open with → Notepad).
2. Tìm dòng gần đầu file:

   ```python
   CHECKIN_URL = "https://example.com/checkin"   # user tu thay URL that
   ```

3. Thay `https://example.com/checkin` bằng địa chỉ trang check-in thật của
   công ty bạn. Lưu file (Ctrl+S).

Các tuỳ chọn khác ở cùng khu vực đầu file (sửa xong nhớ khởi động lại tool):

| Biến | Ý nghĩa |
|---|---|
| `TRAY_LABEL` | Chữ hiện trên icon tray (Windows không cho hiện chữ dài cạnh icon, chỉ có tooltip khi rê chuột). Label từ 4 ký tự trở lên tự động xếp 2 hàng cho chữ to hơn (`"MISA"` → `MI` trên, `SA` dưới); có thể tự ép xuống dòng bằng `"\n"` |
| `TRAY_BLINK` | Hiệu ứng nhấp nháy icon: `"off"` (tắt), `"popup"` (chỉ nháy khi popup nhắc nhở đang mở), `"always"` (nháy liên tục), `"schedule"` (nháy theo khung giờ) |
| `TRAY_BLINK_SCHEDULE` | Các khung giờ nháy khi dùng `"schedule"`, dạng `("HH:MM", "HH:MM")` — mặc định 08:00–10:00 và 17:00–19:00 |
| `TRAY_TZ_UTC_OFFSET` | Múi giờ tính khung giờ, mặc định `7` (UTC+7, giờ Việt Nam) — không phụ thuộc múi giờ cài trong Windows |
| `TRAY_BLINK_INTERVAL` | Chu kỳ nháy, tính bằng giây (mặc định `0.6`) |
| `TRAY_COLOR_NORMAL` / `TRAY_COLOR_ALERT` | Màu nền icon bình thường / khi nháy (RGB) |

### Bước 4 — Đăng ký chạy tự động khi login

Mở PowerShell **tại thư mục chứa tool** (mở thư mục trong File Explorer,
gõ `powershell` vào thanh địa chỉ, Enter) rồi chạy:

```powershell
.\setup_task.ps1
```

Nếu gặp lỗi kiểu *"running scripts is disabled on this system"*, chạy lệnh
sau một lần rồi thử lại (lệnh này chỉ áp dụng cho tài khoản của bạn, không
cần Admin):

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### Bước 5 — Test ngay, không cần đăng nhập lại

```powershell
Start-ScheduledTask -TaskName CheckinGuard
```

Popup nhắc nhở sẽ hiện ra ngay, và icon xuất hiện ở khay hệ thống
(có thể phải bấm mũi tên `^` cạnh đồng hồ để thấy icon).

Cách test khác — chạy trực tiếp không qua Task Scheduler:

```powershell
pythonw .\checkin_guard.pyw
```

Test tình huống "thức dậy sau Sleep": cho máy Sleep (Start → Power → Sleep),
đợi vài giây rồi mở lại — popup sẽ hiện.

**Dừng tool:** click phải vào icon ở khay hệ thống → **Thoát**.

### Icon bị ẩn sau nút mũi tên `^`?

Tool tự động "ghim" icon ra ngoài taskbar (cạnh icon wifi/pin) trên
Windows 11 — có hiệu lực sau vài giây kể từ khi chạy. Nếu icon vẫn nằm
trong khay ẩn, làm thủ công một trong hai cách:

- **Kéo thả:** bấm nút `^` cạnh đồng hồ, kéo icon Checkin Guard thả ra
  vùng taskbar cạnh icon wifi.
- **Qua Settings:** chuột phải vào taskbar → **Taskbar settings** →
  **Other system tray icons** → bật công tắc ở dòng **Python** (pythonw.exe).

**Gỡ bỏ hoàn toàn:**

```powershell
Unregister-ScheduledTask -TaskName CheckinGuard -Confirm:$false
```

---

## Phương án dự phòng: Startup folder

Nếu công ty khoá Task Scheduler bằng Group Policy, dùng cách này (là cơ chế
lõi của Windows, gần như không bị chặn):

1. Bấm `Win + R`, gõ `shell:startup`, Enter → mở thư mục Startup.
2. Trong thư mục đó, chuột phải → **New → Shortcut**.
3. Ở ô location, dán (sửa lại đường dẫn cho đúng máy bạn):

   ```
   pythonw.exe "D:\PCT\checkin_out_guard\new_version\checkin_guard.pyw"
   ```

   > Nếu Windows báo không tìm thấy `pythonw.exe`, mở PowerShell gõ
   > `(Get-Command pythonw).Source` để lấy đường dẫn đầy đủ, rồi dùng
   > đường dẫn đó thay cho chữ `pythonw.exe`.

4. Đặt tên shortcut là `Checkin Guard` → Finish.

Từ lần đăng nhập sau, tool sẽ tự chạy. (Tool có chống chạy trùng — nếu lỡ
bật cả 2 phương án cùng lúc thì cũng chỉ có 1 bản chạy.)

---

## Giới hạn cần biết

1. **Không chặn được Shutdown / Restart / Sleep / Hibernate thật sự.**
   Tool chỉ *nhắc nhở* vào lúc đăng nhập và lúc máy thức dậy — nó không thể
   ngăn bạn tắt máy khi chưa check-out. Hãy tập thói quen nhìn popup / icon
   trước khi rời máy.

2. **Win + L (khoá màn hình) KHÔNG kích hoạt popup.** Khoá màn hình không
   phải là Sleep — Windows không phát sự kiện nguồn điện — nên khi mở khoá
   sẽ không có nhắc nhở. Chỉ Sleep / Hibernate / đăng nhập mới kích hoạt.

3. **Môi trường công ty (Enterprise) có thể bị chặn bởi GPO / AppLocker / EDR:**

   | Bị chặn cái gì | Biểu hiện | Hướng xử lý |
   |---|---|---|
   | Cài Python | Trình cài đặt bị chặn hoặc cần Admin | Dùng bản **Python embeddable / portable** (file zip, giải nén là chạy, không cần cài); hoặc nhờ IT cài giúp |
   | `pip install` | Lỗi mạng / proxy / bị chặn PyPI | Thêm `--proxy http://proxy-cong-ty:port` vào lệnh pip, hoặc tải file `.whl` từ máy khác về cài bằng `pip install --user ten_file.whl` |
   | Task Scheduler | `setup_task.ps1` báo lỗi Access Denied | Dùng **phương án Startup folder** ở trên |
   | Chạy script PowerShell | Lỗi "running scripts is disabled" | Chạy `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` (không cần Admin); nếu vẫn bị GPO ghi đè, tạo task thủ công trong Task Scheduler (giao diện đồ hoạ) hoặc dùng Startup folder |
   | AppLocker / EDR chặn `pythonw.exe` | Tool không khởi động, có thể có cảnh báo | Trường hợp này phải liên hệ IT xin whitelist — không nên tự tìm cách lách vì có thể vi phạm chính sách công ty |

4. Tool **không kiểm tra** bạn đã thật sự check-in hay chưa — nó chỉ nhắc.
   Bấm "Xác nhận rồi" là do bạn tự chịu trách nhiệm.

---

## Cấu trúc file

| File | Vai trò |
|---|---|
| `checkin_guard.pyw` | Script chính (đuôi `.pyw` để chạy ẩn, không hiện cửa sổ đen) |
| `setup_task.ps1` | Đăng ký chạy tự động khi login qua Task Scheduler |
| `README.md` | File hướng dẫn này |
