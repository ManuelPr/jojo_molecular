"""Build NE-own: the public 0.480 neural-ensemble notebook (our verbatim copy) with the second scorer (bgunshui kernel output,
no longer attachable: kernels.get denied since 2026-11-04) replaced by OUR four kit-retrained scorers from the private
dataset mperni/casmi26-own-kit-scorers (artifacts/X2, scripts/extlib/train_kit.py):
  neural_score = 0.5 z(public) + 0.5 mean_i z(own_i)      (K12 'self4' with our own arms)
neural_cos / neural_fp / neural_std (read by the fragment check) = 0.5 public + 0.5 mean of ours; the pipeline run and the
outside candidates use our best scorer (own_w384_s7) where the original used bgunshui's. Rank 1 logic unchanged.
No silent fallback: a missing or failing own scorer fails the kernel.
Usage: build_ne_own.py SRC_BUNDLE_DIR OUT_DIR [--slug casmi26-ne-own4]
"""
import argparse
import json
from pathlib import Path

DATASET = 'mperni/casmi26-own-kit-scorers'
START = 'PUB_BUNDLE = BUNDLE\n'
END = "    print('ENSEMBLE neural = 0.5*z(public) + 0.5*z(ours)', flush=True)\n"
NEW = r'''PUB_BUNDLE = BUNDLE
import pathlib as _pl
OWN_DIRS = sorted({str(p.parent) for p in _pl.Path('/kaggle/input').rglob('final_model.pt') if '__MATCH__' in str(p)})
assert len(OWN_DIRS) == __NOWN__ and all((_pl.Path(d) / 'config.json').is_file() for d in OWN_DIRS), ('OWN: expected __NOWN__ own scorers', OWN_DIRS)
OURS_BUNDLE = [d for d in OWN_DIRS if d.endswith('__BEST__')][0]
print('OWN SCORERS', OWN_DIRS, 'best', OURS_BUNDLE, flush=True)
BUNDLE = OURS_BUNDLE
PIPELINE_DONE = run_public_pipeline()
if not PIPELINE_DONE and not IS_RERUN and COMMIT_MODE == 'fast':
    shutil.copyfile(COMP / 'sample_submission.csv', ROOT / 'submission.csv')
    raise SystemExit('fast commit: sample file written, the scoring rerun runs every stage')
if not PIPELINE_DONE:
    raise RuntimeError('A real baseline run is required; no placeholder-only submission')
BUNDLE = PUB_BUNDLE
NEURAL_OK = score_final_lists()
shutil.copyfile(ROOT / 'neural_candidate_features.parquet', ROOT / 'neural_public.parquet')
import pandas as _pd
_a = _pd.read_parquet(ROOT / 'neural_public.parquet').set_index(['molecule_id', 'smiles'])
def _z(_s):
    _g = _s.groupby(level=0)
    return (_s - _g.transform('mean')) / _g.transform(lambda x: x.std(ddof=0)).clip(lower=1e-6)
_own = []
for _i, _d in enumerate(OWN_DIRS):
    BUNDLE = _d
    assert score_final_lists(), ('OWN: scorer failed', _d)
    shutil.copyfile(ROOT / 'neural_candidate_features.parquet', ROOT / f'neural_own{_i}.parquet')
    _b = _pd.read_parquet(ROOT / f'neural_own{_i}.parquet').set_index(['molecule_id', 'smiles']).reindex(_a.index)
    assert _b['neural_score'].notna().mean() > 0.95, ('OWN: scores missing', _d)
    _own.append(_b)
_zo = sum(_z(_b['neural_score'].fillna(0.0)) for _b in _own) / len(_own)
_a['neural_score'] = 0.5 * _z(_a['neural_score'].fillna(0.0)) + 0.5 * _zo
for _c in ['neural_cos', 'neural_fp', 'neural_std']:
    _a[_c] = 0.5 * _a[_c] + 0.5 * sum(_b[_c].fillna(0.0) for _b in _own) / len(_own)
for _b in _own:
    _a['neural_ok'] = _a['neural_ok'].astype(bool) & _b['neural_ok'].fillna(False).astype(bool)
_a.reset_index().to_parquet(ROOT / 'neural_candidate_features.parquet', index=False)
print('OWN ENSEMBLE neural = 0.5*z(public) + 0.5*mean z(own x4)', flush=True)
if True:
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('out')
    ap.add_argument('--slug', default='casmi26-ne-own4')
    ap.add_argument('--dataset', default=DATASET)
    ap.add_argument('--match', default='own-kit-scorers', help='substring of the attached dataset path holding the own scorers')
    ap.add_argument('--n_own', type=int, default=4)
    ap.add_argument('--best', default='own_w384_s7', help='scorer used where the original used bgunshui alone')
    a = ap.parse_args()
    global NEW
    NEW = NEW.replace('__MATCH__', a.match).replace('__NOWN__', str(a.n_own)).replace('__BEST__', a.best)
    src, out = Path(a.src), Path(a.out)
    nb = json.loads(next(src.glob('*.ipynb')).read_text())
    hits = 0
    for c in nb['cells']:
        if c['cell_type'] != 'code':
            continue
        s = ''.join(c['source'])
        if START in s and END in s:
            i, j = s.index(START), s.index(END) + len(END)
            assert s.count(START) == 1 and s.count(END) == 1
            s = s[:i] + NEW + "    pass\n" + s[j:]
            c['source'] = s.splitlines(keepends=True)
            hits += 1
        c['outputs'], c['execution_count'] = [], None
    assert hits == 1, f'anchor cell found {hits} times'
    meta = json.loads((src/'kernel-metadata.json').read_text())
    meta.update(id=f'mperni/{a.slug}', title=a.slug.replace('-', ' '), code_file=f'{a.slug}.ipynb', is_private=True)
    meta.pop('id_no', None)
    meta['kernel_sources'] = []
    meta['dataset_sources'] = [d for d in meta['dataset_sources'] if d] + [a.dataset]
    out.mkdir(parents=True, exist_ok=True)
    (out/f'{a.slug}.ipynb').write_text(json.dumps(nb, indent=1))
    (out/'kernel-metadata.json').write_text(json.dumps(meta, indent=2) + '\n')
    print('wrote', out, meta['dataset_sources'])


if __name__ == '__main__':
    main()
