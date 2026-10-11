"""Package the local teaching application without user sessions or dependencies."""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
files = [ROOT/n for n in ['requirements.txt','requirements-server.txt','run_local.py','start_local.ps1','build_local_package.py',
                        'run_browser_lab.py','start-student.ps1','render.yaml','serve.py','Dockerfile','.dockerignore','.env.example','compose.yaml','railway.json']]
files += [p for directory in ['smartsort_app','docs','tests','colab','deploy','browser_lab','static_site'] for p in (ROOT/directory).rglob('*')
          if p.is_file() and not {'__pycache__','runtime','data','backups'}.intersection(p.relative_to(ROOT).parts)
          and p.suffix != '.pyc' and (not p.name.startswith('.env') or p.name=='.env.example')]
with zipfile.ZipFile(ROOT/'SmartSort_Local_App.zip','w',zipfile.ZIP_DEFLATED) as z:
    readme=(ROOT/'README.md').read_text(encoding='utf-8').split('## Notebook Colab phiên bản trước')[0]
    z.writestr('SmartSort_Local_App/README.md',readme)
    for file in files:
        z.write(file, 'SmartSort_Local_App/'+file.relative_to(ROOT).as_posix())
with zipfile.ZipFile(ROOT/'SmartSort_Local_App.zip') as z:
    assert z.testzip() is None
print('Built SmartSort_Local_App.zip; Browser Lab: python run_browser_lab.py (port 8001). Backend edition: python run_local.py.')
