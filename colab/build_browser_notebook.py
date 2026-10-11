"""Generate a self-contained Colab notebook for the static browser edition."""
from pathlib import Path
import nbformat

HERE=Path(__file__).resolve().parent
source=(HERE/'train_colab.py').read_text(encoding='utf-8').split("\nif __name__ == '__main__':")[0]
source+='\n'+(HERE/'train_browser_colab.py').read_text(encoding='utf-8').split("\nif __name__=='__main__':")[0]
nb=nbformat.v4.new_notebook(cells=[
    nbformat.v4.new_markdown_cell('''# SmartSort Browser Lab — Train GPU, đánh giá trong trình duyệt

1. Trên web Render: tải ảnh, tự gán nhãn, chia train/validation/test và xuất `SmartSort_Colab_Train.zip`.
2. Chọn **Runtime → Change runtime type → T4 GPU** rồi chạy từng ô dưới đây.
3. Upload gói chỉ train. Colab train classifier của EfficientNet-B0 với backbone ImageNet đóng băng, lưu tất cả epoch/cấu hình.
4. Tải `SmartSort_Browser_Models.zip`, quay lại **đúng phiên trên cùng trình duyệt**, nhập model.
5. Bấm validation trong trình duyệt, so sánh/chốt cấu hình rồi mới mở test và xuất báo cáo.

Colab không nhận validation/test và không tự chọn epoch. Web chọn epoch bằng validation. Backbone được chuyển thành ONNX và kiểm tra đặc trưng so với PyTorch trước khi xuất. Mỗi gói chứa backbone một lần và classifier mỗi epoch. Máy học sinh chạy suy luận CPU trong trình duyệt; train vẫn dùng GPU Colab. Sao lưu ZIP phiên trước khi đổi máy hoặc xóa dữ liệu trình duyệt. Không dùng notebook Docker cũ cho bản Browser Lab.'''),
    nbformat.v4.new_code_cell("import torch\nassert torch.cuda.is_available(), 'Chọn T4 GPU trong Runtime trước khi train.'\nprint(torch.cuda.get_device_name(0))\n%pip -q install 'onnx>=1.17,<2' 'onnxruntime>=1.20,<2'"),
    nbformat.v4.new_code_cell(source),
    nbformat.v4.new_code_cell("from google.colab import files\nuploaded=files.upload()\npackages=[p for p in uploaded if p.lower().endswith('.zip')]\nassert len(packages)==1, 'Upload đúng một gói train.'\npackage_path=packages[0]\ndel uploaded"),
    nbformat.v4.new_code_cell("result_path=train_browser_package(package_path,require_cuda=True)"),
    nbformat.v4.new_code_cell("files.download(result_path)")
],metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python'},'accelerator':'GPU','colab':{'name':'SmartSort_Browser_Colab.ipynb','provenance':[]}})
nbformat.validate(nb)
nbformat.write(nb,HERE/'SmartSort_Browser_Colab.ipynb')
print('Built browser Colab notebook')
