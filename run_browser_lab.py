"""Serve the Render static edition locally. Open http://127.0.0.1:8001."""
import argparse
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

handler=partial(StaticHandler,directory=str(directory))
with ThreadingHTTPServer(('127.0.0.1',args.port),handler) as server:
    print(f'Browser Lab: http://127.0.0.1:{args.port}',flush=True)
    server.serve_forever()
