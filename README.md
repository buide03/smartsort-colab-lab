# SmartSort — Lab phân loại nhựa, giấy, kim loại trên Google Colab

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/buide03/smartsort-colab-lab/blob/main/SmartSort_Lab/SmartSort_Colab_Lab.ipynb)

Lab dùng EfficientNet-B0 pretrained ImageNet, huấn luyện classifier ba lớp, chọn checkpoint bằng validation rồi đánh giá test. Có fine-tuning tùy chọn, early stopping, phân tích lỗi và xuất kết quả.

## Chạy trên Google Colab

1. Tải [notebook](SmartSort_Lab/SmartSort_Colab_Lab.ipynb) và [ZIP dữ liệu chia sẵn](SmartSort_Lab/SmartSort_Data_Split.zip).
2. Mở https://colab.research.google.com/ → **File → Upload notebook**. Repo riêng tư có thể yêu cầu cấp quyền GitHub khi dùng nút Colab; tải/upload notebook là cách thay thế.
3. Chọn **Runtime → Change runtime type → T4 GPU**, rồi **Run all**.
4. Khi được hỏi, upload `SmartSort_Data_Split.zip`. Cũng có thể dùng [ZIP gốc](SmartSort_Lab/SmartSort_Dataset_Original.zip); notebook tự chia validation theo cùng seed.
5. Kết thúc, tải `SmartSort_Results.zip` chứa báo cáo, biểu đồ, dự đoán và checkpoint.

## Dữ liệu và kết quả chạy thử

| Tập | Số ảnh |
|---|---:|
| Train | 96 |
| Validation | 24 |
| Test ba lớp | 60 |
| Test ngoài lớp: thủy tinh, carton | 15 |

Lần chạy CPU đã đạt validation accuracy 100%, test accuracy 78.33%, macro-F1 test 0.769. Test basic đạt 93.33%, variation đạt 63.33%. Đây là dữ liệu nhỏ phục vụ thực hành; chi tiết giới hạn và các yếu tố đánh giá ở [báo cáo kiểm thử](SmartSort_Lab/KET_QUA_KIEM_THU.md).

## Nội dung repo

- [Hướng dẫn lab](SmartSort_Lab/README.md).
- [Notebook](SmartSort_Lab/SmartSort_Colab_Lab.ipynb), [mã nguồn các cell](SmartSort_Lab/lab_source.py), [script tạo notebook và chia dữ liệu](SmartSort_Lab/build_notebook.py).
- ZIP dữ liệu gốc, ZIP chia train/validation/test và [gói lab đầy đủ](SmartSort_Lab/SmartSort_Lab_Colab_Full.zip).
- [Kết quả chạy thử đầy đủ](SmartSort_Lab/verified_run/SmartSort_Results.zip), [checkpoint](SmartSort_Lab/verified_run/outputs/best_model.pt), [báo cáo tự động](SmartSort_Lab/verified_run/outputs/REPORT.md), CSV và biểu đồ trong `SmartSort_Lab/verified_run/outputs/`.

## Chạy trên máy tính

```powershell
python -m pip install -r requirements.txt
$env:SMARTSORT_ZIP = (Resolve-Path 'SmartSort_Lab/SmartSort_Data_Split.zip').Path
python -X utf8 SmartSort_Lab/lab_source.py
```

Trên Linux/macOS:

```bash
python -m pip install -r requirements.txt
SMARTSORT_ZIP=SmartSort_Lab/SmartSort_Data_Split.zip python SmartSort_Lab/lab_source.py
```

Kết quả tại `local_runtime/outputs/`. Để tạo lại notebook và ZIP chia sẵn: `python SmartSort_Lab/build_notebook.py`; có thể chỉ định ZIP khác bằng `--zip PATH`.

Nguồn dữ liệu: TrashNet, Gary Thung; giấy phép MIT của bộ dữ liệu được giữ trong các ZIP. Tài liệu mô hình: [Torchvision EfficientNet-B0](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.efficientnet_b0.html).
