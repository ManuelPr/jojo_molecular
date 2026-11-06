"""Package our kit-retrained scorers (X2) as a private Kaggle dataset folder: one subfolder per scorer with the files the
inference loader needs (config.json, model.py, features.py, final_model.pt) plus the training source and results for
reproducibility (train.py, prepare.py, config_used.json, training_result.json, training/refit history) and the driver
scripts/extlib/train_kit.py. Usage: package_own_scorers.py OUT_DIR
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

X2 = Path('/home/mpernigotto/jojo_molecular/artifacts/X2')
SCORERS = ['own_v4p12_s20261023', 'own_v4p12_s7', 'own_w384_s20261023', 'own_w384_s7']
FILES = ['config.json', 'config_used.json', 'model.py', 'features.py', 'final_model.pt', 'train.py', 'prepare.py', 'inference.py',
         'training_result.json', 'training_history.json', 'refit_history.json']


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--scorers', default=','.join(SCORERS))
    ap.add_argument('--id', default='mperni/casmi26-own-kit-scorers')
    a = ap.parse_args()
    out = Path(a.out)
    scorers = a.scorers.split(',')
    out.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for s in scorers:
        d = out/s
        d.mkdir(exist_ok=True)
        for f in FILES:
            if (X2/s/f).exists():
                shutil.copy2(X2/s/f, d/f)
        cfg = json.loads((d/'config.json').read_text())
        res = json.loads((d/'training_result.json').read_text())
        manifest[s] = dict(width=cfg['width'], heads=cfg['heads'], layers=cfg['layers'], epochs=cfg['epochs'], seed=cfg['seed'],
                           best_epoch=res['best_epoch'], diagnostic_mrr25=res['best_diagnostic_mrr25'],
                           sha256=hashlib.sha256((d/'final_model.pt').read_bytes()).hexdigest())
    shutil.copy2(Path(__file__).with_name('train_kit.py'), out/'train_kit.py')
    (out/'MANIFEST.json').write_text(json.dumps(manifest, indent=1))
    (out/'README.md').write_text(
        '# CASMI26 own kit scorers\n\nSpectrum->structure scorers retrained by us from random weights with the public '
        'sanpier/casmi-spectrum-model-v1 training kit (train.py / prepare.py / model.py / features.py, unchanged) on the '
        'competition train.parquet only (no external data). Driver: train_kit.py (prepare, then train with the overrides in '
        'each config.json). MANIFEST.json lists architecture, seed, best epoch, diagnostic MRR@25 and checkpoint SHA-256.\n')
    (out/'dataset-metadata.json').write_text(json.dumps(dict(title=a.id.split('/')[1].replace('-', ' '), id=a.id,
                                                              licenses=[dict(name='CC0-1.0')]), indent=1))
    print(json.dumps(manifest, indent=1))


if __name__ == '__main__':
    main()
