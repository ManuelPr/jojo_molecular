"""Preserve the full v89 recipe and append one confidence-restoration policy."""
import ast
import json
from hashlib import sha256
from pathlib import Path
from build_flexon_v89_reproduction import build as build_reference

ROOT = Path(__file__).resolve().parents[1]

SNAPSHOT = '''# Read-only capture before simulator reranking mutates the PubChem list.
CONSENSUS_BEFORE_FORWARD = {}
for _mid, _base in BASE.items():
    _p = PC.get(str(_mid), PC.get(_mid, {}))
    _pc = list(_p.get('pc', []))
    _best = _p.get('best_pool_fz', float('nan'))
    _rel = ((_p['fz_top'] if _p.get('fz_top') is not None else _p['pc_fz'][0]) - _best
            if _pc and np.isfinite(_best) else 1e9)
    _s, _pop = _p.get('S'), float(_p.get('top_pop') or 0.)
    _confident = bool((_s is not None and float(_s) > 6. and _pop >= 5.) or _rel > 250.)
    CONSENSUS_BEFORE_FORWARD[str(_mid)] = dict(
        pc_smiles=_pc, base_smiles=list(_base[0]),
        eligible=bool(_pc and _base[2] < LIB_TAU and _confident))
'''


def cell(code):
    ast.parse(code)
    return dict(cell_type='code', execution_count=None, metadata={}, outputs=[], source=code.splitlines(keepends=True))


def build():
    reference = build_reference()
    origin = ROOT / 'kaggle/flexon_v89_reproduction_bundle'
    notebook = json.loads((origin / 'flexon_v89.ipynb').read_text(encoding='utf-8'))
    original_sources = [''.join(c['source']) for c in notebook['cells']]
    notebook['cells'].insert(22, cell(SNAPSHOT))
    policy = (ROOT / 'src/casmi26/pubchem_consensus.py').read_text()
    overlay = (ROOT / 'kaggle/pubchem_consensus_overlay.py').read_text()
    notebook['cells'].extend([cell(policy), cell(overlay)])
    assert [''.join(c['source']) for i,c in enumerate(notebook['cells'][:-2]) if i != 22] == original_sources
    notebook['metadata']['reproduction']['treatment'] = 'Restore confident PubChem lead only on strict forward agreement after v89 fusion.'
    out = ROOT / 'kaggle/pubchem_consensus_submission_bundle'; out.mkdir(exist_ok=True)
    target = out / 'pubchem_consensus.ipynb'
    target.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    meta = json.loads((origin / 'kernel-metadata.json').read_text())
    meta.update(id='mperni/casmi26-pubchem-forward-consensus', title='CASMI26 PubChem Forward Consensus', code_file=target.name)
    (out / 'kernel-metadata.json').write_text(json.dumps(meta, indent=2) + '\n')
    manifest = dict(reference_notebook_sha256=reference['notebook_sha256'],
                    notebook_sha256=sha256(target.read_bytes()).hexdigest(),
                    policy_sha256=sha256(policy.encode()).hexdigest(),
                    overlay_sha256=sha256(overlay.encode()).hexdigest(),
                    preserved_reference_cells=len(original_sources),
                    source_confidence_gate='Unmodified v89: lib<0.9 and ((S>6 and pop>=5) or rel>250)',
                    forward_gate='External lead strictly best among finite scores; at least 2 base and 2 external identities',
                    simulator='GLACIER if gl_of is nonempty, else ICEBERG; no score-based simulator selection',
                    official_submission_performed=False)
    (out / 'build_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    build()
