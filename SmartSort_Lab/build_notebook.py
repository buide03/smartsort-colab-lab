"""Build a Colab notebook from the readable cell source; prepare the split ZIP."""
import argparse
import json
import random
import zipfile
from pathlib import Path
import nbformat

HERE = Path(__file__).resolve().parent
source = (HERE / 'lab_source.py').read_text(encoding='utf-8')
cells = []
for block in source.split('# %%')[1:]:
    header, _, body = block.partition('\n')
    if '[markdown]' in header:
        text = '\n'.join(line[2:] if line.startswith('# ') else '' if line == '#' else line
                         for line in body.rstrip().splitlines())
        cells.append(nbformat.v4.new_markdown_cell(text))
    else:
        compile(body, '<notebook-cell>', 'exec')
        cells.append(nbformat.v4.new_code_cell(body.strip()))
nb = nbformat.v4.new_notebook(cells=cells, metadata={
    'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
    'language_info': {'name': 'python', 'version': '3.12'},
    'colab': {'name': 'SmartSort_Colab_Lab.ipynb', 'provenance': []},
    'accelerator': 'GPU'})
nbformat.validate(nb)
nbformat.write(nb, HERE / 'SmartSort_Colab_Lab.ipynb')

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--zip', type=Path, default=HERE / 'SmartSort_Dataset_Original.zip',
                    help='Original SmartSort dataset ZIP')
original = parser.parse_args().zip
with zipfile.ZipFile(original) as zin:
    manifest = json.loads(zin.read('SmartSortPNG/manifest.json'))
    records = sorted(manifest, key=lambda r: r['file'])
    rng = random.Random(42)
    validation_files = set()
    for c in ['metal', 'paper', 'plastic']:
        candidates = [r['file'] for r in records if r['file'].startswith(f'train/{c}/')]
        rng.shuffle(candidates)
        validation_files.update(candidates[:8])
    prepared = []
    with zipfile.ZipFile(HERE / 'SmartSort_Data_Split.zip', 'w', zipfile.ZIP_DEFLATED) as zout:
        for r in manifest:
            dest = r['file'].replace('train/', 'validation/', 1) if r['file'] in validation_files else r['file']
            zout.writestr('SmartSortPNG/' + dest, zin.read('SmartSortPNG/' + r['file']))
            prepared.append(dict(r, file=dest))
        zout.writestr('SmartSortPNG/manifest.json', json.dumps(prepared, ensure_ascii=False, indent=2))
        zout.writestr('SmartSortPNG/LICENSE.txt', zin.read('SmartSortPNG/LICENSE.txt'))
print(f'Built notebook: {len(cells)} cells; prepared split: 96 train / 24 validation / 60 test / 15 outside')
