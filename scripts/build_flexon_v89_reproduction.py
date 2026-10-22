"""Build the pinned public recipe, changing only the visible smoke switch.

Does not execute upstream code locally or submit to the competition.
"""
import ast
import copy
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA = 'c43e870c92bd67b2f0c0245c1b4064cfb1c49a1cbc81ffac349bee4708ad55a1'
SOURCE_URL = 'https://www.kaggle.com/code/flexonafft/casmi26-public-baseline-adaptation-experiments?scriptVersionId=357683876'
IMAGE = 'gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461'
SWITCH = "IS_RERUN = bool(os.getenv('KAGGLE_IS_COMPETITION_RERUN')) or _sig != '654e030e4173780e945252b4a5adf70b'"


def build():
    source = ROOT / 'third_party/flexon_v89/upstream.ipynb'
    assert sha256(source.read_bytes()).hexdigest() == SOURCE_SHA
    original = json.loads(source.read_text(encoding='utf-8'))
    notebook = copy.deepcopy(original)
    assets = json.loads((ROOT / 'configs/flexon_v89_assets.json').read_text())
    expected = {d['sourceId'] for d in original['metadata']['kaggle']['dataSources'] if d['sourceType'] == 'datasetVersion'}
    assert {d['dataset_version_id'] for d in assets['datasets']} == expected
    assert assets['source_notebook_sha256'] == SOURCE_SHA
    cells = []
    for i, (old, new) in enumerate(zip(original['cells'], notebook['cells'])):
        code = ''.join(old['source'])
        if i == 11:
            assert code.count(SWITCH) == 1
            code = code.replace(SWITCH, 'IS_RERUN = True  # Reproduction: full visible rehearsal; prediction code unchanged.')
        else:
            assert code == ''.join(old['source'])
        ast.parse(code)
        new.update(source=code.splitlines(keepends=True), outputs=[], execution_count=None, metadata={})
        cells.append(dict(index=i, original_sha256=sha256(''.join(old['source']).encode()).hexdigest(),
                          reproduction_sha256=sha256(code.encode()).hexdigest(), changed=i == 11))
    observer = (ROOT / 'kaggle/flexon_v89_observer.py').read_text(encoding='utf-8')
    ast.parse(observer)
    notebook['cells'].append(dict(cell_type='code', execution_count=None, metadata={}, outputs=[], source=observer.splitlines(keepends=True)))
    notebook['metadata'] = {k: original['metadata'][k] for k in ('kernelspec', 'language_info')}
    notebook['metadata']['reproduction'] = dict(source_url=SOURCE_URL, source_sha256=SOURCE_SHA,
                                               change='Full visible run instead of 12-query smoke; read-only final observer.')
    bundle = ROOT / 'kaggle/flexon_v89_reproduction_bundle'
    bundle.mkdir(exist_ok=True)
    target = bundle / 'flexon_v89.ipynb'
    target.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    metadata = dict(id='mperni/casmi26-flexon-v89-faithful-reproduction', title='CASMI26 Flexon v89 Faithful Reproduction',
                    code_file=target.name, language='python', kernel_type='notebook', is_private=True,
                    enable_gpu=True, enable_internet=False, machine_shape='NvidiaTeslaT4',
                    docker_image=IMAGE, docker_image_pinning_type='original',
                    dataset_sources=[d['pinned_source'] for d in assets['datasets']],
                    competition_sources=['enveda-CASMI26-molecule-id-mass-spectra'],
                    kernel_sources=[], model_sources=[])
    (bundle / 'kernel-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    manifest = dict(source_url=SOURCE_URL, source_sha256=SOURCE_SHA,
                    notebook_sha256=sha256(target.read_bytes()).hexdigest(), source_cells=cells,
                    appended_observer_sha256=sha256(observer.encode()).hexdigest(),
                    historical_docker_image_version_id=original['metadata']['kaggle']['dockerImageVersionId'],
                    requested_docker_image=IMAGE,
                    docker_digest_provenance='Pulled current public kernel metadata; historical image ID-to-digest equivalence not independently established.',
                    assets=assets['datasets'], official_submission_performed=False)
    (bundle / 'build_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'bundle': str(bundle), 'notebook_sha256': manifest['notebook_sha256'],
                      'unchanged_source_cells': 34, 'operationally_changed_cell': 11,
                      'exact_dataset_versions': len(expected)}, indent=2))
    return manifest


if __name__ == '__main__':
    build()
