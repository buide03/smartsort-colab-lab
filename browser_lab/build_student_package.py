"""Make a small immutable package for the one-command Windows student launcher."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
files={p.relative_to(ROOT).as_posix():p.read_bytes() for p in (ROOT/'static_site').rglob('*') if p.is_file()}
for name in ['run_browser_lab.py','start-student.ps1']:files[name]=(ROOT/name).read_bytes()
files={name:data if name.endswith('.wasm') else data.replace(b'\r\n',b'\n') for name,data in files.items()}
version=hashlib.sha256(json.dumps({name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())},sort_keys=True).encode()).hexdigest()[:16]
files['student-version.json']=json.dumps({'version':version}).encode()
directory=ROOT/'student'
directory.mkdir(exist_ok=True)
archive=directory/f'SmartSort_Browser_{version}.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as output:
    for name,data in sorted(files.items()):
        info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED
        output.writestr(info,data)
manifest={'version':version,'bundle':archive.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
(directory/'release.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
with zipfile.ZipFile(archive) as check:assert check.testzip() is None
print('Built student package:',archive.name,archive.stat().st_size,'bytes')
