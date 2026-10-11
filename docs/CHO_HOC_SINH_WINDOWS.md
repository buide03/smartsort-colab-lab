# Học sinh: mở SmartSort bằng một câu lệnh

Dành cho Windows 10/11 64-bit. Bản này là **Browser Lab**: train trên Google Colab GPU, validation/chốt/test trên trình duyệt của máy học sinh. Không cần biết lập trình, cài Git, Docker hoặc PyTorch. Máy cần Internet lần đầu và một trình duyệt Chrome/Edge mới.

## Lần đầu

1. Bấm Start, gõ **PowerShell**, mở **Windows PowerShell** bình thường.
2. Giáo viên cung cấp câu lệnh dưới đây. Học sinh sao chép cả dòng, dán vào PowerShell và bấm Enter:

```powershell
& ([scriptblock]::Create((Invoke-RestMethod 'https://raw.githubusercontent.com/buide03/smartsort-colab-lab/main/start-student.ps1')))
```

3. Chờ đến khi thấy **SAN SANG**. Trình duyệt tự mở **http://127.0.0.1:8001/**.
4. Tạo phiên có tên nhóm; tải ảnh, gán nhãn rồi làm theo năm bước trên giao diện.

Câu lệnh tải và chạy launcher từ repo của giáo viên. Launcher tải Python portable 3.13.16 từ python.org, kiểm tra SHA-256 theo bản phát hành chính thức, tải bộ lab khoảng 3 MB và kiểm tra hash của gói. Python portable khoảng 11 MB; tổng tải lần đầu khoảng 14 MB, tùy kiến trúc. File nằm trong `%LOCALAPPDATA%\SmartSortBrowserLab` và không cần thay PATH hay cài package Python. [Python embeddable package](https://docs.python.org/3.13/using/windows.html#the-embeddable-package), [nguồn tải và hash Python](https://www.python.org/downloads/release/python-31316/).

## Lần sau

- Bấm đúp **SmartSort Lab** trên Desktop. Khi có mạng, launcher kiểm tra phiên bản mới; nếu mất mạng và bộ cài đã tải đủ, nó dùng bản đã lưu.
- Có thể đóng cửa sổ PowerShell sau khi trang đã mở; server chạy nền.
- Kết thúc buổi học: bấm **Sao lưu phiên** trên web để tải ZIP. Muốn dừng server, bấm **Dung SmartSort Lab** trên Desktop. Đóng trình duyệt không tự dừng server.
- Sau khi khởi động lại máy, bấm **SmartSort Lab** để mở lại. Dùng cùng browser profile và địa chỉ `http://127.0.0.1:8001/` để thấy phiên cũ.

Không mở cùng lab trong hai tab của cùng browser profile. Không dùng tab ẩn danh cho bài cần lưu. Dữ liệu được lưu trong trình duyệt, không nằm trong thư mục Python; đổi trình duyệt, đổi port hoặc xóa site data cần nhập ZIP sao lưu để phục hồi.

## Khi có lỗi

| Thông báo | Cách xử lý |
|---|---|
| Không tải được / kiểm tra Internet | Kiểm tra mạng, quyền truy cập GitHub/python.org rồi chạy lại cùng câu lệnh. |
| Cổng 8001 đang có ứng dụng/bản lab khác | Đóng bản local cũ hoặc bấm nút dừng của lab rồi mở lại. Không tùy tiện đổi port vì đó là nơi lưu phiên học. |
| Lab đã mở trong tab khác | Đóng tab cũ rồi tải lại trang. |
| Windows hoặc nhà trường chặn chạy phần mềm/script | Nhờ giáo viên/quản trị phòng máy hỗ trợ; không tìm cách vượt chính sách máy. |
| Bộ nhớ trình duyệt đầy | Tải ZIP sao lưu, giảm số/kích thước ảnh hoặc nhờ giáo viên dọn dữ liệu. |

Mã lớp/tài khoản server không cần trong bản local này. Học sinh dùng tài khoản Google của mình khi mở Colab; notebook sẽ yêu cầu chọn GPU và chạy các ô theo thứ tự. Cài local không tự đăng nhập hoặc tạo runtime Colab. [Hướng dẫn đầy đủ luồng bài học](DEPLOY_RENDER_STATIC.md).

## Giáo viên / kỹ thuật phòng máy

Repo có `start-student.ps1` và gói student trong `student/release.json`. Không dùng `start_local.ps1` cho hướng dẫn một câu lệnh này vì đó là bản backend cần nhiều thư viện.

Nếu cần chạy launcher tải sẵn từ repo:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-student.ps1
```

Tham số `-NoBrowser`, `-NoShortcut`, `-Offline`, `-InstallRoot` và `-Port` phục vụ kiểm thử/quản lý. `-Stop` chỉ dừng PID có executable và command line khớp server của bản cài này; không tự dừng ứng dụng khác chiếm port. Launcher không xóa phiên trình duyệt khi cập nhật/dừng lab.

Trình build `python browser_lab/build_student_package.py` tạo gói có đường dẫn chứa version hash; gói cũ giữ nguyên để tải không bị lẫn phiên bản trong lúc cập nhật repo. Gói không chứa dataset hay phiên học. Chưa kiểm thử trên Mac/Linux hoặc thiết bị Windows ARM64 thật; ARM64 có nguồn runtime/hash riêng, cần kiểm tra trên máy tương ứng trước khi dùng trong lớp.
