# Lab Google Colab: Nhựa — Giấy — Kim loại

## Chạy trên Colab

1. Truy cập https://colab.research.google.com/ → **File → Upload notebook** → chọn `SmartSort_Colab_Lab.ipynb`.
2. Chọn **Runtime → Change runtime type → T4 GPU**.
3. Chọn **Runtime → Run all**. Ở hộp tải dữ liệu, chọn **một** ZIP: `SmartSort_Data_Split.zip` đã chia sẵn, hoặc ZIP gốc `SmartSort_Dataset_PNG (2).zip`.
4. Theo dõi bảng validation. Mục tiêu mặc định: macro-F1 ≥ 0.80 và recall từng lớp ≥ 0.60. Nếu chưa đạt, notebook dừng trước test; điều chỉnh bằng validation rồi chạy lại từ đầu. Không hạ ngưỡng chỉ để đạt kết quả.
5. Sau khi đạt validation, notebook chạy test và tải `SmartSort_Results.zip`. Giữ file này trước khi đóng Colab.
6. Để thử ảnh mới, bỏ dấu `#` trước `upload_and_predict()` ở ô 11 và chạy ô đó.

## Dữ liệu đã chuẩn bị

| Tập | Kim loại | Giấy | Nhựa | Ngoài lớp | Tổng |
|---|---:|---:|---:|---:|---:|
| Train | 32 | 32 | 32 | 0 | 96 |
| Validation | 8 | 8 | 8 | 0 | 24 |
| Test basic | 10 | 10 | 10 | 0 | 30 |
| Test variation | 10 | 10 | 10 | 0 | 30 |
| Test outside | 0 | 0 | 0 | 15 | 15 |

ZIP đã chia và ZIP gốc tạo cùng danh sách train/validation theo seed 42. Giữ nguyên toàn bộ test; không augmentation test. Đã kiểm tra CRC, SHA-256, giải mã cả 195 ảnh RGB 256×256; không có ảnh trùng theo nguồn, nội dung file hay pixel. Kiểm tra này chưa loại trừ cùng vật thể được chụp thành nhiều ảnh khác nhau.

## Mô hình và đánh giá

EfficientNet-B0 với trọng số ImageNet, đóng băng backbone, học classifier 3 lớp; tùy chọn fine-tuning block cuối. Notebook phân loại một ảnh, không phát hiện vị trí hay nhiều vật thể. Có checkpoint tốt nhất, early stopping, learning curves và cổng validation trước test.

Kết quả gồm accuracy và khoảng Wilson 95%, precision/recall/F1 từng lớp, macro-F1, confusion matrix, basic so với variation, log-loss, Brier score, ECE, ROC-AUC OVR, lỗi tự tin cao, khả năng từ chối ảnh ngoài lớp bằng ngưỡng cố định, tốc độ suy luận và kích thước mô hình. Báo cáo `REPORT.md` tự rút ra lớp yếu, cặp nhầm nhiều nhất và các yếu tố cần kiểm tra. CSV phân tích lỗi có cột điều kiện chụp để người học ghi chú.

## File kết quả

- `best_model.pt`: checkpoint, nhãn và thông tin tiền xử lý.
- `REPORT.md`, `results.json`: kết quả và nhận xét tự động theo lần chạy.
- `history.csv`, `validation.json`, `test_metrics.csv`, `per_class_metrics.csv`.
- `test_predictions.csv`, `outside_predictions.csv`, `error_review_template.csv`.
- `split_manifest.csv`, `dataset_audit.json`, `config.json`, `environment.json`.
- Biểu đồ learning curves, confusion matrix, ảnh sai và ảnh train.

## Giới hạn

Validation chỉ 8 ảnh/lớp; test chỉ 20 ảnh/lớp. Bộ dữ liệu phù hợp thực hành. Điểm softmax chưa hiệu chỉnh và heuristic confidence không đảm bảo nhận ra lớp lạ. Không dùng test để chọn mô hình hoặc ngưỡng. Nếu đổi mô hình sau khi xem test, cần test mới độc lập.

Nguồn dữ liệu theo metadata cung cấp: TrashNet, Gary Thung, MIT; giữ nguyên `LICENSE.txt` trong ZIP đã chia. Tài liệu: https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.efficientnet_b0.html và https://docs.pytorch.org/tutorials/beginner/transfer_learning_tutorial.html.

## Chạy kiểm tra trên máy tính (tùy chọn)

Cài thư viện từ `requirements.txt` ở thư mục gốc repo, đặt biến môi trường `SMARTSORT_ZIP` là đường dẫn ZIP; chạy `python lab_source.py`. Không cần Google Colab cho chế độ này. Kết quả mặc định tại `local_runtime/outputs`; đặt `SMARTSORT_OUTPUT` để đổi thư mục. `build_notebook.py` dùng để tạo lại notebook và ZIP chia từ `SmartSort_Dataset_Original.zip` đặt cạnh script, hoặc đường dẫn truyền bằng `--zip PATH`.
