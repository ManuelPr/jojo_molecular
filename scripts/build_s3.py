"""Build S3 = NE-own4 + gated genfix (cell 39, G3b gate, writes /kaggle/working/g3b_gated.json) + G2 generation insert.

Input: a gated-genfix bundle built by build_c477_genwide.py --mode genfix --gate ... from kaggle/ne_own4_bundle (it must
contain the GF_GATED export of scripts/genfix_patch.py). One new final code cell runs scripts/g2/kernel_g2_stage.py from the
private dataset mperni/casmi26-g2-decoder after every other layer has written submission.csv: G2 v2 samples for the gated
molecules, scored by 0.5 z(public sanpier) + 0.5 z(own_w384_s7), KINS inserted after position MINPOS (values chosen on the
G4 cal halves). Time budget = min(MAX_H hours, 8.6 h - elapsed - 15 min). Fail-safe: the stage never breaks the submission.
Usage: build_s3.py SRC_BUNDLE OUT_DIR --kins K --minpos P [--slug casmi26-ne-own4-g2]
"""
import argparse
import json
from pathlib import Path

DATASET = 'mperni/casmi26-g2-decoder'
CELL = r'''# ── S3: G2 generation insert for gated (type-3-like) molecules; runs after every other layer ──
import sys as _s3sys, time as _s3time
from pathlib import Path as _S3P
_g2dirs = sorted({p.parent for p in _S3P('/kaggle/input').rglob('kernel_g2_stage.py') if 'g2-decoder' in str(p)}, key=lambda p: len(str(p)))
assert _g2dirs, 'S3: dataset casmi26-g2-decoder not attached'
_s3sys.path.insert(0, str(_g2dirs[0]))
import kernel_g2_stage as _g2stage
_s3_own = [d for d in OWN_DIRS if d.endswith('own_w384_s7')][0]
_s3_gated = ROOT / 'g3b_gated.json'
_s3_budget = max(0.0, min(__MAX_H__ * 3600, 8.6 * 3600 - (_s3time.time() - NB_T0) - 900))
print('S3 G2 stage: gated file', _s3_gated.is_file(), 'budget s', round(_s3_budget), flush=True)
if _s3_gated.is_file():
    S3_REPORT = _g2stage.run(str(ROOT), str(COMP / 'test.parquet'), str(_s3_gated), str(_g2dirs[0]), str(PUB_BUNDLE), _s3_own,
                             n=__N__, kins=__KINS__, minpos=__MINPOS__, device='cuda', time_budget_s=_s3_budget, topm=20)
else:
    print('S3 G2 stage: no gated ids (cell 39 did not write them); submission unchanged', flush=True)
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('out')
    ap.add_argument('--slug', default='casmi26-ne-own4-g2')
    ap.add_argument('--kins', type=int, required=True)
    ap.add_argument('--minpos', type=int, required=True)
    ap.add_argument('--n', type=int, default=256)
    ap.add_argument('--max_h', type=float, default=2.5)
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)
    nb = json.loads(next(src.glob('*.ipynb')).read_text())
    allsrc = ''.join(''.join(c['source']) for c in nb['cells'] if c['cell_type'] == 'code')
    assert 'GF_GATED' in allsrc and 'OWN_DIRS' in allsrc and 'PUB_BUNDLE' in allsrc, 'source bundle lacks gated export / own scorers'
    cell = (CELL.replace('__MAX_H__', repr(a.max_h)).replace('__N__', str(a.n)).replace('__KINS__', str(a.kins))
            .replace('__MINPOS__', str(a.minpos)))
    compile(cell, 's3cell', 'exec')
    nb['cells'].append(dict(cell_type='code', metadata={}, execution_count=None, outputs=[], source=cell.splitlines(keepends=True)))
    for c in nb['cells']:
        if c['cell_type'] == 'code':
            c['outputs'], c['execution_count'] = [], None
    meta = json.loads((src/'kernel-metadata.json').read_text())
    meta.update(id=f'mperni/{a.slug}', title=a.slug.replace('-', ' '), code_file=f'{a.slug}.ipynb', is_private=True)
    meta.pop('id_no', None)
    meta['dataset_sources'] = [d for d in meta['dataset_sources'] if d] + [DATASET]
    out.mkdir(parents=True, exist_ok=True)
    (out/f'{a.slug}.ipynb').write_text(json.dumps(nb, indent=1))
    (out/'kernel-metadata.json').write_text(json.dumps(meta, indent=2) + '\n')
    print('wrote', out, meta['dataset_sources'][-2:])


if __name__ == '__main__':
    main()
