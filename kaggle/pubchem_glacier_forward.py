"""Score an immutable feature cache on GPU, without recomputing retrieval."""
import glob
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import time
from functools import lru_cache
import numpy as np

started = time.time()


def find(name):
    paths = glob.glob('/kaggle/input/**/' + name, recursive=True)
    if len(paths) != 1:
        raise RuntimeError(f'Expected one {name}, found {paths}')
    return Path(paths[0])


wheel = find('rdkit-2026.3.3-cp313-cp313-manylinux_2_28_x86_64.whl')
if streamed_hash(wheel) != SCORER_WHEEL_SHA256:
    raise RuntimeError('Scorer wheel drift')
subprocess.run([__import__('sys').executable, '-m', 'pip', 'install', '--no-index', '--no-deps', str(wheel)], check=True)
from rdkit import Chem, rdBase, RDLogger
from rdkit.Chem.MolStandardize import rdMolStandardize
RDLogger.DisableLog('rdApp.*')
if rdBase.rdkitVersion != '2026.03.3':
    raise RuntimeError('Scorer version mismatch')

cache_manifest = find('feature_manifest.json')
if streamed_hash(cache_manifest) != CACHE_MANIFEST_SHA256:
    raise RuntimeError('Mounted feature cache is not the reviewed version')
manifest = json.loads(cache_manifest.read_text())
if manifest['configuration'] != EXPERIMENT or not manifest['complete']:
    raise RuntimeError('Feature configuration mismatch')
root = cache_manifest.parent
for name, key in [('forward_input.json', 'forward_input_sha256'), ('experiment_candidates.json', 'candidates_sha256')]:
    if streamed_hash(root/name) != manifest[key]:
        raise RuntimeError('Feature cache checksum mismatch: ' + name)
records = json.loads((root/'experiment_candidates.json').read_text())
items = json.loads((root/'forward_input.json').read_text())
if len(records) != manifest['query_count']:
    raise RuntimeError('Feature query count mismatch')
pkg = find('PROVENANCE.json').parent
aux = find('auxiliary_manifest.json').parent
python, child_env = prepare_forward_environment(pkg, aux, '/kaggle/tmp/fwd_cached_site',
    provenance_hash=STACK_PROVENANCE_SHA256, auxiliary_hash=AUXILIARY_SHA256, device='cuda')
command = [python, str(pkg/'runner/fwd_runner.py'), str(pkg), 'batch', str(root/'forward_input.json'), 'forward_scores.json',
           '--models', 'glacier', '--stack', 'none', '--device', 'cuda', '--bs', str(EXPERIMENT['forward_batch_size']), '--budget', '7200']
print('[FORWARD] Starting', len(items), 'covered molecules; cached queries', len(records), flush=True)
result = subprocess.run(command, capture_output=True, text=True, env=child_env, timeout=7500)
Path('forward_run.log').write_text(result.stdout + '\n' + result.stderr)
meta_path = Path('forward_scores.json.meta.json')
if not meta_path.exists():
    raise RuntimeError('Forward runner produced no status report')
meta = json.loads(meta_path.read_text())
if result.returncode != 0 or meta['status'] != 'ok' or meta['errors'] or meta['items_done'] != len(items) or meta['device'] != 'cuda':
    raise RuntimeError('GLACIER incomplete or failed: ' + json.dumps(meta))
raw = json.loads(Path('forward_scores.json').read_text())
forward = {}
for item in items:
    scores = raw[item['id']]['glacier']
    if len(scores) != len(item['candidates']) or not np.isfinite(np.asarray(scores, float)).all():
        raise RuntimeError('Supported GLACIER prediction missing/nonfinite')
    forward[item['id']] = dict(zip(item['candidates'], scores))
report = evaluate(records, forward)
report.update(complete=True, forward_executed=True, feature_manifest=manifest, forward_meta=meta,
              configuration=EXPERIMENT, total_elapsed_seconds=time.time()-started,
              parent_rdkit=importlib.metadata.version('rdkit'),
              cache_manifest_sha256=CACHE_MANIFEST_SHA256,
              kernel_sha256=streamed_hash(__file__))
save_json('experiment_report.json', report)
print('[FORWARD] COMPLETE', json.dumps({k:v for k,v in report.items() if k!='per_query'}), flush=True)
