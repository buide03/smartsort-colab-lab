> **Bản Render Static mới:** học sinh mở URL, không cài Python/PyTorch. Chạy local bằng `python run_browser_lab.py` tại http://127.0.0.1:8001/. Xem [hướng dẫn Browser Lab](DEPLOY_RENDER_STATIC.md). Các bước backend bên dưới dành cho bản Docker/Oracle/Railway.

# Cài đặt SmartSort sau khi clone repo

Hướng dẫn này dành cho người dùng mới, từ cài môi trường đến mở giao diện và thực hiện bài lab. Không cần Node.js, npm, Docker hoặc Google Colab để chạy bản local.

**Luồng lớp học mới:** train trên Colab, nhập checkpoint vào web để chạy validation và test. Xem [Colab + Docker/Railway](COLAB_VA_DEPLOY_RAILWAY.md) nếu muốn cung cấp URL cho học sinh; học sinh dùng URL không cần cài Python. Hướng dẫn dưới đây vẫn dùng để chạy backend trên máy và kiểm thử local.

## 1. Chuẩn bị

| Thành phần | Yêu cầu |
|---|---|
| Python | 3.10 trở lên; khuyến nghị Python 3.11 hoặc 3.12, bản 64-bit |
| Git | Dùng để clone và cập nhật repo |
| Trình duyệt | Chrome, Edge hoặc Firefox |
| GPU | Không bắt buộc; mặc định có thể chạy CPU |
| Internet | Cần khi clone, cài thư viện và lần đầu tải trọng số ImageNet |

Cài [Python](https://www.python.org/downloads/) và [Git](https://git-scm.com/downloads). Trên Windows, chọn **Add Python to PATH** nếu trình cài đặt có tùy chọn này, rồi mở lại PowerShell.

Kiểm tra trong terminal:

```powershell
git --version
python --version
```

Trên Linux/macOS, lệnh Python thường là `python3 --version`.

Repo hiện ở chế độ **public**. Người dùng có thể clone để chạy mà không cần đăng nhập GitHub hoặc được cấp quyền riêng. Quyền ghi/push vẫn dành cho chủ repo và cộng tác viên được cấp quyền. Xem [hướng dẫn clone của GitHub](https://docs.github.com/en/repositories/creating-and-managing-repositories/cloning-a-repository).

## 2. Clone repo

Mở terminal tại thư mục muốn lưu dự án:

```bash
git clone https://github.com/buide03/smartsort-colab-lab.git
cd smartsort-colab-lab
```

Đăng nhập GitHub nếu Git yêu cầu. Sau khi clone, thư mục hiện tại phải có `run_local.py`, `requirements.txt` và thư mục `smartsort_app/`.

## 3. Cài môi trường trên Windows — PowerShell

Trong thư mục `smartsort-colab-lab`, chạy lần lượt:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Dòng cài `torch torchvision` chọn bản CPU để bắt đầu mà không cần CUDA. Dòng tiếp theo cài các thư viện còn lại. Hãy đợi cài đặt hoàn tất; PyTorch là gói lớn, thời gian phụ thuộc mạng và máy.

Các lệnh gọi trực tiếp Python trong `.venv`, nên không cần kích hoạt môi trường hay đổi ExecutionPolicy. Môi trường này tách thư viện của lab khỏi Python toàn hệ thống; xem [tài liệu venv của Python](https://docs.python.org/3.12/library/venv.html).

Nếu máy có nhiều Python và muốn dùng đúng 3.12 đã cài, thay lệnh tạo môi trường bằng:

```powershell
py -3.12 -m venv .venv
```

### Khởi chạy

```powershell
.\.venv\Scripts\python.exe run_local.py
```

Mở **[http://127.0.0.1:8000](http://127.0.0.1:8000)**. Giữ terminal này mở; không cần thêm terminal frontend. Nhấn `Ctrl+C` trong terminal để dừng server.

## 4. Cài môi trường trên Linux/macOS

Trong thư mục repo:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python run_local.py
```

Mở **[http://127.0.0.1:8000](http://127.0.0.1:8000)**, giữ terminal chạy. Trên Linux, nếu `venv` chưa được cài, cài gói venv tương ứng với phiên bản Python bằng trình quản lý gói của hệ điều hành rồi tạo lại môi trường.

Trên Linux muốn cài rõ bản CPU, chạy dòng sau **trước** dòng cài requirements:

```bash
./.venv/bin/python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

Ứng dụng hiện chọn CUDA nếu có, còn lại chạy CPU; không tự bật MPS trên macOS.

## 5. Kiểm tra môi trường và tùy chọn GPU

Windows:

```powershell
.\.venv\Scripts\python.exe -c "import torch, torchvision, fastapi; print('Torch:', torch.__version__); print('Torchvision:', torchvision.__version__); print('CUDA:', torch.cuda.is_available())"
```

Linux/macOS:

```bash
./.venv/bin/python -c "import torch, torchvision, fastapi; print('Torch:', torch.__version__); print('Torchvision:', torchvision.__version__); print('CUDA:', torch.cuda.is_available())"
```

`CUDA: False` **không phải lỗi**: lab vẫn chạy bằng CPU. Nếu có GPU NVIDIA và muốn dùng CUDA, chọn lệnh cài đúng hệ điều hành/Pip/Python/CUDA theo [trang cài đặt chính thức của PyTorch](https://pytorch.org/get-started/locally/), rồi chạy lệnh bằng Python của `.venv`. Cài `torch` và `torchvision` cùng bộ tương thích; không đoán phiên bản CUDA hoặc cài riêng hai phiên bản không khớp. Nếu đã cài bản CPU, thay bằng bộ CUDA phù hợp theo hướng dẫn PyTorch.

## 6. Thực hiện bài lab trên giao diện

1. **Tạo phiên:** bấm “Phiên mới”, đặt tên nhóm/bài thực hành.
2. **Tải ảnh:** chọn nhiều ảnh hoặc ZIP. Có thể thử ZIP mẫu tại `SmartSort_Lab/SmartSort_Dataset_Original.zip`; giao diện vẫn coi mọi ảnh là chưa có nhãn.
3. **Gán nhãn:** chọn Nhựa/Giấy/Kim loại; có thể chọn nhiều ảnh để gán cùng nhãn. Chọn Bỏ qua cho ảnh ngoài ba lớp hoặc không phù hợp quy tắc bài học. Cần ít nhất 10 ảnh khác nhau mỗi lớp, khuyến nghị từ 50 ảnh/lớp.
4. **Chia ba tập:** mặc định train/validation/test = 70/15/15, seed 42. Kiểm tra số lượng rồi chốt nhãn và bản chia.
5. **Huấn luyện Colab và validation web:** đặt cấu hình, tải gói train, mở notebook Colab mới và chọn T4 GPU, train rồi nhập gói mô hình về đúng phiên. Bấm **Chạy validation trên web** để xem các cấu hình/epoch. Nút **Train trên máy (tùy chọn)** chỉ dành cho bản local khi được bật; bản Docker tắt nút này.
6. **Chốt cấu hình:** xem bảng validation, chọn cấu hình đạt tiêu chí. Mặc định macro-F1 validation ≥ 0.80 và recall từng lớp ≥ 0.60; đây là mục tiêu thực hành đặt trước thí nghiệm.
7. **Chạy test:** bấm “Mở test & thu kết quả”. Đọc accuracy, precision/recall/F1, confusion matrix và ảnh sai.
8. **Tải kết quả:** tải ZIP báo cáo/checkpoint/CSV. Có thể thử ảnh mới sau khi test hoàn tất.

Nếu validation chưa đạt, điều chỉnh dữ liệu/cấu hình dựa trên train và validation, chưa mở test. Sau khi xem test và muốn cải tiến, cần tập test mới độc lập. Xem [hướng dẫn dạy học](HUONG_DAN_DAY_HOC.md) để tổ chức buổi học và câu hỏi thảo luận.

## 7. Mở lại, cập nhật và sao lưu

Lần sau không cần clone hoặc cài lại từ đầu. Mở terminal tại thư mục repo và chạy:

Windows:

```powershell
.\.venv\Scripts\python.exe run_local.py
```

Linux/macOS:

```bash
./.venv/bin/python run_local.py
```

Ảnh, nhãn, bản chia, cấu hình và kết quả lưu trong `.smartsort/`. Không xóa thư mục này nếu muốn giữ bài làm. `.smartsort/` và `.venv/` được Git ignore, không đi theo Git clone/push. Để sao lưu bài học, tải ZIP kết quả và sao chép `.smartsort/` khi server đã dừng; không cần sao chép `.venv` sang máy khác, hãy tạo lại môi trường ở máy mới.

Tác vụ đang train khi tắt máy không tiếp tục chạy trong nền. Khởi động lại server và chạy lại tác vụ cần thiết; nhãn và dữ liệu đã lưu vẫn còn. Test bị ngắt chỉ được thử lại bằng mô hình đã chốt.

Để lấy bản cập nhật, dừng server rồi chạy:

```bash
git pull --ff-only
```

Sau đó cài lại `requirements.txt` bằng Python của `.venv` và khởi động lại. Nếu Git báo có thay đổi local, lưu/commit thay đổi của bạn trước; không dùng lệnh xóa/reset dữ liệu để cập nhật.

## 8. Lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `git` hoặc `python` không nhận diện | Cài Git/Python, kiểm tra PATH, mở lại terminal. Windows có Python Launcher thì thử `py --version`. |
| Clone báo `Repository not found` / lỗi kết nối | Kiểm tra URL và kết nối GitHub; repo này public, không cần đăng nhập để clone. |
| Không tìm thấy `requirements.txt` / `run_local.py` | Chạy `cd smartsort-colab-lab` trước, kiểm tra đúng thư mục repo. |
| `No module named ...` | Cài requirements bằng chính Python `.venv` dùng để chạy, không trộn môi trường. |
| PowerShell chặn `Activate.ps1` | Dùng trực tiếp `.\.venv\Scripts\python.exe` như hướng dẫn, không cần activate. |
| Cổng 8000 đã được dùng | Có thể app đang chạy. Mở URL hiện tại, hoặc chạy `run_local.py --port 8001` và mở `http://127.0.0.1:8001`. |
| Trình duyệt không kết nối backend | Kiểm tra server còn chạy, đúng cổng và không có lỗi trong terminal. `127.0.0.1` chỉ truy cập từ chính máy đang chạy server. |
| Train lần đầu chờ ở bước khởi tạo/tải mô hình | Chờ Python nạp thư viện và tải weights; kiểm tra mạng nếu tải thất bại. |
| `CUDA: False` | Chạy CPU bình thường; muốn GPU thì kiểm tra driver và bộ PyTorch CUDA tương thích. |
| Lỗi thư viện Torch/Torchvision hoặc không tìm thấy bản cài | Dùng Python được hỗ trợ và cài cả hai theo bộ chính thức của PyTorch trong cùng `.venv`. |
| Không chia được dữ liệu | Gán nhãn hoặc Bỏ qua tất cả ảnh, đủ 10 ảnh/lớp; ba tỷ lệ phải cộng thành 100%. |
| Không chốt được mô hình | Cấu hình chưa đạt tiêu chí validation; kiểm tra dữ liệu/nhãn, điều chỉnh bằng validation trước khi mở test. |

## 9. Kiểm tra mã dành cho người phát triển

Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install httpx
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_workflow.py -v
```

Linux/macOS: dùng `./.venv/bin/python` cho hai lệnh tương ứng. Không cần cài Playwright để dùng sản phẩm bình thường. Kiểm thử trình duyệt nâng cao và kết quả xác minh nằm ở [KIEM_THU_LOCAL.md](KIEM_THU_LOCAL.md).
