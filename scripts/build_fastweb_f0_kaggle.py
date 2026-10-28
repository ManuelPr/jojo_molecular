"""Package the fixed F0 notebook with the explicitly audited research mounts.

Prediction code is unchanged. Building does not upload or submit anything.
"""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = '3b05fe5620f0bfe3acb319c782761acb61c61d283d8835b415a4d671cd841aa4'


def build():
    source = ROOT / 'artifacts/cluster/f0-gu-v492-latest-audit/casmi26-v492-dg-v19.ipynb'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == SOURCE_SHA256
    notebook = json.loads(source.read_text())
    for cell in notebook['cells']:
        if cell['cell_type'] == 'code':
            ast.parse(''.join(cell['source']))
            cell.update(outputs=[], execution_count=None)
    assets = json.loads((ROOT / 'configs/fastweb_research_assets_2026-10-22.json').read_text())
    mounts = [f"{a['source']}/{a['version']}" for a in assets['assets']
              if a['kind'] == 'dataset' and not a['source'].startswith('franciscoangulo/')]
    metadata = json.loads((source.parent / 'kernel-metadata.json').read_text())
    metadata.pop('id_no', None)  # Never address the upstream author's notebook.
    metadata.update(id='mperni/casmi26-f0-gu-v492-research-control',
                    title='CASMI26 F0 Gu V492 Research Control', is_private=True,
                    code_file='f0.ipynb', dataset_sources=mounts,
                    enable_internet=False, enable_gpu=True)
    bundle = ROOT / 'kaggle/fastweb_f0_bundle'
    bundle.mkdir(parents=True, exist_ok=True)
    target = bundle / 'f0.ipynb'
    target.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + '\n')
    (bundle / 'kernel-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    manifest = dict(source_sha256=SOURCE_SHA256,
                    notebook_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                    changed_prediction_cells=0, dataset_sources=mounts,
                    historical_mount_versions_certified=False,
                    limitation='Research snapshot; historical public 0.464 is not a reproduced score.',
                    visible_run='Original 12-query smoke; official rerun processes the whole hidden test.',
                    user_authorization='2026-10-23: farei la submission a priori')
    (bundle / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    build()
