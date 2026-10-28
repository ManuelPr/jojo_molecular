"""Generate a Kaggle GPU notebook that trains one JM scorer from the private cache/code datasets."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CELL = r'''
import json, shutil, subprocess, sys, time
from pathlib import Path
RUN = {run!r}
OVERRIDES = {overrides!r}
code = next(p.parent for p in Path('/kaggle/input').rglob('train_jm.py'))
data = next(p.parent for p in Path('/kaggle/input').rglob('peaks.bin'))
jm = Path('/kaggle/working/jm'); (jm/'upstream').mkdir(parents=True, exist_ok=True)
for f in ['train_jm.py', 'model.py', 'features.py']: shutil.copy2(code/f, jm/f)
shutil.copy2(code/'upstream_train.py', jm/'upstream'/'train.py')
shutil.copy2(code/'features.py', jm/'upstream'/'features.py')
cfg = json.loads((code/'jm_base.json').read_text())
cfg.update(work=str(data), bank_dir=str(data), amp='fp16', hours=10.5, **OVERRIDES)
(jm/'run_config.json').write_text(json.dumps(cfg, indent=2))
out = Path('/kaggle/working')/RUN
print('code', code, 'data', data, 'config', cfg, flush=True)
subprocess.run(['nvidia-smi'])
t = time.time()
proc = subprocess.run([sys.executable, '-u', str(jm/'train_jm.py'), '--config', str(jm/'run_config.json'), '--output', str(out)])
print('exit', proc.returncode, 'minutes', round((time.time()-t)/60, 1), flush=True)
for f in ['last_model.pt', 'validation_predictions.csv']:
    (out/f).unlink(missing_ok=True)
print(sorted(p.name for p in out.iterdir()))
print((out/'training_result.json').read_text() if (out/'training_result.json').exists() else 'NO RESULT')
assert proc.returncode == 0
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--name', required=True, help='run name, e.g. base-s3')
    p.add_argument('--set', nargs='*', default=[], help='config overrides key=json')
    a = p.parse_args()
    overrides = {k: json.loads(v) for k, v in (kv.split('=', 1) for kv in a.set)}
    out = ROOT/'kaggle/jm_train_runs'/a.name
    out.mkdir(parents=True, exist_ok=True)
    slug = f'casmi26-jm-train-{a.name}'
    nb = dict(nbformat=4, nbformat_minor=5, metadata=dict(kernelspec=dict(name='python3', display_name='Python 3', language='python')),
              cells=[dict(cell_type='code', metadata={}, execution_count=None, outputs=[],
                          source=CELL.format(run=a.name, overrides=overrides).strip().splitlines(keepends=True))])
    (out/f'{slug}.ipynb').write_text(json.dumps(nb, indent=1))
    meta = dict(id=f'mperni/{slug}', title=slug, code_file=f'{slug}.ipynb', language='python', kernel_type='notebook',
                is_private=True, enable_gpu=True, enable_internet=False, machine_shape='NvidiaTeslaT4',
                dataset_sources=['mperni/casmi26-jm-code', 'mperni/casmi26-jm-cache-v1'], competition_sources=[], kernel_sources=[])
    (out/'kernel-metadata.json').write_text(json.dumps(meta, indent=2))
    print(out, overrides)


if __name__ == '__main__':
    main()
