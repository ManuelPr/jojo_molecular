"""Build <base notebook> + wider class-3 generation (type-3 lever measured on K6/K7/T1 replays, K2_GEN_CFG in k2_runner.py).

One edit to the base notebook (C477 private fork, or a public notebook of the same lineage with the same frozen pipeline
and runner.py): the cell that starts with `BUNDLE = materialise_sources()` patches the pinned runner.py so that pipeline
cells 36 and 37 build the main engine with EngineCfg(generate=True, <GEN_CFG>) instead of EngineCfg(generate=True).
Everything downstream (forward models, fusion, neural consensus, final layer) is unchanged. No silent fallback: a missing
anchor fails the build or the kernel, and the runner asserts that both engine cells were patched.

Usage:
  build_c477_genwide.py                                   # C477 + genwide -> kaggle/c477_genwide_bundle
  build_c477_genwide.py --src DIR --out DIR --slug SLUG   # any same-lineage notebook directory (ipynb + kernel-metadata.json)
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN_CFG = 'gen_n_analog=24, gen_max_per_parent=200, gen_max_total=1000'
ANCHOR = 'BUNDLE = materialise_sources()\n'

RUNNER_HOOK = r'''# ── Genwide hook: wider class-3 generation in the main engine (pipeline cells 36 and 37) ──
_RUNNER = CODE / 'runner.py'
_rt = _RUNNER.read_text()
_A1 = "        exec(compile(''.join(c['source']),f'pipeline_cell_{i}','exec'),scope)\n"
_A2 = "    assert 'candidate_promotion_evidence' in scope, 'Candidate-specific promotion fix missing'\n"
_GEN_OLD = 'EngineCfg(generate=True)'
_GEN_NEW = 'EngineCfg(generate=True, __GEN_CFG__)'
assert _rt.count(_A1) == 1 and _rt.count(_A2) == 1, 'GENWIDE: runner anchor changed'
_rt = _rt.replace(_A1, "        _src=''.join(c['source'])\n"
                       "        if i in (36, 37) and _src.count(" + repr(_GEN_OLD) + "):\n"
                       "            _src=_src.replace(" + repr(_GEN_OLD) + ", " + repr(_GEN_NEW) + ")\n"
                       "            _GENWIDE_CELLS.append(i)\n"
                       "            print('GENWIDE cell', i, 'patched', flush=True)\n"
                       "        exec(compile(_src,f'pipeline_cell_{i}','exec'),scope)\n")
_rt = _rt.replace(_A2, "    assert _GENWIDE_CELLS == [36, 37], f'GENWIDE: engine cells patched {_GENWIDE_CELLS}'\n" + _A2)
_rt = _rt.replace("    scope={'__name__'", "    _GENWIDE_CELLS=[]\n    scope={'__name__'", 1)
assert _rt.count('_GENWIDE_CELLS=[]') == 1, 'GENWIDE: scope anchor changed'
compile(_rt, 'runner.py', 'exec')
_RUNNER.write_text(_rt)
print('GENWIDE runner hook installed:', __GEN_CFG_REPR__, flush=True)
'''.replace('__GEN_CFG_REPR__', repr(GEN_CFG)).replace('__GEN_CFG__', GEN_CFG)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--src', default=str(ROOT/'kaggle/c477_bundle'))
    p.add_argument('--out', default=str(ROOT/'kaggle/c477_genwide_bundle'))
    p.add_argument('--slug', default='casmi26-c477-genwide')
    a = p.parse_args()
    src, out = Path(a.src), Path(a.out)
    nbs = sorted(src.glob('*.ipynb'))
    assert len(nbs) == 1, nbs
    nb = json.loads(nbs[0].read_text())
    hits = [i for i, c in enumerate(nb['cells']) if c['cell_type'] == 'code' and ''.join(c['source']).startswith(ANCHOR)]
    assert len(hits) == 1, f'anchor cells {hits}'
    c = ''.join(nb['cells'][hits[0]]['source'])
    nb['cells'][hits[0]]['source'] = (ANCHOR + RUNNER_HOOK + c[len(ANCHOR):]).splitlines(keepends=True)
    for c in nb['cells']:
        if c['cell_type'] == 'code':
            c['outputs'], c['execution_count'] = [], None
    meta = json.loads((src/'kernel-metadata.json').read_text())
    meta.update(id=f'mperni/{a.slug}', title=a.slug.replace('-', ' '), code_file=f'{a.slug}.ipynb', is_private=True)
    meta.pop('id_no', None)
    out.mkdir(parents=True, exist_ok=True)
    (out/f'{a.slug}.ipynb').write_text(json.dumps(nb, indent=1))
    (out/'kernel-metadata.json').write_text(json.dumps(meta, indent=2)+'\n')
    print('wrote', out, 'hook cell', hits[0], 'bytes', (out/f'{a.slug}.ipynb').stat().st_size)


if __name__ == '__main__':
    main()
