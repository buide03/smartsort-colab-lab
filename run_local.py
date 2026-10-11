"""Start SmartSort on localhost. Usage: python run_local.py [--port 8000]."""
import argparse
import importlib.util
import socket
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', type=int, default=8000)
args = parser.parse_args()
missing = [m for m in ['fastapi','uvicorn','multipart','torch','torchvision','sklearn','PIL'] if importlib.util.find_spec(m) is None]
if missing:
    print('Thiếu thư viện: '+', '.join(missing))
    print('Chạy: python -m pip install -r requirements.txt')
    sys.exit(1)
with socket.socket() as sock:
    if sock.connect_ex(('127.0.0.1',args.port)) == 0:
        print(f'Cổng {args.port} đang được dùng. Mở http://127.0.0.1:{args.port} hoặc chọn --port 8001.')
        sys.exit(1)
print(f'SmartSort: http://127.0.0.1:{args.port}')
print('Nhấn Ctrl+C để dừng. Dữ liệu và kết quả được lưu trong .smartsort/.')
import uvicorn
uvicorn.run('smartsort_app.server:app', host='127.0.0.1', port=args.port, log_level='warning')
