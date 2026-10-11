"""Package the local teaching application without user sessions or dependencies."""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
files = [ROOT/n for n in ['requirements.txt','requirements-server.txt','run_local.py','start_local.ps1','build_local_package.py',
                        'serve.py','Dockerfile','.dockerignore','compose.yaml','railway.json']]
files += [p for directory in ['smartsort_app','docs','tests','colab'] for p in (ROOT/directory).rglob('*')
          if p.is_file() and '__pycache__' not in p.parts and 'runtime' not in p.parts and p.suffix != '.pyc']
with zipfile.ZipFile(ROOT/'SmartSort_Local_App.zip','w',zipfile.ZIP_DEFLATED) as z:
    readme=(ROOT/'README.md').read_text(encoding='utf-8').split('## Notebook Colab phiên bản trước')[0]
    z.writestr('SmartSort_Local_App/README.md',readme)
    for file in files:
        z.write(file, 'SmartSort_Local_App/'+file.relative_to(ROOT).as_posix())
with zipfile.ZipFile(ROOT/'SmartSort_Local_App.zip') as z:
    assert z.testzip() is None
print('Built SmartSort_Local_App.zip; extract, install requirements, run python run_local.py.')
