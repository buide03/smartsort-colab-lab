"""Portable Colab trainer: train-only ZIP -> ONNX backbone + JSON epoch heads."""
import tempfile
if __name__!='__main__':
    from .train_colab import *


def train_browser_package(package_path, result_path='SmartSort_Browser_Models.zip', require_cuda=True):
    # train_package, torch, np, nn, efficientnet_b0 are provided by train_colab.py.
    import onnx
    import onnxruntime as ort
    with tempfile.TemporaryDirectory(prefix='smartsort-browser-') as temporary:
        raw_path = str(Path(temporary)/'raw.zip')
        train_package(package_path,raw_path,require_cuda=require_cuda)
        with zipfile.ZipFile(raw_path) as raw:
            bundle=json.loads(raw.read('bundle.json'))
            model=efficientnet_b0(weights=None).cpu().eval()
            with np.load(io.BytesIO(raw.read('backbone.npz')),allow_pickle=False) as state:
                model.features.load_state_dict({key:torch.from_numpy(state[key].copy()) for key in state.files})
            backbone=nn.Sequential(model.features,model.avgpool,nn.Flatten(1)).eval()
            onnx_path=str(Path(temporary)/'backbone.onnx')
            torch.onnx.export(backbone,torch.zeros(1,3,224,224),onnx_path,
                              input_names=['image'],output_names=['features'],opset_version=17,
                              dynamo=False,external_data=False)
            onnx.checker.check_model(onnx.load(onnx_path))
            # Verify converted features against PyTorch before sending to students.
            rng=np.random.default_rng(42)
            sample=rng.normal(size=(1,3,224,224)).astype(np.float32)
            with torch.inference_mode():reference=backbone(torch.from_numpy(sample)).numpy()
            runtime=ort.InferenceSession(onnx_path,providers=['CPUExecutionProvider'])
            actual=runtime.run(None,{'image':sample})[0]
            np.testing.assert_allclose(actual,reference,rtol=1e-3,atol=1e-4)
            bundle['kind']='smartsort_browser_models'
            bundle['format']='onnx_features_json_heads_v1'
            bundle['onnx_max_abs_error']=float(np.abs(actual-reference).max())
            bundle['preprocessing']['resize']='pillow_bicubic_v1'
            with zipfile.ZipFile(result_path,'w',zipfile.ZIP_DEFLATED) as output:
                output.write(onnx_path,'backbone.onnx')
                for candidate in bundle['candidates']:
                    for checkpoint in candidate['checkpoints']:
                        old=checkpoint['file']
                        checkpoint['file']=old.replace('.npz','.json')
                        with np.load(io.BytesIO(raw.read(old)),allow_pickle=False) as state:
                            head={'weight':state['1.weight'].tolist(),'bias':state['1.bias'].tolist()}
                        output.writestr(checkpoint['file'],json.dumps(head,separators=(',',':'),allow_nan=False))
                output.writestr('bundle.json',json.dumps(bundle,ensure_ascii=False,allow_nan=False))
    print('Đã xuất',result_path,'— nhập vào web Browser Lab, chưa chạy validation/test.',flush=True)
    return str(Path(result_path).resolve())


if __name__=='__main__':
    from train_colab import *
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package')
    parser.add_argument('--output',default='SmartSort_Browser_Models.zip')
    parser.add_argument('--allow-cpu',action='store_true')
    args=parser.parse_args()
    train_browser_package(args.package,args.output,require_cuda=not args.allow_cpu)
