"""Recover G3 evidence after the main retrieval/ICE stages completed.

Preserves cached candidate lists and successful ICE scores; repeats interrupted
GLACIER from its exact saved inputs. Avoids retaining the large reference index
in the parent while simulators run. No Kaggle API and no new allocation.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    out = ROOT/'artifacts/cluster/g3-dev200-2545/control'
    comp = out.parent/'competition'
    source = ROOT/'artifacts/cluster/f0-gu-v492-latest-audit/casmi26-v492-dg-v19.ipynb'
    from prepare_f0_source import SOURCE_SHA256
    assert hashlib.sha256(source.read_bytes()).hexdigest() == SOURCE_SHA256
    assert os.environ.get('SLURM_JOB_ID') == '2545'
    assert json.loads((ROOT/'artifacts/kaggle/f0-gu-v1/finalizer-state.json').read_text())['status'] == 'submitted'
    inputs = ['base-candidates.json', 'eng_lists.json', 'pc_lists.json',
              'raw_candidate_evidence.parquet', 'ice_work/ice_in.json',
              'ice_work/ice_out.json', 'ice_work/ice_out.json.meta.json',
              'cell-25.py', 'cell-26.py', 'cell-40.py']
    manifest = dict(source_sha256=SOURCE_SHA256, repeated_stages=['GLACIER real and N1 proxy', 'fusion/audit'],
                    reused_stages=['main candidates', 'Engine2', 'PubChem', 'ICEBERG'],
                    inputs_sha256={p: hashlib.sha256((out/p).read_bytes()).hexdigest() for p in inputs},
                    reason='Previous26GiB guard interrupted GLACIER; reconstruct a lightweight parent without the reference index.')
    (out.parent/'forward-recovery-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    os.chdir(out)
    inp = out/'input'
    env = dict(__name__='__main__', Path=Path, time=time, os=os, json=json, hashlib=hashlib,
               display=lambda value: print('DISPLAY', getattr(value, 'shape', type(value).__name__)))
    exec('import sys,glob,pickle,math,gc\nimport numpy as np\nimport pandas as pd\nimport pyarrow as pa\nimport pyarrow.parquet as pq\nimport rdkit\nimport torch\n', env)
    env.update(FOLD=inp/'casmi26-fold-safe-fpnet', POP=inp/'casmi26-pubchem-popularity-prior',
               TABLE=inp/'casmi26-natural-product-knowledge-table', PANEL=inp/'casmi26-natural-product-panel-benchmark',
               NOTEBOOK_STARTED=time.monotonic())
    for i in [25, 26]:
        exec(compile((out/f'cell-{i}.py').read_text(), f'cell-{i}.py', 'exec'), env)
    sys.path.insert(0, env['V4CODE'])
    from casmi import chem
    from rdkit import Chem
    from rdkit.Chem.rdMolDescriptors import CalcMolFormula
    sys.path.insert(0, str(inp/'casmi26-attributed-v4g-reproduction-assets/casmi26-iceberg'))
    import fuse as ice_fuse
    base = json.loads((out/'base-candidates.json').read_text())
    BASE = {k: (v['smiles'], v['keys'], v['library_confidence'], v['scores'], v['formulas']) for k, v in base.items()}
    pc = json.loads((out/'pc_lists.json').read_text())
    for mid, values in pc.items():
        if values.get('pc') and BASE[mid][2] < env['LIB_TAU']:
            values['pc_form'] = [CalcMolFormula(Chem.MolFromSmiles(s)) for s in values['pc']]
    te = env['pd'].read_parquet(comp/'test.parquet')
    te['nm'] = chem.neutral_mass(te.precursor_mz.values.astype(float), te.adduct.values)
    items = json.loads((out/'ice_work/ice_in.json').read_text())
    meta = json.loads((out/'ice_work/ice_out.json.meta.json').read_text())
    assert meta['status'] == 'ok' and meta['n_pred_fail'] == 0 and meta['n_mols'] == 200
    assert set(BASE) == {str(it['mid']) for it in items} == set(json.loads((comp/'contract.json').read_text())['truth'])
    cell40 = (out/'cell-40.py').read_text()
    header = cell40[:cell40.index('\ntry:\n    ICE_PKG =')]
    exec(compile(header, 'cell40-helper-definitions.py', 'exec'), env)
    env.update(chem=chem, ice_fuse=ice_fuse, BASE=BASE, PC=pc,
               ENG=json.loads((out/'eng_lists.json').read_text()),
               BASE_TAIL_CANDIDATES={k: list(v[0]) for k, v in BASE.items()},
               te=te, COMP=str(comp), dev='cuda', n_err=0, IS_RERUN=True, SMOKE_N=200,
               items=items, cands={str(it['mid']): it['cands'] for it in items},
               mids=sorted(BASE, key=lambda m: BASE[m][2]), ICE_PC=True,
               ICE_PKG=str(inp/'casmi26-attributed-v4g-reproduction-assets/casmi26-iceberg'),
               ICE_SCORES=json.loads((out/'ice_work/ice_out.json').read_text()),
               CLAW_ICE_HEALTH='ok; restored from verified successful metadata',
               ENG_DIR=str(out/'eng'),
               POOL_POP=env['np'].load(inp/'casmi26-pubchem-popularity-prior/pool_lsid.npy').astype(float)
                        +env['np'].load(inp/'casmi26-pubchem-popularity-prior/pool_lpmid.npy').astype(float))
    # Retain the interrupted driver output before the original glue overwrites it.
    if (out/'gl_work').exists():
        archive = out/('gl_work-interrupted-'+str(int(time.time())))
        (out/'gl_work').rename(archive)
    print('RECOVERY_FORWARD_START', flush=True)
    tail = cell40[cell40.index('GL_SCORES, gl_stats, GL_LAM, GL_BUDGET ='):]
    exec(compile(tail, 'cell40-forward-recovery.py', 'exec'), env)
    for key in ['ICE_SCORES', 'GL_SCORES', 'GL_REAL_SCORES']:
        (out/(key.lower()+'.json')).write_text(json.dumps(env[key], default=str))
    (out/'simulator-items.json').write_text(json.dumps(items, default=str))
    nb = json.loads(source.read_text())
    for i in [42, 44, 46, 47, 48, 49, 50, 51, 52]:
        print('RECOVERY_ANALYSIS_CELL', i, flush=True)
        if i == 49:
            env['E004_REPORT'] = dict(experiment='E004', processed_ids=sorted(BASE),
                                     hashes={'submission.csv': hashlib.sha256((out/'submission.csv').read_bytes()).hexdigest()}, stages={})
            (out/'e004_verification.json').write_text(json.dumps(env['E004_REPORT'], indent=2))
            continue
        code = ''.join(nb['cells'][i]['source']).replace('/kaggle/input', str(inp)).replace('/kaggle/working', str(out))
        exec(compile(code, f'cell-{i}-recovery.py', 'exec'), env)
    from f0_g1_evidence import export
    export(env, comp/'contract.json', out)
    manifest.update(status='complete', final_submission_sha256=hashlib.sha256((out/'submission.csv').read_bytes()).hexdigest())
    (out.parent/'forward-recovery-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print('RECOVERY_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
