# Xem trực quan kết quả nhận diện tập test

Phần **Detection · Nhận diện vật liệu trên tập test** nằm ở bước 5, xuất hiện sau khi chốt model và chạy **Mở test & thu kết quả**. Có trong cả Browser Lab trên Render và giao diện backend local.

1. Xem tổng số ảnh đúng/sai của từng vật liệu theo **nhãn thật**. Thanh màu xanh là ảnh đúng, màu cam là ảnh sai.
2. Lọc **Nhãn thật** để xem Kim loại, Giấy hoặc Nhựa. Lọc **Kết quả** để xem ảnh đúng hoặc ảnh sai.
3. Sắp xếp theo độ tin cậy cao/thấp hoặc tên ảnh, tìm tên ảnh và chuyển trang để xem toàn bộ tập test.
4. Mỗi ảnh hiển thị nhãn thật, nhãn model dự đoán, độ tin cậy của lớp dự đoán và xác suất của cả ba lớp. Bấm ảnh để phóng lớn và xem chi tiết.
5. Tải ZIP/CSV kết quả ở cột bên phải để nộp bài; các số liệu của phần trực quan lấy từ kết quả test đã lưu.

Model EfficientNet-B0 hiện tại **phân loại toàn bộ ảnh**, không tạo bounding box hoặc đếm nhiều vật thể. Tên mục Detection chỉ phần xem kết quả nhận diện vật liệu; để xác định vị trí từng vật thể cần dữ liệu gán nhãn khung và một model phát hiện vật thể riêng.

## Câu hỏi cho học sinh

- Lớp nào có nhiều ảnh bị nhận sai nhất? Các ảnh đó bị nhầm sang lớp nào?
- Ảnh sai có độ tin cậy cao có nền, góc chụp, ánh sáng hoặc hình dạng gì đáng chú ý?
- Ảnh đúng có độ tin cậy thấp có điểm gì khác với ảnh đúng có độ tin cậy cao?
- Cần thu thập thêm ảnh và kiểm tra nhãn như thế nào cho lần thí nghiệm tiếp theo?

Độ tin cậy không bảo đảm dự đoán đúng. Lọc và xem ảnh không chạy lại model, không điều chỉnh cấu hình và không thay đổi điểm test. Giữ nguyên kết quả cuối của phiên này; nếu cải tiến, làm thí nghiệm mới với tập test độc lập.
