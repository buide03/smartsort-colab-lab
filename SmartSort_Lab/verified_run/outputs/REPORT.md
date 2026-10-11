# Báo cáo SmartSort — kết quả đo thực tế của lần chạy

## Cấu hình và dữ liệu
- EfficientNet-B0/ImageNet; seed 42; fine-tuning: False.
- Train 96, validation 24, test ba lớp 60, ngoài lớp 15.
- SHA-256 ZIP: 12a29fb527b0bc99101179c74b886e3a40ba6429d612b5f1d5a8312437ffb36e.
- Thiết bị: cpu; torch 2.14.1+cpu; torchvision 0.29.1+cpu.
- Checkpoint tốt nhất epoch 79; thời gian trích đặc trưng + train 17.8 giây.
- Validation: macro-F1 1.000, đạt tiêu chí đặt trước: True.

## Kết quả test
- Accuracy: 78.3%; khoảng Wilson 95% [66.4%, 86.9%].
- Macro precision/recall/F1: 0.794 / 0.783 / 0.769.
- Basic: 93.3%; variation: 63.3%; chênh basic - variation 30.0 điểm phần trăm.
- Recall thấp nhất: Kim loại (50.0%).
- Cặp nhầm nhiều nhất theo chiều thật → dự đoán: Kim loại → Nhựa (6 ảnh).
- Log-loss 0.836; Brier 0.345; ECE 0.163; ROC-AUC OVR 0.936.
- Với ngưỡng 0.70: coverage 93.3%; accuracy trên ảnh được chấp nhận 0.8214285714285714.
- Số lỗi test: 13; sai nhưng confidence ≥ ngưỡng: 10.

## Ngoài lớp và tài nguyên
- Kết quả ngoài lớp: {"n": 15, "threshold": 0.7, "rejection_rate": 0.2, "false_acceptance_rate": 0.8, "in_domain_rejection_rate": 0.06666666666666667}.
- Forward batch=1: median 27.84 ms, p95 31.79 ms.
- Tham số 4,011,391; checkpoint 15.57 MB.

## Những yếu tố cần đánh giá
1. Hiệu năng tổng thể: accuracy và macro-F1, so với baseline chọn ngẫu nhiên đều ~33.3% trên ba lớp cân bằng.
2. Khả năng từng vật liệu: precision, recall, F1, support; ưu tiên recall lớp yếu và cặp nhầm trong confusion matrix.
3. Overfit: so sánh learning curves train/validation và kết quả test; train accuracy đo khi dropout bật/ảnh tăng cường nên chỉ là chỉ dấu.
4. Độ bền vững: so sánh basic/variation; tiếp tục ghi chú nền, ánh sáng, góc chụp, che khuất, biến dạng, trong suốt/phản chiếu trong error_review_template.csv. Chênh lệch nhóm chưa xác định nguyên nhân.
5. Độ tin cậy: log-loss, Brier, ECE; kiểm tra lỗi tự tin cao. Confidence softmax chưa được hiệu chỉnh, không coi là xác suất chắc chắn đúng.
6. Giới hạn lớp lạ: tỷ lệ từ chối ngoài lớp và từ chối ảnh trong miền tại ngưỡng đã cố định. Carton/thủy tinh không được tính vào accuracy ba lớp.
7. Hiệu suất: thời gian huấn luyện, forward latency, số tham số và kích thước mô hình; đo thêm pipeline đầy đủ trước khi triển khai.
8. Độ vững của kết luận: chỉ 60 ảnh test, 20 ảnh/lớp; một lỗi thay đổi recall lớp 5 điểm phần trăm. Khoảng tin cậy giả định các ảnh độc lập; kiểm tra cùng vật thể/nguồn chụp trước khi suy rộng.

## Kết luận thực hành
Ưu tiên thu thập thêm ảnh độc lập cho lớp có recall thấp và các điều kiện hay sai. Tách theo vật thể/phiên chụp để tránh rò rỉ. Nếu thay đổi mô hình sau báo cáo này, đánh giá cuối cần một tập test mới, không dùng lại test để chọn tham số. Bộ dữ liệu nhỏ phù hợp thực hành, chưa đủ kết luận hệ thống dùng ngoài thực tế.
