"""X2: retrain the public sanpier-family spectrum->structure scorer ourselves with the public training kit
(sanpier/casmi-spectrum-model-v1 kit as staged by bgunshui/casmi26-scorer-train-public: prepare.py, train.py, model.py,
features.py copied unchanged into the output bundle), so every ensemble member we ship has our own reproducible weights.

Usage:
  train_kit.py prepare --work DIR [--seed S]
  train_kit.py train --work DIR --out DIR --gpu N [--width 256 --heads 8 --layers 3 --epochs 120 --seed S ...]
The config starts from the kit's config.json; only the overrides given on the command line change. Time budgets are set
high (H100 is faster than the Kaggle T4 the budgets were written for) so epochs/patience decide, not the clock.
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

KIT = Path('/home/mpernigotto/jojo_molecular/data/fastweb/bgunshui_scorer_out/kit_staged')
TRAIN = '/home/mpernigotto/jojo_molecular/data/fastweb/competition/train.parquet'
KIT_FILES = ['prepare.py', 'train.py', 'model.py', 'features.py', 'inference.py']


def base_cfg(seed):
    cfg = json.loads((KIT/'config.json').read_text())
    cfg.update(seed=seed, train_path=TRAIN, external_paths=[], require_gpu=True, holdout_hours=48.0, refit_hours=48.0)
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['prepare', 'train'])
    ap.add_argument('--work', required=True)
    ap.add_argument('--out')
    ap.add_argument('--gpu', default='0')
    ap.add_argument('--seed', type=int, default=20261023)
    for k, t in [('width', int), ('heads', int), ('layers', int), ('embedding', int), ('epochs', int), ('patience', int),
                 ('lr', float), ('dropout', float), ('batch_size', int), ('hard_negatives', int), ('steps_per_epoch', int)]:
        ap.add_argument('--' + k, type=t)
    a = ap.parse_args()
    os.environ['CUDA_VISIBLE_DEVICES'] = a.gpu
    sys.path.insert(0, str(KIT))
    cfg = base_cfg(a.seed)
    cfg['work'] = a.work
    if a.cmd == 'prepare':
        import prepare
        Path(a.work).mkdir(parents=True, exist_ok=True)
        print(json.dumps(prepare.prepare(cfg), default=str)[:2000], flush=True)
        return
    for k in ['width', 'heads', 'layers', 'embedding', 'epochs', 'patience', 'lr', 'dropout', 'batch_size', 'hard_negatives',
              'steps_per_epoch']:
        v = getattr(a, k)
        if v is not None:
            cfg[k] = v
    if a.width is not None and a.embedding is None:
        cfg['embedding'] = a.width
    out = Path(a.out)
    cfg['output'] = str(out)
    out.mkdir(parents=True, exist_ok=True)
    for f in KIT_FILES:
        shutil.copy2(KIT/f, out/f)
    (out/'config.json').write_text(json.dumps(cfg, indent=2))
    (out/'config_used.json').write_text(json.dumps(cfg, indent=2))
    import train
    print(json.dumps(train.run(cfg), default=str), flush=True)


if __name__ == '__main__':
    main()
