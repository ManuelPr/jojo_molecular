"""Build NE480-JM3: the public 0.480 neural-ensemble notebook with our JM-base scorer (mperni/casmi26-jm-base-s1, replay
arm jm_base) as a third member of the ranks 2-25 neural z-ensemble: 0.5 z(public) + 0.25 z(bgunshui) + 0.25 z(JM).
Rank 1 keeps the pipeline's leader-safe decision as before; neural_cos / neural_fp / neural_std / neural_ok (read by the
fragment check) keep the original two-model averages. K10 (scripts/unseen/eval_neural_ensemble.py) measured
z(public)+z(JM) on ranks 2-25: T1-thin ver +0.011, K6 type 2 +0.010 (all), type 3 +0.002, T1 -0.001.
No silent fallback: if the JM scorer fails the kernel fails.

Usage: build_ne480_jm3.py SRC_DIR OUT_DIR
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLUG = 'casmi26-ne480-jm3'
JM_NB = Path('/home/mpernigotto/jojo_molecular/kaggle/jm_submissions/jm-base-s1/notebook/casmi26-jm-base-s1.ipynb')
JM_DATASET = 'mperni/casmi26-jm-base-s1'

OLD = """    _a['neural_score'] = 0.5 * _z(_a['neural_score'].fillna(0.0)) + 0.5 * _z(_b['neural_score'].fillna(0.0))\n"""
NEW = """    from bundle import find_bundle as _jm_find_bundle
    JM_BUNDLE = _jm_find_bundle(str(INPUT), ROOT, JM_PINS)
    BUNDLE = JM_BUNDLE
    assert score_final_lists(), 'JM3: JM scorer failed'
    shutil.copyfile(ROOT / 'neural_candidate_features.parquet', ROOT / 'neural_jm.parquet')
    _c = _pd.read_parquet(ROOT / 'neural_jm.parquet').set_index(['molecule_id', 'smiles']).reindex(_a.index)
    assert _c['neural_score'].notna().mean() > 0.95, 'JM3: JM scores missing'
    _a['neural_score'] = (0.5 * _z(_a['neural_score'].fillna(0.0)) + 0.25 * _z(_b['neural_score'].fillna(0.0))
                          + 0.25 * _z(_c['neural_score'].fillna(0.0)))
    print('JM3 ENSEMBLE neural = 0.5*z(public) + 0.25*z(bgunshui) + 0.25*z(JM-base)', JM_BUNDLE, flush=True)
"""


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    nb = json.loads(next(src.glob('*.ipynb')).read_text())
    jm_src = '\n'.join(''.join(c['source']) for c in json.loads(JM_NB.read_text())['cells'] if c['cell_type'] == 'code')
    pins = re.search(r'MODEL_PINS = (\{[^}]*\})', jm_src).group(1)
    hits = 0
    for c in nb['cells']:
        s = ''.join(c['source'])
        if c['cell_type'] == 'code' and OLD in s:
            assert s.count(OLD) == 1 and '_b = _pd.read_parquet' in s
            s = s.replace(OLD, NEW)
            c['source'] = s.splitlines(keepends=True); hits += 1
        if c['cell_type'] == 'code' and s.startswith('MODEL_PINS = {') or (c['cell_type'] == 'code' and '\nMODEL_PINS = {' in s):
            s = s.replace('MODEL_PINS = {', 'JM_PINS = ' + pins + '\nMODEL_PINS = {', 1)
            c['source'] = s.splitlines(keepends=True); hits += 10
        if c['cell_type'] == 'code':
            c['outputs'], c['execution_count'] = [], None
    assert hits == 11, f'anchors found {hits}'
    meta = json.loads((src/'kernel-metadata.json').read_text())
    meta.update(id=f'mperni/{SLUG}', title=SLUG.replace('-', ' '), code_file=f'{SLUG}.ipynb', is_private=True)
    meta.pop('id_no', None)
    meta['dataset_sources'] = list(meta['dataset_sources']) + [JM_DATASET]
    out.mkdir(parents=True, exist_ok=True)
    (out/f'{SLUG}.ipynb').write_text(json.dumps(nb, indent=1))
    (out/'kernel-metadata.json').write_text(json.dumps(meta, indent=2)+'\n')
    print('wrote', out, 'JM pins', pins[:80])


if __name__ == '__main__':
    main()
