# Tự kiểm tra và che thông tin cá nhân trước khi dùng ảnh

Ở bước **Chuẩn bị & gán nhãn** và mục **Thử một ảnh mới**, chọn ảnh sẽ mở hộp kiểm tra PII trước khi ảnh được lưu hoặc gửi để dự đoán. Ảnh trong ZIP cũng được kiểm tra từng ảnh. Người học tự phát hiện và che PII; không có bộ quét hoặc OCR tự động.

1. Quan sát toàn bộ ảnh để tìm khuôn mặt, họ tên, số điện thoại, địa chỉ, mã học sinh, biển số, mã QR và thông tin trên giấy tờ. Phóng to bằng trình duyệt nếu cần xem chi tiết.
2. Kéo trên ảnh để phủ ô đen lên toàn bộ vùng chứa thông tin. Có thể che nhiều vùng; **Hoàn tác vùng cuối** nếu khoanh nhầm. Chừa phần vật liệu cần phân loại.
3. Kiểm tra lại bản đã che, đánh dấu xác nhận đã tự kiểm tra toàn bộ ảnh và che hết thông tin cá nhân nhìn thấy, rồi chọn **Dùng ảnh đã kiểm tra**. Ảnh không có PII vẫn phải được xem và xác nhận. Thay đổi vùng che sẽ hủy xác nhận cũ.
4. Chọn **Bỏ ảnh này** nếu không thể che mà vẫn giữ ý nghĩa ảnh. **Hủy lượt tải** bỏ toàn bộ lượt đang kiểm tra, kể cả ảnh đã duyệt trong lượt đó.

Việc che diễn ra ngay trong trình duyệt trên máy học sinh. Ảnh gốc không được gửi đi trong bước này. Luồng tải ảnh chỉ lưu/gửi bản PNG đã duyệt, dùng tên ngẫu nhiên và không kèm EXIF/metadata của ảnh gốc. Ảnh xem trước khi dự đoán cũng là bản đã duyệt. File gốc trên máy học sinh không bị sửa.

Sau khi duyệt, tiếp tục gán nhãn và chia tập như hiện tại. Bước huấn luyện xuất **SmartSort_Colab_Train.zip** từ những ảnh đã lưu sau khi che; mở notebook Colab và tải gói này lên. Không tải ảnh gốc/ZIP gốc lên Colab. Gói vẫn chỉ chứa train, không chứa validation/test.

Người học chịu trách nhiệm kiểm tra và che đầy đủ; công cụ không bảo đảm đã loại hết PII. Ảnh đã lưu trong phiên cũ hoặc bản sao lưu cũ chưa được bước này xử lý; tạo phiên mới và nhập lại ảnh qua bước kiểm tra trước khi chia sẻ hoặc huấn luyện.

Câu hỏi thảo luận: Vì sao cần kiểm tra và che thông tin cá nhân trước khi tải lên? Nếu che quá nhiều vùng khiến không còn nhận ra vật liệu, nên giữ hay bỏ ảnh?

Áp dụng cho giao diện local/server và Browser Lab. Quy trình chia tập, huấn luyện, validation, chốt mô hình và đánh giá test giữ nguyên. Chạy `python browser_lab/build_static.py` để tạo lại bản deploy. Website đang deploy cần cập nhật mã để có thay đổi này.

Kiểm thử: mở Browser Lab bằng `python run_browser_lab.py --port 8017`, rồi chạy `python tests/verify_privacy_review.py` và `python tests/verify_privacy_export.py` (cần Pillow và Playwright; Windows dùng Edge). Bài kiểm tra xác minh che đúng pixel, xác nhận của người học, hủy thao tác, không gửi ảnh/chữ ra ngoài trong bước kiểm tra và ảnh đã che trong ZIP train.
