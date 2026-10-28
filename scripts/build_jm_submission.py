"""Package a trained JM scorer as a private Kaggle dataset and a C477 notebook variant that uses it.

The C477 notebook (public busyaprime m1 fork) selects its neural bundle by SHA-256 pins over
features.py, model.py, config.json and final_model.pt; we swap those pins and attach our dataset.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'kaggle/c477_bundle'
OLD_PINS = {
    'features.py': 'a97ad9b3ab3711517864d56e497e1672cb29bb05683c72b52db9f9b0a17b1455',
    'model.py': '2547418857386d1c2513fd1ab6c70961e6a96e73d9d495bbfe3052197e69dc39',
    'config.json': '563fb2a2a81ca48ea094f9ab78c157a48a6e9a5503e85e6ce8f0fb3615c1cc03',
    'final_model.pt': '44436b2daec64373e66f9120dd2389c24fc83dd9430ebeeac18e3cb49dcb9642',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True, help='training output dir with config.json and final_model.pt')
    p.add_argument('--name', required=True, help='short slug, e.g. jm-base-s1')
    p.add_argument('--set', nargs='*', default=[], help='notebook config overrides NAME=python_literal (e.g. CUSTOM weights)')
    a = p.parse_args()
    run = Path(a.run)
    out = ROOT/'kaggle/jm_submissions'/a.name
    data = out/'dataset'
    nb = out/'notebook'
    shutil.rmtree(out, ignore_errors=True)
    data.mkdir(parents=True)
    nb.mkdir(parents=True)
    for f in ['features.py', 'model.py']:
        shutil.copy2(ROOT/'kaggle/jm_scorer'/f, data/f)
    shutil.copy2(run/'final_model.pt', data/'final_model.pt')
    cfg = json.loads((run/'config.json').read_text())
    cfg.pop('work', None)
    cfg.pop('output', None)
    (data/'config.json').write_text(json.dumps(cfg, indent=2))
    for f in ['training_history.json', 'training_result.json']:
        if (run/f).exists():
            shutil.copy2(run/f, data/f)
    (data/'README.txt').write_text(
        'JM spectrum-candidate scorer (mperni). Drop-in for sanpier/casmi-spectrum-model-v1 bundles.\n'
        'Training code: kaggle/jm_scorer/train_jm.py (github ManuelPr/jojo_molecular), data: competition train.parquet\n'
        'plus PubChem tier negatives (dmitriigluzdov/casmi26-pubchem-popularity-prior). Architecture and features\n'
        'derived from Saner Turhaner (sanpier) casmi-spectrum-model-v1.\n')
    slug = f'casmi26-{a.name}'
    (out/'dataset/dataset-metadata.json').write_text(json.dumps(
        dict(title=slug, id=f'mperni/{slug}', licenses=[dict(name='CC-BY-NC-SA-4.0')]), indent=2))
    pins = {f: sha(data/f) for f in OLD_PINS}
    nbsrc = json.loads((BASE/'casmi26-c477-public-port.ipynb').read_text())
    replaced = 0
    for cell in nbsrc['cells']:
        text = ''.join(cell['source'])
        new = text
        for f, old in OLD_PINS.items():
            new = new.replace(f'"{f}": "{old}"', f'"{f}": "{pins[f]}"')
        for kv in a.set:
            k, v = kv.split('=', 1)
            lines = new.split('\n')
            for i, line in enumerate(lines):
                if line.startswith(k+' =') or line.startswith(k+'='):
                    lines[i] = f'{k} = {v}'
                    replaced += 1
            new = '\n'.join(lines)
        if new != text:
            cell['source'] = new.splitlines(keepends=True)
    text = json.dumps(nbsrc)
    assert all(pins[f] in text for f in pins), 'MODEL_PINS not replaced'
    assert replaced >= len(a.set), 'notebook override not applied'
    code = f'{slug}.ipynb'
    (nb/code).write_text(json.dumps(nbsrc, indent=1))
    meta = json.loads((BASE/'kernel-metadata.json').read_text())
    meta.update(id=f'mperni/{slug}-nb', title=f'{slug}-nb', code_file=code)
    meta['dataset_sources'] = meta['dataset_sources']+[f'mperni/{slug}']
    (nb/'kernel-metadata.json').write_text(json.dumps(meta, indent=2))
    (out/'build-manifest.json').write_text(json.dumps(dict(run=str(run), pins=pins, overrides=a.set,
                                                          notebook_sha256=sha(nb/code)), indent=2))
    print(json.dumps(dict(out=str(out), pins=pins), indent=1))


if __name__ == '__main__':
    main()
