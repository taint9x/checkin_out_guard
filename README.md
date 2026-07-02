# Checkin/Checkout Guard - Hướng dẫn cài đặt

## 1. Công cụ này làm gì, chạy khi nào?

Đây là một chương trình chạy nền trên Windows, hiển thị popup nhắc
**"Have you checked in / checked out?"** và chặn tắt máy cho đến khi bạn xác
nhận. Popup xuất hiện chính xác ở **3 thời điểm**:

| # | Thời điểm | Cơ chế kỹ thuật | Có chặn được không? |
|---|-----------|------------------|----------------------|
| 1 | **Ngay sau khi đăng nhập Windows** | Task Scheduler chạy chương trình với trigger "At log on" | Không cần chặn, chỉ hiện popup |
| 2 | **Ngay trước khi Shutdown / Restart** | Bắt sự kiện `WM_QUERYENDSESSION` của Windows, dùng `ShutdownBlockReasonCreate` | **Có** - máy sẽ đứng ở màn hình "Đang chờ ứng dụng đóng lại" cho đến khi bạn bấm nút "Confirmed" trong popup |
| 3 | **Ngay sau khi máy thức dậy từ Sleep/Hibernate** | Bắt sự kiện `WM_POWERBROADCAST` (`PBT_APMRESUMEAUTOMATIC` / `PBT_APMRESUMESUSPEND`) | Không - Windows không cho phép app nào chặn trước lúc Sleep/Hibernate xảy ra (xem mục "Giới hạn cần biết" bên dưới), popup chỉ hiện **sau khi** thức dậy |

Trong popup có 2 nút:
- **"Not yet, go to check-in/check-out website"** - mở trình duyệt tới URL
  check-in, popup **vẫn còn hiện** (không tự đóng)
- **"Confirmed"** - đóng popup; nếu đang ở tình huống #2 (chuẩn bị tắt máy),
  bấm nút này mới cho phép máy tiếp tục tắt/khởi động lại

Chương trình phải đang **chạy nền liên tục** từ lúc đăng nhập thì mới bắt
được sự kiện tắt máy/thức dậy. Nếu bạn tắt process trong Task Manager, popup
sẽ không hiện nữa cho đến khi đăng nhập lại (Task Scheduler tự chạy lại).

Không cần quyền Admin ở bất kỳ bước nào.

## 2. Chọn 1 trong 3 cách cài đặt

| Lựa chọn | File cần dùng | Có cần cài Python không? | Khi nào nên chọn |
|----------|---------------|---------------------------|-------------------|
| **Option 1: Dùng file .exe có sẵn** | `checkin_guard.exe` | Không | Cách đơn giản nhất, khuyến nghị cho hầu hết mọi người, kể cả máy không cài Python |
| **Option 2: Chạy trực tiếp file .pyw** | `checkin_guard.pyw` (qua `pythonw.exe`) | Có | Khi bạn muốn sửa code và chạy thử ngay, không muốn build lại .exe mỗi lần |
| **Option 3: Tự build .exe từ .pyw** | `checkin_guard.pyw` -> build ra `checkin_guard.exe` mới | Có (chỉ trên máy build) | Khi bạn đã sửa xong code và muốn deploy lại thành 1 file .exe độc lập, gọn nhẹ, để đưa cho máy khác dùng như Option 1 |

Cả 3 cách đều dùng chung `setup_task.ps1` để đăng ký Task Scheduler -
script này tự nhận diện: nếu có `checkin_guard.exe` trong thư mục thì ưu
tiên dùng file đó, nếu không có thì tìm `checkin_guard.pyw` + `pythonw.exe`.

---

## Option 1: Dùng file .exe có sẵn (khuyến nghị)

Không cần cài Python. Chỉ cần các file:

- `checkin_guard.exe`
- `setup_task.ps1`
- `README.md` (file này)

### Bước 1: Đặt các file vào 1 thư mục cố định

Copy 3 file trên vào 1 thư mục bạn sẽ **KHÔNG** xóa/di chuyển sau này, ví dụ:
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

### Bước 3: Test thử ngay (không cần restart máy)

Trong PowerShell:

```
Start-ScheduledTask -TaskName CheckinCheckoutGuard
```

Popup sẽ hiện ra sau vài giây. Trong Task Manager, process sẽ hiện tên
**`checkin_guard`** (nhờ metadata trong `version_info.txt` lúc build).

### Bước 4: Test thật với Shutdown/Restart

1. Đảm bảo task đang chạy (đăng nhập lại 1 lần để Task Scheduler tự khởi
   động, hoặc chạy `Start-ScheduledTask` như Bước 3)
2. Bấm Start > Shutdown (hoặc Restart)
3. Windows sẽ hiện màn hình "Đang chờ ứng dụng đóng lại" (đây là màn hình
   chuẩn của Windows khi có app dùng `ShutdownBlockReason`) - popup của bạn
   sẽ hiện phía sau/cùng lúc
4. Chỉ khi bạn bấm "Confirmed" thì máy mới tiếp tục tắt/restart

### Gỡ bỏ (khi không dùng nữa)

```
Unregister-ScheduledTask -TaskName CheckinCheckoutGuard -Confirm:$false
```

Và tắt process đang chạy (nếu có) trong Task Manager: tìm `checkin_guard.exe`.

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

File kết quả nằm ở `dist\checkin_guard.exe`.

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
