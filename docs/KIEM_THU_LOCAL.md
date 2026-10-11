# Xác minh SmartSort local

Ngày kiểm thử: 11/10/2026. Đã chạy giao diện bằng Microsoft Edge headless trên Windows, backend FastAPI local và EfficientNet-B0 thật trên CPU (PyTorch 2.14.1, Torchvision 0.29.1). Không dùng kết quả giả để xác minh mô hình.

## Kiểm thử toàn quy trình

- Tải ZIP 195 ảnh qua giao diện; đủ 195 ảnh bắt đầu **chưa có nhãn**, không dùng nhãn thư mục/manifest để tự gán.
- Thao tác chọn ảnh và gán nhãn theo nhóm qua giao diện. Phần còn lại trong kiểm thử được gán bằng nhãn tham chiếu của bộ dữ liệu làm fixture, qua API gán nhãn; đây chỉ là cách tự động hóa kiểm thử, không phải tính năng tự gán nhãn của sản phẩm.
- 180 ảnh thuộc ba lớp được đưa vào thí nghiệm; 15 ảnh thủy tinh/carton được gán Bỏ qua.
- Chia 70/15/15: train 126 (42/lớp), validation 27 (9/lớp), test 27 (9/lớp). Ba tập không giao nhau.
- Huấn luyện ba learning rate 0.001, 0.003, 0.01, dropout 0.2, tối đa 60 epoch; validation macro-F1 tốt nhất của cả ba cấu hình khoảng 0.927. Lựa chọn cuối tie-break bằng validation loss.
- Chốt checkpoint bằng giao diện rồi mới chạy test: **accuracy 25/27 = 92.59%, macro-F1 0.925**, một lỗi có confidence ≥ 0.70.
- Tải ZIP, báo cáo, CSV và checkpoint; kiểm tra CRC ZIP và thử suy luận một ảnh mới.
- Reload trang vẫn thấy cùng phiên, cấu hình và kết quả đã lưu.
- Không có lỗi JavaScript trong toàn bộ luồng; kiểm tra giao diện ở 1440 px và 390 px, không tràn ngang trên màn hình hẹp.

Điểm test này là kết quả của một bản chia nhỏ dùng **xác minh chức năng sản phẩm**. Bộ ảnh đã được dùng cho ví dụ trước; không dùng điểm này làm bằng chứng đánh giá mới độc lập hay so trực tiếp với bản chia của notebook cũ.

## Kiểm tra các ranh giới bài học

- Chưa gán nhãn hết: không chia dữ liệu.
- Chưa chia: không train.
- Đã chia: không sửa nhãn; ảnh test bị chặn cho đến khi đánh giá cuối hoàn tất.
- Chưa train hoặc cấu hình không đạt validation: không chốt.
- Chưa chốt: không chạy test.
- Đã chốt: không train lại.
- Đã test: không sửa dữ liệu/chọn lại cấu hình; gọi test trả kết quả cũ.
- Test thất bại/ngắt: chỉ được thử lại mô hình đã chốt, không quay lại tuning.

Ba bài kiểm tra tự động trong `tests/test_workflow.py` đã đạt, kiểm tra nhập ảnh không suy ra nhãn, ảnh trùng/hỏng, chia không giao nhau, khóa nhãn/test và validation gate. Test này dùng mô phỏng huấn luyện để tập trung vào ranh giới trạng thái; kiểm thử trình duyệt nêu trên dùng mô hình thật.

## Tái chạy

```powershell
python -m pip install httpx playwright
python -m unittest discover -s tests -p test_workflow.py -v
```

Khởi động server bằng `python run_local.py` trong cửa sổ khác, rồi chạy:

```powershell
python tests/verify_browser.py
```

Script trình duyệt mặc định dùng đường dẫn Microsoft Edge trên Windows và ZIP mẫu trong repo. Screenshot/log lưu ở `tests/runtime/` (Git ignore). Các nhãn được lưu tại `.smartsort/`; script tạo một phiên kiểm thử mới, không sửa phiên người học đang dùng. Bản chia dựa trên manifest phiên, nên số đo giữa các phiên mới có thể thay đổi.
