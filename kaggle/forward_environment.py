"""Isolated CPython 3.12 reference stack without altering parent packages."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import zipfile


def streamed_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def unpack_verified_wheel(path, expected, destination):
    path, destination = Path(path), Path(destination)
    if path.stat().st_size != expected['bytes'] or streamed_hash(path) != expected['sha256']:
        raise RuntimeError('Wheel checksum mismatch: ' + path.name)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as wheel:
        for name in wheel.namelist():
            relative = PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts:
                raise RuntimeError('Unsafe wheel member')
            # Runtime packages in purelib/platlib must be placed at site root.
            parts = relative.parts
            if parts and parts[0].endswith('.data'):
                if len(parts) < 3 or parts[1] not in ('purelib', 'platlib'):
                    continue
                target = destination.joinpath(*parts[2:])
            else:
                target = destination.joinpath(*parts)
            if name.endswith('/'):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with wheel.open(name) as source, target.open('wb') as output:
                import shutil
                shutil.copyfileobj(source, output)


def prepare_forward_environment(pkg, aux, site, *, provenance_hash, auxiliary_hash, device='cpu'):
    pkg, aux, site = Path(pkg), Path(aux), Path(site)
    provenance_path = pkg / 'PROVENANCE.json'
    aux_path = aux / 'auxiliary_manifest.json'
    if streamed_hash(provenance_path) != provenance_hash or streamed_hash(aux_path) != auxiliary_hash:
        raise RuntimeError('Pinned forward environment manifest drift')
    manifest = json.loads(provenance_path.read_text())
    auxiliary = json.loads(aux_path.read_text())
    # Verify every upstream source module actually imported by the child.
    for name, expected in manifest['files'].items():
        if name.startswith(('ms_pred_src/', 'runner/')) or name == 'ckpt/glacier_msg/best.ckpt':
            path = pkg / name
            if path.stat().st_size != expected['bytes'] or streamed_hash(path) != expected['sha256']:
                raise RuntimeError('Forward source/checkpoint checksum mismatch: ' + name)
    front, back = site / 'front', site / 'back'
    marker = site / 'environment_complete.json'
    signature = {'provenance': provenance_hash, 'auxiliary': auxiliary_hash, 'device': device}
    if not marker.exists() or json.loads(marker.read_text()) != signature:
        groups = ('hi',) if device == 'cuda' else ('cpu', 'cpu_common')
        for name, expected in manifest['files'].items():
            if any(name.startswith('wheels/' + group + '/') for group in groups):
                unpack_verified_wheel(pkg / name, expected, front)
            elif name.startswith('wheels/lo/'):
                unpack_verified_wheel(pkg / name, expected, back)
        for name, expected in auxiliary['files'].items():
            unpack_verified_wheel(aux / name, expected, back)
        marker.write_text(json.dumps(signature))
    interpreter = Path('/usr/bin/python3.12')
    if not interpreter.is_file():
        raise RuntimeError('Pinned CPython 3.12 is unavailable')
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join([str(back), str(front), str(pkg / 'ms_pred_src')])
    env['OMP_NUM_THREADS'] = env['MKL_NUM_THREADS'] = env['OPENBLAS_NUM_THREADS'] = '4'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    return str(interpreter), env
