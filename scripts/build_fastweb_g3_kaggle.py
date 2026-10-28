"""Package authorized experimental G3 deployment without rerunning experiments."""
import ast
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
MODEL_DATASET = 'mperni/casmi26-g3-fusion-research-models'
KERNEL = 'mperni/casmi26-f0-g3-lightgbm-experiment'


def build():
    source = ROOT/'artifacts/cluster/f0-gu-v492-latest-audit/casmi26-v492-dg-v19.ipynb'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == '3b05fe5620f0bfe3acb319c782761acb61c61d283d8835b415a4d671cd841aa4'
    models = ROOT/'artifacts/cluster/g3-dev200-2545/fusion'
    assets = ROOT/'kaggle/assets/g3_fusion_v1'
    assets.mkdir(parents=True, exist_ok=True)
    for fold in range(5):
        for name in [f'lightgbm-fold{fold}.txt', f'preprocessing-fold{fold}.json']:
            shutil.copyfile(models/name, assets/name)
    shutil.copyfile(ROOT/'kaggle/g3_fusion_overlay.py', assets/'g3_fusion_overlay.py')
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(assets.iterdir())
             if p.name.startswith(('lightgbm-', 'preprocessing-', 'g3_fusion_overlay'))}
    manifest = dict(files_sha256=files, ensemble='Arithmetic mean of five LightGBM fold scores',
                    training='200 public-panel reference-disjoint queries; upstream pretrained exclusions unverified',
                    experimental=True, user_authorization='2026-10-23: integriamolo gia nella submission',
                    source_results_sha256=hashlib.sha256((models/'results.json').read_bytes()).hexdigest())
    (assets/'g3_fusion_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    (assets/'dataset-metadata.json').write_text(json.dumps(dict(
        id=MODEL_DATASET, title='CASMI26 G3 Fusion Research Models',
        licenses=[dict(name='other')], description='Experimental fusion models trained from public CASMI panel evidence. Five fixed LightGBM folds and preprocessing only; no spectrum data or validation labels. Private research artifact.'), indent=2)+'\n')
    nb = json.loads(source.read_text())
    needle = "                order = np.argsort(-score, kind='stable')"
    code = ''.join(nb['cells'][38]['source'])
    assert code.count(needle) == 1
    hook = "                _g3_capture(mid,C,np.concatenate([X,F],1),list(FEATURES)+list(names),score,lib_max,POOL_POP)\n"
    nb['cells'][38]['source'] = (code.replace(needle, hook+needle)).splitlines(keepends=True)
    code = ''.join(nb['cells'][40]['source'])
    needle = "N1_ARM = 'N1A_D'"
    assert code.count(needle) == 1
    nb['cells'][40]['source'] = code.replace(needle, "G3_GL_REAL_SCORES = {k:dict(v) for k,v in GL_SCORES.items()}\n"+needle).splitlines(keepends=True)
    loader = '''from pathlib import Path
import hashlib, json
_g3_hits = sorted(Path('/kaggle/input').rglob('g3_fusion_manifest.json'), key=lambda p: len(str(p)))
assert len(_g3_hits) == 1, 'Attach the pinned G3 model dataset exactly once'
G3_ASSET_DIR = _g3_hits[0].parent
_g3_manifest = json.loads(_g3_hits[0].read_text())
assert hashlib.sha256((G3_ASSET_DIR/'g3_fusion_overlay.py').read_bytes()).hexdigest() == _g3_manifest['files_sha256']['g3_fusion_overlay.py']
exec(compile((G3_ASSET_DIR/'g3_fusion_overlay.py').read_text(), 'g3_fusion_overlay.py', 'exec'), globals())
'''
    def cell(text):
        ast.parse(text)
        return dict(cell_type='code', metadata={}, execution_count=None, outputs=[], source=text.splitlines(keepends=True))
    nb['cells'].insert(38, cell(loader))
    nb['cells'].append(cell("G3_RECEIPT = _g3_run(globals(), G3_ASSET_DIR)\n"))
    for c in nb['cells']:
        if c['cell_type'] == 'code':
            ast.parse(''.join(c['source']))
            c.update(outputs=[], execution_count=None)
    metadata = json.loads((ROOT/'kaggle/fastweb_f0_bundle/kernel-metadata.json').read_text())
    metadata.update(id=KERNEL, title='CASMI26 F0 G3 LightGBM Experiment', code_file='g3.ipynb')
    metadata['dataset_sources'] += [MODEL_DATASET+'/1']
    bundle = ROOT/'kaggle/fastweb_g3_bundle'
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle/'g3.ipynb').write_text(json.dumps(nb, ensure_ascii=False, indent=1)+'\n')
    (bundle/'kernel-metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
    build_manifest = dict(kernel=KERNEL, model_dataset=MODEL_DATASET+'/1',
                          notebook_sha256=hashlib.sha256((bundle/'g3.ipynb').read_bytes()).hexdigest(),
                          model_manifest_sha256=hashlib.sha256((assets/'g3_fusion_manifest.json').read_bytes()).hexdigest(),
                          changed_source_cells=[38,40], inference='F0 final candidate pool, five-fold mean G3 ordering; replaces final heuristic and rank2 ordering.',
                          experimental=True, source_F0_submission=57552927)
    (bundle/'build-manifest.json').write_text(json.dumps(build_manifest, indent=2)+'\n')
    print(json.dumps(build_manifest, indent=2))


if __name__ == '__main__':
    build()
