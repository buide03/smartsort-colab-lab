"""Serve the Render static edition locally. Open http://127.0.0.1:8001."""
import argparse
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port',type=int,default=8001)
args=parser.parse_args()
directory=Path(__file__).resolve().parent/'static_site'
class StaticHandler(SimpleHTTPRequestHandler):
    # Windows registry can map .mjs to text/plain, which browsers reject as modules.
    extensions_map={**SimpleHTTPRequestHandler.extensions_map,'.mjs':'application/javascript','.wasm':'application/wasm'}
    def do_GET(self):
        if self.path=='/smartsort-status':
            marker=directory.parent/'student-version.json'
            version=json.loads(marker.read_text(encoding='utf-8'))['version'] if marker.exists() else 'source'
            data=json.dumps({'application':'smartsort-browser-lab','version':version}).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

handler=partial(StaticHandler,directory=str(directory))
with ThreadingHTTPServer(('127.0.0.1',args.port),handler) as server:
    print(f'Browser Lab: http://127.0.0.1:{args.port}',flush=True)
    server.serve_forever()
