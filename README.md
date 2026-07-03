# Checkin/Checkout Guard - Hướng dẫn cài đặt

## 1. Công cụ này làm gì, chạy khi nào?

Đây là một chương trình chạy nền trên Windows, hiển thị popup nhắc
**"Have you checked in / checked out?"** và chặn tắt máy cho đến khi bạn xác
nhận. Popup xuất hiện chính xác ở **3 thời điểm**:

| # | Thời điểm | Cơ chế kỹ thuật | Có chặn được không? |
|---|-----------|------------------|----------------------|
| 1 | **Ngay sau khi đăng nhập Windows** | Task Scheduler chạy chương trình với trigger "At log on" | Không cần chặn, chỉ hiện popup |
| 2 | **Bấm shortcut "Shutdown (with check-in)" trên Desktop** (khuyến nghị) | Chạy `checkin_guard.exe --shutdown`: popup hiện trước, **chưa có gì xảy ra cả**; chỉ khi bấm "Confirmed" máy mới thật sự tắt | **Có, hoàn toàn** - đây là cách duy nhất đạt được trải nghiệm "popup trước, tắt máy sau" trên Windows |
| 3 | **Bấm Shutdown/Restart từ Start menu** | Bắt sự kiện `WM_QUERYENDSESSION`, dùng `ShutdownBlockReasonCreate` | **Có, nhưng qua màn hình trung gian của Windows** - xem giải thích quan trọng bên dưới |
| 4 | **Ngay sau khi máy thức dậy từ Sleep/Hibernate** | Bắt sự kiện `WM_POWERBROADCAST` (`PBT_APMRESUMEAUTOMATIC` / `PBT_APMRESUMESUSPEND`) | Không - Windows không cho phép app nào chặn trước lúc Sleep/Hibernate xảy ra (xem mục "Giới hạn cần biết" bên dưới), popup chỉ hiện **sau khi** thức dậy |

Trong popup có 2 nút:
- **"Not yet, go to check-in/check-out website"** - mở trình duyệt tới URL
  check-in, popup **vẫn còn hiện** (không tự đóng)
- **"Confirmed"** - đóng popup; ở tình huống #2 bấm nút này máy sẽ tắt thật;
  ở tình huống #3 bấm nút này mới cho phép máy tiếp tục tắt/khởi động lại

### QUAN TRỌNG: luồng khi bấm Shutdown từ Start menu (tình huống #3)

Khi app chặn shutdown từ Start menu, **Windows bắt buộc chen màn hình toàn
màn hình của chính nó** vào giữa (không app nào tắt được màn hình này, và
không xóa được nút "Shut down anyway" trên đó nếu không có policy IT):

1. Bấm Start > Shutdown -> Windows hiện màn hình tối "**This app is
   preventing you from shutting down**" kèm dòng chữ *"Check-in/check-out
   not confirmed. Click 'Cancel' to go back and confirm."*
2. Bấm **Cancel** trên màn hình đó -> quay về desktop, popup của app đang
   chờ sẵn
3. Bấm "Not yet..." để mở website check-in, hoặc "Confirmed" để xác nhận
4. Sau khi Confirmed, bấm Shutdown lại -> máy tắt bình thường

Nếu bấm "**Shut down anyway**" trên màn hình của Windows thì máy tắt luôn -
app không thể ngăn được (giới hạn của Windows, cần GPO/IT mới khóa được nút
này). Vì vậy **cách dùng khuyến nghị là shortcut "Shutdown (with check-in)"**
(tình huống #2): popup hiện trước tiên, không có màn hình trung gian nào,
không có nút bỏ qua nào - chạy `create_shutdown_shortcut.ps1` 1 lần để tạo
shortcut này trên Desktop.

Chương trình phải đang **chạy nền liên tục** từ lúc đăng nhập thì mới bắt
được sự kiện tắt máy/thức dậy. Nếu bạn tắt process trong Task Manager, popup
sẽ không hiện nữa cho đến khi đăng nhập lại (Task Scheduler tự chạy lại).

Không cần quyền Admin ở bất kỳ bước nào.

## 2. Chọn 1 trong 3 cách cài đặt

| Lựa chọn | File cần dùng | Có cần cài Python không? | Khi nào nên chọn |
|----------|---------------|---------------------------|-------------------|
| **Option 1: Dùng file .exe có sẵn** | `checkin_guard.exe` (1 file duy nhất) | Không | Cách đơn giản nhất, khuyến nghị cho hầu hết mọi người, kể cả máy không cài Python |
| **Option 2: Chạy trực tiếp file .pyw** | `checkin_guard.pyw` (qua `pythonw.exe`) | Có | Khi bạn muốn sửa code và chạy thử ngay, không muốn build lại .exe mỗi lần |
| **Option 3: Tự build .exe từ .pyw** | `checkin_guard.pyw` -> build ra 1 file `checkin_guard.exe` mới | Có (chỉ trên máy build) | Khi bạn đã sửa xong code và muốn deploy lại thành 1 file .exe độc lập, gọn nhẹ, để đưa cho máy khác dùng như Option 1 |

Cả 3 cách đều dùng chung `setup_task.ps1` để đăng ký Task Scheduler -
script này tự nhận diện theo thứ tự ưu tiên: `checkin_guard.exe` dạng file
đơn lẻ -> `checkin_guard\checkin_guard.exe` (nếu bạn tự build kiểu thư mục,
xem mục "Mức sử dụng tài nguyên" bên dưới) -> `checkin_guard.pyw` +
`pythonw.exe`.

---

## 3. Mức sử dụng tài nguyên (RAM/CPU)

Chương trình chạy nền gần như không tốn tài nguyên:

- **RAM**: ~17 MB tổng cộng lúc rảnh - không tăng dần theo thời gian vì
  không có rò rỉ bộ nhớ, chỉ có 1 popup ẩn + 1 hidden window luôn tồn tại.
- **CPU**: gần 0% khi rảnh - chương trình chỉ "thức dậy" khi có sự kiện
  Windows gửi tới (login/shutdown/resume) hoặc mỗi 300ms để kiểm tra hàng
  đợi popup (hàm `poll_queue` trong code), không chạy vòng lặp nặng.
- **Disk/Network**: không dùng, trừ lúc bấm nút mở trình duyệt.

### Vì sao Task Manager hiện 2 process tên `checkin_guard`?

`checkin_guard.exe` được đóng gói kiểu **`--onefile`** (đóng gói thành 1
file .exe duy nhất) bằng PyInstaller - trên Windows, kiểu đóng gói này luôn
tạo ra **2 process** khi chạy: 1 process "bootloader" tự bung (giải nén) nội
dung ra thư mục tạm, và 1 process con thật sự chạy chương trình; process cha
đứng chờ process con để trả lại đúng exit code. Đây là hành vi tiêu chuẩn
của PyInstaller khi dùng `--onefile`, không phải lỗi.

Đây là đánh đổi có chủ đích: dự án ưu tiên **1 file .exe gọn, dễ copy/di
chuyển** hơn là tối ưu tuyệt đối số process. Tổng RAM của cả 2 process cộng
lại vẫn rất nhỏ (~17 MB, gần như không đáng kể trên máy hiện đại) nên không
ảnh hưởng gì đến hiệu năng máy.

Nếu muốn chỉ còn đúng 1 process (đánh đổi lại: không còn là 1 file gọn mà
là 1 thư mục gồm exe + thư viện đi kèm), có thể build bằng `--onedir` thay
vì `--onefile` ở Bước 3 của Option 3 bên dưới - `setup_task.ps1` vẫn nhận
diện được cả 2 kiểu build.

---

## Option 1: Dùng file .exe có sẵn (khuyến nghị)

Không cần cài Python. Chỉ cần các file:

- `checkin_guard.exe`
- `setup_task.ps1`
- `setup_startup.ps1` (dự phòng, chỉ cần dùng nếu `setup_task.ps1` báo lỗi
  Access is denied - xem mục
  [Không đăng ký được Task Scheduler](#không-đăng-ký-được-task-scheduler-access-is-denied)
  bên dưới)
- `create_shutdown_shortcut.ps1` (tạo shortcut "Shutdown (with check-in)"
  trên Desktop - cách tắt máy khuyến nghị, xem mục 1)
- `README.md` (file này)

### Bước 1: Đặt các file vào 1 thư mục cố định

Copy các file trên vào 1 thư mục bạn sẽ **KHÔNG** xóa/di chuyển sau này, ví dụ:
`C:\Users\<tên-bạn>\CheckinGuard\`

### Bước 2: Đăng ký Task Scheduler

1. Mở **PowerShell** bình thường (KHÔNG cần "Run as Administrator")
2. `cd` vào thư mục vừa tạo, ví dụ:
   ```
   cd C:\Users\<tên-bạn>\CheckinGuard
   ```
3. Nếu lần đầu chạy script PowerShell trên máy, gõ 1 lần:
   ```
   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
   ```
   (Lệnh này chỉ ảnh hưởng user hiện tại, không cần Admin)
4. Chạy:
   ```
   .\setup_task.ps1
   ```
5. Thấy dòng "Task 'CheckinCheckoutGuard' created successfully." là xong.
   Nếu gặp lỗi "Access is denied", xem mục
   **[Không đăng ký được Task Scheduler](#không-đăng-ký-được-task-scheduler-access-is-denied)**
   bên dưới.

### Bước 3: Test thử ngay (không cần restart máy)

Trong PowerShell:

```
Start-ScheduledTask -TaskName CheckinCheckoutGuard
```

Popup sẽ hiện ra sau vài giây. Trong Task Manager, process sẽ hiện tên
**`checkin_guard`** (nhờ metadata trong `version_info.txt` lúc build) - có
thể thấy 2 dòng `checkin_guard` (xem mục "Mức sử dụng tài nguyên" ở trên để
biết lý do, đây là bình thường).

### Bước 4: Tạo shortcut tắt máy có kiểm soát (khuyến nghị)

```
.\create_shutdown_shortcut.ps1
```

Shortcut "**Shutdown (with check-in)**" sẽ xuất hiện trên Desktop. Từ giờ
dùng shortcut này thay cho Start > Shutdown: bấm vào -> popup hiện ra,
**chưa có gì xảy ra** -> "Confirmed" mới thật sự tắt máy, "Not yet..." mở
website check-in (popup vẫn chờ).

### Bước 5: Test với Shutdown/Restart từ Start menu

1. Đảm bảo task đang chạy (đăng nhập lại 1 lần để Task Scheduler tự khởi
   động, hoặc chạy `Start-ScheduledTask` như Bước 3)
2. Bấm Start > Shutdown (hoặc Restart)
3. Windows hiện màn hình tối "**This app is preventing you from shutting
   down**" kèm lý do "Check-in/check-out not confirmed. Click 'Cancel' to
   go back and confirm." (màn hình này là của Windows, app không bỏ được -
   xem mục 1)
4. Bấm **Cancel** -> quay về desktop, popup đang chờ -> bấm "Confirmed"
5. Bấm Shutdown lại -> máy tắt bình thường
   (Nếu ở bước 3 bấm "Shut down anyway" thì máy tắt luôn - app không ngăn
   được nút này)

### Gỡ bỏ (khi không dùng nữa)

```
Unregister-ScheduledTask -TaskName CheckinCheckoutGuard -Confirm:$false
```

Và tắt process đang chạy (nếu có) trong Task Manager: tìm `checkin_guard`.

### Không đăng ký được Task Scheduler (Access is denied)

Nếu chạy `.\setup_task.ps1` báo lỗi **"Failed to register task ... Access is
denied"**, đây thường là do máy bị IT khóa quyền Task Scheduler (hay gặp
trên máy công ty được quản lý tập trung), không phải lỗi của script.

Có 2 nguyên nhân/mức độ khác nhau:

1. **Chỉ đường WMI bị khóa** - `setup_task.ps1` bản mới nhất tự động thử
   lại bằng `schtasks.exe` (dùng Task Scheduler COM API cổ điển, không qua
   WMI) nếu cách đầu (`Register-ScheduledTask`) thất bại. Nhiều máy bị khóa
   WMI nhưng `schtasks.exe` vẫn chạy được - trường hợp này chỉ cần chạy lại
   `.\setup_task.ps1`, nó sẽ tự chuyển sang `schtasks.exe` và báo thành công.

2. **Toàn bộ Task Scheduler bị khóa** (cả `Register-ScheduledTask` lẫn
   `schtasks.exe` đều báo Access is denied) - dùng script thay thế
   **`setup_startup.ps1`**: thay vì tạo task trong Task Scheduler, nó tạo 1
   shortcut trong thư mục Startup cá nhân của bạn
   (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`) - thư mục này
   *bất kỳ user thường nào cũng ghi được*, không cần quyền Task Scheduler.
   Windows tự chạy mọi thứ trong thư mục Startup khi đăng nhập, tương đương
   trigger "At log on" của Task Scheduler. Phần chặn shutdown/thông báo
   resume vẫn hoạt động y hệt vì đó là do bản thân chương trình xử lý,
   không liên quan đến cách nó được khởi động.

   Chạy:
   ```
   .\setup_startup.ps1
   ```

   Gỡ bỏ: xóa file shortcut được tạo trong thư mục Startup (script sẽ in ra
   đường dẫn chính xác sau khi chạy).

### Process chạy bình thường nhưng shutdown không hiện popup

Nếu Task Manager thấy `checkin_guard` đang chạy, popup lúc khởi động vẫn
hiện bình thường, nhưng bấm Shutdown/Restart thì máy tắt luôn không chờ,
kiểm tra lần lượt các trường hợp sau:

**Bước 0 - Xác nhận đang chạy đúng bản build mới nhất.** Mở
`checkin_guard.log` (cùng thư mục với exe), dòng đầu của phiên chạy có dạng
`=== main() started (build 2026-07-03.1) ===`. Nếu không có build tag (log
cũ chỉ ghi `=== main() started ===`) nghĩa là đang chạy bản cũ - copy exe
mới đè lên, **tắt process cũ trong Task Manager rồi chạy lại** (exe mới chỉ
có tác dụng với process khởi động sau khi thay file).

**Trường hợp 1 - Bug block trong message handler (đã fix từ build
2026-07-03.1).** Các bản cũ chờ user bấm "Confirmed" ngay bên trong hàm xử
lý `WM_QUERYENDSESSION` trước khi trả kết quả về cho Windows. Theo tài liệu
Microsoft, handler bắt buộc phải trả về ngay - nếu block, Windows coi cửa
sổ là "treo" và tắt máy luôn. Triệu chứng trong log:
```
WM_QUERYENDSESSION received
ShutdownBlockReasonCreate returned 1
(hết, không có dòng nào tiếp theo)
```

**Trường hợp 2 - Process không có cửa sổ visible (đã fix từ build
2026-07-03.1).** Từ Windows Vista trở đi, màn hình "This app is preventing
shutdown" **chỉ hiện cho process có ít nhất 1 cửa sổ top-level đang
visible** tại thời điểm chặn - process chỉ có cửa sổ ẩn sẽ bị **kill thẳng
sau vài giây, không hiện UI gì cả**. Bản mới sửa bằng cách bật visible cho
cửa sổ listener (kiểu `WS_POPUP` kích thước 0x0 - không vẽ gì lên màn hình
nhưng `IsWindowVisible` = TRUE) ngay trước khi chặn. Log bản mới sẽ có dòng
`listener window made visible, IsWindowVisible=1`.

**Trường hợp 3 - Registry `AutoEndTasks` bật (hay gặp trên máy Enterprise
do IT cấu hình, hoặc do tinh chỉnh "tắt máy nhanh").** Khi
`HKCU\Control Panel\Desktop\AutoEndTasks` = 1, Windows tự động kill mọi app
đang chặn shutdown mà **không hiện màn hình chờ** - app không thể làm gì
được. Bản build mới tự ghi giá trị này vào log lúc khởi động (dòng
`policy HKCU\...\AutoEndTasks = ...`; không có dòng này nghĩa là không bị).
Nếu = 1, tắt bằng lệnh (không cần Admin, chỉ ảnh hưởng user hiện tại):
```
Set-ItemProperty 'HKCU:\Control Panel\Desktop' -Name AutoEndTasks -Value 0
```
Cũng xem thêm trong log các dòng `WaitToKillAppTimeout` / `HungAppTimeout`
- nếu bị IT đặt quá ngắn (vd 1000ms), cửa sổ chờ có thể biến mất trước khi
kịp thấy. Trên máy Enterprise, nếu các giá trị này do GPO ép (sửa xong bị
tự đổi lại), phải nhờ IT.

**Trường hợp 4 - Smart App Control / SmartScreen chặn file không có chữ ký
(thông báo "Part of this app has been blocked ... can't confirm who
published _lzma.pyd").** Lưu ý 2 điều:
- Thông báo này KHÔNG phải Windows Firewall (firewall chỉ quản lý mạng,
  không liên quan popup shutdown). Đây là Smart App Control chặn file
  `.pyd`/`.dll` không có chữ ký số mà bản `--onefile` giải nén ra thư mục
  tạm lúc chạy.
- Riêng `_lzma.pyd` bị chặn thì **vô hại** với app này (module nén lzma
  không được dùng) - bằng chứng là log vẫn ghi `listener window created` và
  `WM_QUERYENDSESSION received`, tức toàn bộ phần bắt shutdown hoạt động.
  Chỉ khi Protection history cho thấy các file `pywin32` (`win32api.pyd`,
  `win32gui.pyd`, `pywintypes*.dll`) bị chặn thì mới là nguyên nhân.

Để "xác nhận được publisher" như Windows yêu cầu, có script
**`sign_exe.ps1`** đi kèm: tạo certificate code-signing tự ký, cài vào
Trusted Root + Trusted Publisher của user hiện tại (sẽ có 1 hộp thoại xác
nhận của Windows - bấm Yes), rồi ký `checkin_guard.exe`. Tác dụng và giới
hạn:
- Hết cảnh báo "unknown publisher" của SmartScreen trên máy đã cài cert;
  IT có thể tạo Publisher rule (WDAC/AppLocker) tin cert này thay vì phải
  whitelist từng bản build theo hash.
- **KHÔNG** qua được Smart App Control - SAC chỉ tin cert do CA thật cấp
  hoặc app có danh tiếng. Nếu SAC là thứ đang chặn: tắt SAC (Windows
  Security > App & browser control > Smart App Control - lưu ý tắt là
  vĩnh viễn, muốn bật lại phải cài lại Windows), hoặc mua cert CA, hoặc
  nhờ IT deploy chính sách WDAC.
- Trên **Windows 11 Enterprise**, SAC thường không khả dụng (chỉ có trên
  Home/Pro cài mới) - thứ chặn app thường là WDAC/AppLocker do IT quản lý
  tập trung, bắt buộc phải nhờ IT whitelist (gửi họ file exe đã ký +
  file cert xuất từ `sign_exe.ps1`).

**Trường hợp 5 - Đọc log để chẩn đoán tiếp.** Chương trình ghi log vào
`checkin_guard.log` (cùng thư mục exe) mỗi lần chạy. Sau 1 lần thử shutdown,
đối chiếu:
- Không có `listener window created` -> tạo cửa sổ ẩn thất bại (xem
  traceback trong log, thường liên quan trường hợp 4)
- Có `listener window created` nhưng không có `WM_QUERYENDSESSION received`
  -> Windows không gửi sự kiện tới app (kiểm tra trường hợp 3, hoặc app bị
  kill trước đó)
- Có đủ `WM_QUERYENDSESSION received` + `listener window made visible` +
  `ShutdownBlockReasonCreate returned 1` nhưng máy vẫn tắt ngay -> gần như
  chắc chắn trường hợp 3 (AutoEndTasks)
- Có dòng `WM_ENDSESSION received, session_ending=True` -> Windows đã quyết
  định tắt phiên bất chấp block (user bấm "Shut down anyway", hoặc policy
  ép tắt)
- `FATAL uncaught exception` kèm traceback -> gửi nguyên văn cho người hỗ trợ

---

## Option 2: Chạy trực tiếp file .pyw (không build .exe)

Phù hợp khi bạn đang sửa code và muốn chạy thử nhanh, không tốn thời gian
build lại .exe mỗi lần đổi 1 dòng.

### Bước 1: Cài Python (nếu chưa có)

1. Tải Python tại https://www.python.org/downloads/ (bản 3.10+)
2. Khi cài, **tick chọn "Add python.exe to PATH"**
3. Cài xong, mở Command Prompt gõ `python --version` để kiểm tra

### Bước 2: Cài thư viện pywin32

Mở Command Prompt (không cần Admin):

```
pip install pywin32
```

### Bước 3: Sửa URL check-in (nếu cần)

Mở file `checkin_guard.pyw` bằng Notepad, tìm dòng:

```python
CHECKIN_URL = "https://example.com/checkin"
```

Đổi thành URL thật của bạn, lưu lại.

### Bước 4: Đặt các file vào 1 thư mục cố định

Copy các file sau vào 1 thư mục bạn sẽ **KHÔNG** xóa/di chuyển sau này:

- `checkin_guard.pyw`
- `setup_task.ps1`
- `README.md` (file này)

(Không cần `checkin_guard.exe` - nếu nó vẫn còn trong thư mục,
`setup_task.ps1` sẽ ưu tiên dùng .exe thay vì .pyw. Muốn ép chạy .pyw thì
xóa/di chuyển `checkin_guard.exe` đi trước.)

### Bước 5: Đăng ký Task Scheduler và test

Làm giống hệt "Bước 2, 3, 4" của Option 1 ở trên (`.\setup_task.ps1`,
`Start-ScheduledTask -TaskName CheckinCheckoutGuard`, test shutdown...).
Khác biệt duy nhất: Task Manager sẽ hiện process tên **`Python`** (vì chạy
qua `pythonw.exe`) thay vì `checkin_guard`.

### Gỡ bỏ

Giống Option 1, nhưng tìm `pythonw.exe` trong Task Manager thay vì
`checkin_guard.exe`.

---

## Option 3: Tự build file .exe từ .pyw

Dùng khi bạn đã sửa xong `checkin_guard.pyw` (ví dụ đổi `CHECKIN_URL`, đổi
giao diện popup...) và muốn đóng gói lại thành 1 file `.exe` độc lập, gọn,
không cần Python, để mang sang máy khác cài như Option 1.

### Bước 1: Trên máy build, cài Python + các gói cần thiết

```
pip install pyinstaller pywin32
```

### Bước 2: Sửa code trong checkin_guard.pyw theo ý muốn

Ví dụ đổi URL:

```python
CHECKIN_URL = "https://example.com/checkin"
```

### Bước 3: Build

Từ thư mục dự án (có sẵn file `version_info.txt` đi kèm), chạy:

```
python -m PyInstaller --onefile --noconsole --name checkin_guard --version-file version_info.txt checkin_guard.pyw
```

File kết quả nằm ở `dist\checkin_guard.exe`. Đây là kiểu đóng gói
**`--onefile`** - gọn nhẹ trong 1 file duy nhất, đổi lại lúc chạy sẽ hiện
2 process trong Task Manager (xem mục "Mức sử dụng tài nguyên" ở đầu file -
không đáng lo, chỉ ~17 MB RAM tổng cộng).

`version_info.txt` chứa metadata (FileDescription, ProductName...) giúp
Task Manager hiển thị tên `checkin_guard` thay vì "Python" - nếu bạn đổi
tên chương trình, có thể sửa các giá trị trong file này trước khi build.

### Bước 4: Thay thế và triển khai

1. Copy `dist\checkin_guard.exe` đè lên file `checkin_guard.exe` cũ ở thư
   mục gốc dự án (hoặc thư mục cài đặt trên máy dùng)
2. Dọn các thư mục tạm `build\`, `dist\` và file `checkin_guard.spec` nếu
   không cần giữ lại (có thể build lại bất cứ lúc nào từ file `.pyw`)
3. Làm tiếp theo hướng dẫn Option 1 (Bước 1-4) để cài/đăng ký lại task trên
   máy dùng - vì action trong Task Scheduler đã đổi, cần chạy lại
   `.\setup_task.ps1` (dùng `-Force` nên sẽ tự ghi đè task cũ)

---

## Giới hạn cần biết (quan trọng)

1. **Sleep/Hibernate không chặn được trước khi xảy ra.** Đây là giới hạn của
   Windows từ bản thân nó - từ Vista trở đi, Microsoft cố tình không cho app
   nào được "giữ" máy lại khi user chủ động bấm Sleep hoặc gập laptop (để
   tránh máy nóng/hết pin trong balo). Popup chỉ hiện **sau khi máy thức dậy
   trở lại**, không hiện trước lúc sleep/hibernate.

2. **Không phân biệt được nguyên nhân sleep** (bấm nút Sleep vs gập nắp) -
   Windows gửi cùng 1 loại message cho cả 2 trường hợp, không thể tách riêng
   ở mức user-mode (không Admin). Nhưng vì popup chỉ hiện lúc resume (không
   phải lúc sleep), việc này không còn quan trọng nữa.

3. **Win+L (khóa màn hình) không kích hoạt popup** - đây là hành vi đúng như
   bạn muốn, vì khóa màn hình không phải là sleep/shutdown, máy vẫn chạy
   bình thường.

4. **Popup có thể bị vượt qua bằng Alt+Tab / chuột phải vào taskbar** - popup
   dùng `overrideredirect` + `topmost` + `grab_set` để chặn đóng/tương tác
   cửa sổ khác của CHÍNH app này, nhưng về mặt kỹ thuật Windows vẫn cho phép
   Alt+Tab sang app khác (đây là giới hạn của Windows, không có API chính
   thức để "khóa" toàn bộ hệ thống ở mức user không Admin). Nếu cần chặn
   Alt+Tab tuyệt đối, sẽ cần dùng kỹ thuật hook bàn phím nặng hơn - nói nếu
   bạn muốn mình làm thêm phần này.

5. Process phải đang **chạy nền** từ lúc đăng nhập đến lúc tắt máy thì mới
   bắt được sự kiện shutdown. Nếu bạn vô tình tắt process trong Task Manager,
   popup shutdown sẽ không hiện lần đó cho đến khi đăng nhập lại.
