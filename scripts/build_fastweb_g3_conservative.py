"""Package the user-authorized F0 top1-preserving G3 tail experiment."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build():
    original = ROOT/'kaggle/fastweb_g3_bundle'
    bundle = ROOT/'kaggle/fastweb_g3_conservative_bundle'
    bundle.mkdir(parents=True, exist_ok=True)
    notebook = json.loads((original/'g3.ipynb').read_text())
    overlay = (ROOT/'kaggle/g3_conservative_overlay.py').read_text()
    ast.parse(overlay)
    last = notebook['cells'][-1]
    assert ''.join(last['source']).strip() == 'G3_RECEIPT = _g3_run(globals(), G3_ASSET_DIR)'
    last['source'] = (overlay+'\nG3_RECEIPT = _g3_run(globals(), G3_ASSET_DIR)\n').splitlines(keepends=True)
    for cell in notebook['cells']:
        if cell['cell_type'] == 'code':
            ast.parse(''.join(cell['source']))
            cell.update(outputs=[], execution_count=None)
    metadata = json.loads((original/'kernel-metadata.json').read_text())
    metadata.update(id='mperni/casmi26-f0-g3-conservative-tail', title='CASMI26 F0 G3 Conservative Tail')
    (bundle/'g3.ipynb').write_text(json.dumps(notebook, ensure_ascii=False, indent=1)+'\n')
    (bundle/'kernel-metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
    manifest = json.loads((original/'build-manifest.json').read_text())
    manifest.update(kernel=metadata['id'], notebook_sha256=hashlib.sha256((bundle/'g3.ipynb').read_bytes()).hexdigest(),
                    conservative_overlay_sha256=hashlib.sha256(overlay.encode()).hexdigest(),
                    inference='Preserve exact F0 top1 and top25 candidate set; reorder positions2-25 by saved G3 ensemble scores.',
                    user_authorization='2026-10-23: bho, falla')
    (bundle/'build-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    build()
