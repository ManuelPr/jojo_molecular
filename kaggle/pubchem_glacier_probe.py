"""Offline environment and asset probe; no submission, no accuracy claim."""
import glob
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np
import base64
import io


def find(name):
    hits = glob.glob('/kaggle/input/**/' + name, recursive=True)
    if len(hits) != 1:
        raise RuntimeError(f'Expected one {name}, found {hits}')
    return Path(hits[0])


report = {'main_python': sys.version, 'started': time.time(), 'phase': 'inventory'}


def save():
    Path('probe_report.json').write_text(json.dumps(report, indent=2))
    print('[PROBE]', json.dumps(report), flush=True)


try:
    pc_mass = np.load(find('pc_mass.npy'), mmap_mode='r')
    pc_off = np.load(find('pc_off.npy'), mmap_mode='r')
    pc_smiles = np.load(find('pc_smiles.npy'), mmap_mode='r')
    if pc_off.shape != (len(pc_mass) + 1,) or pc_smiles.ndim != 1:
        raise RuntimeError('PubChem array contract mismatch')
    if pc_off[0] != 0 or pc_off[-1] != len(pc_smiles):
        raise RuntimeError('PubChem offset contract mismatch')
    report['pubchem'] = {'count': len(pc_mass), 'mass_dtype': str(pc_mass.dtype),
                        'offset_dtype': str(pc_off.dtype), 'buffer_dtype': str(pc_smiles.dtype),
                        'smiles_bytes': len(pc_smiles), 'file_bytes': {n: find(n).stat().st_size for n in ['pc_mass.npy', 'pc_off.npy', 'pc_smiles.npy']}}
    mass = 194.0803756
    lo, hi = np.searchsorted(pc_mass, [mass * (1 - 10e-6), mass * (1 + 10e-6)])
    off = pc_off[lo:hi+1]
    report['pubchem']['caffeine_window_count'] = int(hi-lo)
    report['pubchem']['first_smiles'] = [bytes(pc_smiles[int(off[j]):int(off[j+1])]).decode('ascii') for j in range(min(3, hi-lo))]
    provenance = find('PROVENANCE.json')
    if sha256(provenance.read_bytes()).hexdigest() != STACK_PROVENANCE_SHA256:
        raise RuntimeError('Forward stack provenance drift')
    pkg = provenance.parent
    inventory = json.loads(provenance.read_text())['files']
    for name in ['runner/fwd_runner.py', 'ckpt/glacier_msg/best.ckpt']:
        path = pkg / name
        if sha256(path.read_bytes()).hexdigest() != inventory[name]['sha256']:
            raise RuntimeError('Forward asset drift: ' + name)
    candidates = ['/usr/bin/python3.12', '/opt/venv/bin/python3.12', shutil.which('python3.12')]
    versions = {}
    for p in candidates:
        if p and Path(p).is_file():
            r = subprocess.run([p, '-c', 'import sys,json;print(json.dumps({"version":sys.version,"path":sys.path}))'], capture_output=True, text=True)
            versions[p] = {'returncode': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr}
    report['python312_candidates'] = versions
    save()
    if not versions:
        raise RuntimeError('No Python 3.12 interpreter for pinned upstream stack')
    python = next(p for p,v in versions.items() if v['returncode'] == 0)
    python, child_env = prepare_forward_environment(pkg, find('auxiliary_manifest.json').parent, '/kaggle/tmp/fwd_probe_site',
                                                    provenance_hash=STACK_PROVENANCE_SHA256, auxiliary_hash=AUXILIARY_SHA256, device=PROBE_DEVICE)
    items = [{'id': 'compatibility_only', 'candidates': ['Cn1c(=O)c2c(ncn2C)n(C)c1=O', 'CC(=O)Oc1ccccc1C(=O)O'],
              'spectra': [{'mz': [50.0, 100.0, 150.0], 'it': [1.0, 0.5, 0.2], 'precursor_mz': 195.08765,
                           'adduct': '[M+H]+', 'ce': 30.0, 'instrument': 'timsTOF', 'mode': 'positive'}]}]
    Path('probe_input.json').write_text(json.dumps(items))
    command = [python, str(pkg / 'runner/fwd_runner.py'), str(pkg), 'raw', 'probe_input.json', 'probe_raw.npz',
               '--models', 'glacier', '--stack', 'none', '--device', PROBE_DEVICE, '--bs', '2', '--budget', '1200']
    report['phase'] = 'forward_smoke'
    report['command'] = command
    save()
    result = subprocess.run(command, capture_output=True, text=True, timeout=1500, env=child_env)
    Path('probe_forward.log').write_text(result.stdout + '\n' + result.stderr)
    report['forward_exit_code'] = result.returncode
    report['forward_log_tail'] = (result.stdout + result.stderr)[-3500:]
    meta = Path('probe_raw.npz.meta.json')
    report['forward_meta'] = json.loads(meta.read_text()) if meta.exists() else None
    if result.returncode != 0 or not report['forward_meta'] or report['forward_meta']['status'] != 'ok' or report['forward_meta']['device'] != PROBE_DEVICE:
        raise RuntimeError('Pinned upstream GLACIER smoke failed; inspect probe_forward.log')
    with np.load('probe_raw.npz') as raw:
        if len(raw.files) != 2:
            raise RuntimeError('Expected two real forward predictions')
        for key in raw.files:
            array = raw[key]
            if array.ndim != 2 or array.shape[1] != 2 or not np.isfinite(array).all() or not (array[:, 1] > 0).any():
                raise RuntimeError('Invalid GLACIER prediction')
        if CPU_REFERENCE_B64:
            reference = np.load(io.BytesIO(base64.b64decode(CPU_REFERENCE_B64)))
            differences = {}
            for key in raw.files:
                expected, actual = reference[key], raw[key]
                if expected.shape != actual.shape:
                    raise RuntimeError('CPU/GPU fragment enumeration differs')
                order_e = np.lexsort((expected[:, 1], expected[:, 0]))
                order_a = np.lexsort((actual[:, 1], actual[:, 0]))
                expected, actual = expected[order_e], actual[order_a]
                differences[key] = np.abs(expected-actual).max(axis=0).tolist()
                if not np.allclose(expected, actual, rtol=1e-4, atol=1e-5):
                    raise RuntimeError('CPU/GPU prediction parity failed')
            report['cpu_gpu_parity_max_abs_difference'] = differences
    report['phase'] = 'complete'
    report['complete'] = True
except Exception as error:
    report['phase'] = 'failed'
    report['complete'] = False
    report['error'] = repr(error)
    raise
finally:
    report['elapsed_seconds'] = time.time() - report['started']
    save()
