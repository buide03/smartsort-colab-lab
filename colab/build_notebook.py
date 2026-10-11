from pathlib import Path
import nbformat

HERE = Path(__file__).resolve().parent
source = (HERE/'train_colab.py').read_text(encoding='utf-8').split("\nif __name__ == '__main__':")[0]
nb = nbformat.v4.new_notebook(cells=[
    nbformat.v4.new_markdown_cell('''# SmartSort: train trên Colab, validation/test trên web

1. Trên web: gán nhãn, chia dữ liệu và bấm **Tải gói train cho Colab**.
2. Trên Colab: **Runtime → Change runtime type → T4 GPU**.
3. Chạy các ô dưới đây và upload `SmartSort_Colab_Train.zip` khi được hỏi.
4. Train xong, tải `SmartSort_Colab_Models.zip` rồi nhập vào **đúng phiên** trên web.
5. Học sinh bấm **Chạy validation**, so sánh cấu hình/epoch, chốt mô hình rồi chạy test.

Gói chỉ có train. Colab lưu classifier ở mỗi epoch; không dùng validation để tự chọn checkpoint, không có early stopping bằng validation. Web chọn epoch tốt nhất bằng validation sau khi nhập gói. Backbone đóng băng, classifier ba lớp; augmentation chỉ từ train. Cần mạng để tải trọng số ImageNet lần đầu. Runtime Colab/GPU cần người dùng chọn và cấp phát; notebook không tự đặt lịch hay duy trì kết nối với web.'''),
    nbformat.v4.new_code_cell("import torch\nassert torch.cuda.is_available(), 'Hãy chọn T4 GPU trong Runtime trước khi train.'\nprint(torch.cuda.get_device_name(0))"),
    nbformat.v4.new_code_cell(source),
    nbformat.v4.new_code_cell("from google.colab import files\nuploaded = files.upload()\npackages = [p for p in uploaded if p.lower().endswith('.zip')]\nassert len(packages) == 1, 'Upload đúng một gói train xuất từ web.'\npackage_path = packages[0]\ndel uploaded"),
    nbformat.v4.new_code_cell("result_path = train_package(package_path, require_cuda=True)"),
    nbformat.v4.new_code_cell("files.download(result_path)")
],metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
            'language_info':{'name':'python'},'accelerator':'GPU',
            'colab':{'name':'SmartSort_Train_Colab.ipynb','provenance':[]}})
nbformat.validate(nb)
nbformat.write(nb,HERE/'SmartSort_Train_Colab.ipynb')
print('Built Colab training notebook')
