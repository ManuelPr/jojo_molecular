"""Replay the C477 frozen 0.465 pipeline locally on a K2 cohort, reference-excluded, with per-stage exports.

Patches (each asserted to apply once): /kaggle/input and /kaggle/working remapped; RDKit wheel bootstrap
removed (venv already has 2026.03.3); external reference cache filtered with Codex's
exclude_canonical_references right after it is built from the cohort's filtered train.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT/'artifacts/k2_replay/src/frozen_0465.ipynb'
FROZEN_SHA256 = 'd1e757c2b71b46e6e8a5777f14302a4737d0fdbcd56d8365093c039b93c5fd88'
CROSSWALK = ROOT/'data/fastweb/casmi26-natural-product-panel-benchmark-v10/casmi26-identity-disjoint-validation-folds/structures.parquet'


def patch(i, source, inp, out, contract_path, catalog_contract=None):
    source = source.replace('/kaggle/input', str(inp)).replace('/kaggle/working', str(out))
    if i == 28 and os.environ.get('K2_STOP_AFTER'):
        # CPU phase on a node without GPUs: the preflight GPU probe is informational there.
        old = "gpu = subprocess.check_output("
        assert source.count(old) == 1
        source = source.replace("assert gpu and gpu.strip(), gpu", "assert gpu is not None, gpu")
        source = source.replace(old, "gpu = 'cpu-phase' if True else subprocess.check_output(")
    if i in (32, 34) and os.environ.get('K2_DIAG_TOPN'):
        # Diagnostic CPU phase only: longer Engine2 / PubChem lists to measure channel recall beyond the top 25.
        assert os.environ.get('K2_STOP_AFTER'), 'K2_DIAG_TOPN changes downstream fusion: CPU phase only'
        old = '    TOPN = 25\\n' if i == 32 else 'K = 25\\n'
        assert source.count(old) == 1
        source = source.replace(old, old.replace('25', os.environ['K2_DIAG_TOPN']))
    if i == 28 and os.environ.get('K2_GPU_PROBE') == 'torch' and not os.environ.get('K2_STOP_AFTER'):
        # Node with an NVML driver/library mismatch: nvidia-smi fails while CUDA works. Read the name through torch in a
        # child process, so the parent still has no CUDA context before Engine2 (as the cell requires).
        old = "['nvidia-smi', '--query-gpu=name', '--format=csv,noheader']"
        assert source.count(old) == 1
        source = source.replace(old, "[__import__('sys').executable, '-c', 'import torch; print(torch.cuda.get_device_name(0))']")
    if i in (36, 37) and os.environ.get('K2_GEN_CFG'):
        # Type-3 experiment: wider class-3 derivative generation in the main engine, e.g. K2_GEN_CFG='gen_n_analog=20,...'.
        old = 'EngineCfg(generate=True)'
        assert source.count(old) >= 1
        source = source.replace(old, f"EngineCfg(generate=True, {os.environ['K2_GEN_CFG']})")
    if i == 34 and os.environ.get('K2_PUBCHEM_EXCLUDE'):
        # K7 type-3 bench: the PubChem channel must not see the withheld truths. Append a wrapper to probe_core2.py that
        # drops window SMILES whose exact string, raw InChIKey14 or metric identity belongs to the withheld set.
        anchor = ".write(CORE + V17_PATCH)\n"
        assert source.count(anchor) == 1
        wrapper = (
            "\nimport json as _k7json\n"
            f"_K7 = _k7json.load(open({os.environ['K2_PUBCHEM_EXCLUDE']!r}))\n"
            "_K7_SMILES = set(_K7['smiles']); _K7_KEYS = set(_K7['raw']) | set(_K7['metric'])\n"
            "_k7_orig_window_bundle = _window_bundle\n"
            "def _window_bundle(target):\n"
            "    smis, priors = _k7_orig_window_bundle(target)\n"
            "    Chem = _W['Chem']; keep = []\n"
            "    for i, s in enumerate(smis):\n"
            "        if s in _K7_SMILES:\n"
            "            continue\n"
            "        m = Chem.MolFromSmiles(s)\n"
            "        if m is not None and Chem.MolToInchiKey(m)[:14] in _K7_KEYS:\n"
            "            continue\n"
            "        keep.append(i)\n"
            "    if len(keep) < len(smis):\n"
            "        print('K7_PC_FILTERED', len(smis) - len(keep), flush=True)\n"
            "    idx = np.asarray(keep, np.int64)\n"
            "    return [smis[i] for i in keep], {k: np.asarray(v)[idx] for k, v in priors.items()}\n")
        source = source.replace(anchor, anchor + f"open({str(out/'probe_core2.py')!r}, 'a').write({wrapper!r})\n")
    if i in (32, 34) and os.environ.get('K2_REUSE_CHANNELS'):
        # GPU phase: reuse Engine2 / PubChem channel lists computed by the CPU phase instead of re-running them.
        source = ("import subprocess as _k2sp, shutil as _k2sh\n"
                  "from pathlib import Path as _k2P\n"
                  "_k2_real_run = getattr(_k2sp, '_k2_real_run', _k2sp.run); _k2sp._k2_real_run = _k2_real_run\n"
                  "def _k2_run(cmd, *a, **k):\n"
                  "    names = {'eng_runner.py': 'eng_lists.json', 'pc_runner.py': 'pc_lists.json'}\n"
                  "    hit = [n for s in map(str, cmd) for b, n in names.items() if s.endswith(b)]\n"
                  "    if hit:\n"
                  "        dst = next(str(x) for x in cmd if str(x).endswith(hit[0]))\n"
                  f"        src = _k2P({os.environ['K2_REUSE_CHANNELS']!r}) / hit[0]\n"
                  "        assert src.is_file(), f'missing precomputed {src}'\n"
                  "        _k2sh.copy2(src, dst); print('K2 reused precomputed', src, flush=True)\n"
                  "        return _k2sp.CompletedProcess(cmd, 0, 'K2 reused ' + str(src), '')\n"
                  "    return _k2_real_run(cmd, *a, **k)\n"
                  "_k2sp.run = _k2_run\n") + source
    if i == 32:
        # Bound Engine2 workers so parallel replays do not oversubscribe the node (default: all cores, as upstream).
        assert source.count('workers=os.cpu_count()') == 1
        source = source.replace('workers=os.cpu_count()', 'workers=int(os.environ.get("K2_ENGINE2_WORKERS", os.cpu_count()))')
    if i == 32 and os.environ.get('K2_RANKER_CACHE'):
        # Opt-in: reuse Codex's validated Engine2 ranker cache (job 2720); writes eng/ranker_cache_audit.json.
        from patch_k2_ranker_cache import patch_cell
        source = patch_cell(source, os.environ['K2_RANKER_CACHE'])
    if catalog_contract is not None and i == 32:
        anchor = 'for _n, _src in ENG_FILES.items():'
        assert source.count(anchor) == 1
        audit = out/'engine2_catalog_guard_audit.json'
        lines = ['import json as _k2json, atexit as _k2atexit, sys as _k2sys',
                 'from casmi26.catalog_exclusion import install_engine2_pool_guard',
                 f'ENGINE2_CATALOG_GUARD = install_engine2_pool_guard(_k2sys.modules[__name__], _k2json.load(open({str(catalog_contract)!r})))',
                 f'_k2atexit.register(lambda: open({str(audit)!r}, "w").write(_k2json.dumps(ENGINE2_CATALOG_GUARD.audit(), default=str)))']
        hook = (
            "_k2s = ENG_FILES['casmi_engine.py']; _k2a = 'POOL = build_pool(L, workers)'\n"
            "assert _k2s.count(_k2a) == 1, 'engine2 hook anchor'\n"
            "_k2p = _k2s.index(_k2a); _k2ind = _k2s[_k2s.rfind(chr(10), 0, _k2p) + 1:_k2p]\n"
            f"_k2h = ''.join(chr(10) + _k2ind + _l for _l in {lines!r})\n"
            "ENG_FILES['casmi_engine.py'] = _k2s[:_k2p + len(_k2a)] + _k2h + _k2s[_k2p + len(_k2a):]\n"
            "print('K2 engine2 catalog guard injected', flush=True)\n")
        source = source.replace(anchor, hook + anchor)
    if catalog_contract is not None and i == 32 and os.environ.get('K2_CATALOG_IDENTITY_LOOKUP'):
        # Opt-in: Codex's fast catalog guard (exhaustively equal decisions, job 2727); same install signature.
        from patch_k2_fast_guards import patch_cell as _fast_guard_patch
        source = _fast_guard_patch(i, source)
    if catalog_contract is not None and i == 34 and 'pubchem_gate_policy' in json.loads(Path(catalog_contract).read_text()):
        from casmi26.pubchem_source_patch import patch_pubchem_cell
        source = patch_pubchem_cell(source, str(catalog_contract))
    if catalog_contract is not None and i == 37:
        anchor = "P = Pool('work')"
        assert source.count(anchor) == 1
        source = source.replace(anchor, anchor + "\nimport json as _k2json\nfrom casmi26.catalog_exclusion import install_main_pool_guard\n"
                                f"MAIN_CATALOG_GUARD = install_main_pool_guard(P, _k2json.load(open({str(catalog_contract)!r})))\n"
                                "print('K2 main catalog guard installed', flush=True)\n")
    if i == 39:
        anchor = '    if POOLPOP_MU > 0 and len(scs) > 1:'
        assert source.count(anchor) == 1
        source = source.replace(anchor, "    _K2_MAIN_ORIGIN[str(mid)] = dict(zip(smis, pids_))\n" + anchor)
        source = '_K2_MAIN_ORIGIN = {}\n' + source
        # Snapshot before the forward-model rerank of cell 41 truncates BASE to 25 rows without scores.
        source += "\n_K2_BASE_PRE = {str(k): (list(v[0]), list(v[3]) if len(v) > 3 else None) for k, v in BASE.items()}\n"
    if i == 41:
        source += "\n_K2_BASE_POST = {str(k): (list(v[0]), None) for k, v in BASE.items()}\n"
    if i == 48 and os.environ.get('K2_REUSE_CHANNELS'):
        # Withheld catalogs can leave Engine2 legitimately empty for a query (certified by the CPU-phase log in
        # k2_reuse_coverage.json); the final pass already reads ENG.get(mid, {}), only its coverage assert needs them.
        anchor = "assert _active <= set(map(str, ENG)), 'Engine 2 did not cover all active molecules'"
        assert source.count(anchor) == 1
        source = source.replace(anchor, (
            f"_k2_cov = json.loads(open({str(out/'k2_reuse_coverage.json')!r}).read())\n"
            "assert _k2_cov['eng_completed'], _k2_cov\n"
            "for _k2q in _k2_cov['eng_missing']:\n"
            "    ENG.setdefault(_k2q, {'smiles': []})\n"
            "print('K2 certified empty Engine2 entries', _k2_cov['eng_missing'], flush=True)\n") + anchor)
    if i == 26:
        begin = source.index("tag = f'cp{sys.version_info.major}{sys.version_info.minor}'")
        end_marker = "assert rdkit.__version__ == '2026.03.3'"
        end = source.index(end_marker)+len(end_marker)
        source = source[:begin]+"import rdkit; assert rdkit.__version__ == '2026.03.3'  # K2: venv RDKit, no pip bootstrap"+source[end:]
    if i == 36:
        anchor = "_EXTERNAL_REFERENCE_STATE = _build_external_reference_cache('work', TABLE, _EXTERNAL_REFERENCE_PINS)"
        assert source.count(anchor) == 1
        filt = (anchor+"\nfrom filter_k2_reference_cache import exclude_canonical_references\n"
                f"_EXTERNAL_REFERENCE_STATE = exclude_canonical_references(_EXTERNAL_REFERENCE_STATE, json.loads(open({str(contract_path)!r}).read()), "
                f"{str(out/'work_k2_filtered_external')!r}, {str(CROSSWALK)!r})\n"
                "print('K2 reference exclusion', _EXTERNAL_REFERENCE_STATE.get('k2_reference_audit'), flush=True)\n")
        source = source.replace(anchor, filt)
    return source


def stage_export(scope, out, contract):
    """Every candidate of every stage list, with metric identity, plus the truth key per query."""
    import pandas as pd
    identity = scope['metric_identity']
    rows = []

    main_origin = scope.get('_K2_MAIN_ORIGIN', {})
    eng = {str(m): set(v.get('smiles', [])) for m, v in scope.get('ENG', {}).items()}
    pcs = {str(m): set(v.get('pc', [])) for m, v in scope.get('PC', {}).items()}

    def origin(mid, s):
        pid = main_origin.get(str(mid), {}).get(s)
        if pid is not None:
            return ('main_catalog' if pid >= 0 else 'generated'), pid
        if s in eng.get(str(mid), ()):
            return 'engine2', None
        if s in pcs.get(str(mid), ()):
            return 'pubchem_tier', None
        return 'unknown', None

    def add(mid, stage, smiles, scores=None):
        for rank, s in enumerate(smiles, 1):
            key = identity(s)
            org, pid = origin(mid, s)
            rows.append(dict(query_id=str(mid), stage=stage, rank=rank, smiles=s, candidate_key=key[0] if key else None,
                             score=float(scores[rank-1]) if scores is not None and rank-1 < len(scores) else None,
                             origin=org, pid=pid))
    for mid, v in scope.get('BASE', {}).items():
        add(mid, 'main', v[0], v[3] if len(v) > 3 else None)
    for name in ('pre', 'post'):
        for mid, (smis, scores) in scope.get(f'_K2_BASE_{name.upper()}', {}).items():
            add(mid, f'main_{name}_forward', smis, scores)
    for mid, v in scope.get('ENG', {}).items():
        add(mid, 'engine2', v.get('smiles', []))
    for mid, v in scope.get('PC', {}).items():
        add(mid, 'pubchem', v.get('pc', []))
    for mid, v in scope.get('PREFUSION_LISTS', {}).items():
        add(mid, 'prefusion', v)
    final = pd.read_csv(out/'submission.csv', dtype=str, keep_default_na=False)
    for mid, answer in final.itertuples(index=False):
        add(mid, 'final0465', answer.split(';'))
    frame = pd.DataFrame(rows)
    frame['truth_key'] = frame.query_id.map(contract['truth'])
    frame['is_truth'] = frame.candidate_key == frame.truth_key
    frame.to_parquet(out/'k2_stage_candidates.parquet', index=False)
    summary = frame.groupby('stage').apply(lambda g: dict(queries=g.query_id.nunique(), truth_present=int(g[g.is_truth].query_id.nunique())),
                                           include_groups=False).to_dict()
    (out/'k2_stage_summary.json').write_text(json.dumps(summary, indent=2))
    print('K2 STAGE EXPORT', summary, flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, required=True, help='local /kaggle/input mirror (competition = cohort)')
    p.add_argument('--contract', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--catalog-contract', type=Path, help='K2 catalog-withheld contract (proxy3)')
    a = p.parse_args()
    a.input, a.contract = a.input.resolve(), a.contract.resolve()
    catalog = a.catalog_contract.resolve() if a.catalog_contract else None
    raw = FROZEN.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FROZEN_SHA256
    out = a.output.resolve()
    assert not out.exists(), 'fresh output directory required'
    out.mkdir(parents=True)
    contract = json.loads(a.contract.read_text())
    sys.path[:0] = [str(ROOT/'artifacts/k2_replay/src'), str(ROOT/'scripts/cluster')]
    os.chdir(out)
    from IPython.display import display
    scope = {'__name__': '__main__', 'display': display}
    started = time.monotonic()
    nb = json.loads(raw)
    for i, c in enumerate(nb['cells']):
        if c['cell_type'] != 'code':
            continue
        source = patch(i, ''.join(c['source']), a.input, out, a.contract, catalog)
        (out/'cells').mkdir(exist_ok=True)
        (out/'cells'/f'cell-{i:02d}.py').write_text(source)
        print(f'K2 CELL {i} START {time.monotonic()-started:.0f}s', flush=True)
        exec(compile(source, f'pipeline_cell_{i}', 'exec'), scope)
        print(f'K2 CELL {i} DONE {time.monotonic()-started:.0f}s', flush=True)
        if i == 34 and os.environ.get('K2_REUSE_CHANNELS'):
            # Reused channel lists must cover every query of the contract (a missing channel is not coverage 0).
            queries = set(map(str, contract['truth']))  # query ids of the cohort contract
            eng_keys = set(map(str, scope.get('ENG', {}))); pc_keys = set(map(str, scope.get('PC', {})))
            coverage = dict(queries=len(queries), eng_missing=sorted(queries-eng_keys), pc_missing=sorted(queries-pc_keys))
            # eng_runner/pc_runner omit a query only when it has no candidates; that is a valid empty channel,
            # provided the CPU-phase subprocess completed and printed its list count (checked in the CPU log).
            cpu_log = Path(os.environ['K2_REUSE_CHANNELS']+'.log')
            log = cpu_log.read_text() if cpu_log.is_file() else ''
            coverage.update(eng_completed=f'engine lists {len(eng_keys)} ' in log, pc_completed=f'pubchem lists {len(pc_keys)} ' in log,
                            missing_status='empty_channel (no candidates produced by a completed subprocess)')
            (out/'k2_reuse_coverage.json').write_text(json.dumps(coverage, indent=2))
            assert coverage['eng_completed'] and coverage['pc_completed'], f'reused channel lists not certified by CPU log: {coverage}'
        if os.environ.get('K2_STOP_AFTER') and i >= int(os.environ['K2_STOP_AFTER']):
            (out/'k2_cpu_phase_done.json').write_text(json.dumps(dict(stopped_after_cell=i, seconds=time.monotonic()-started,
                eng_lists=(out/'eng_lists.json').is_file(), pc_lists=(out/'pc_lists.json').is_file())))
            print('K2 CPU PHASE DONE', flush=True)
            return
    assert scope['IS_RERUN'], 'cohort must run as a full rerun'
    assert int(scope['te'].molecule_id.nunique()) == contract['query_count']
    if catalog is not None:
        (out/'main_catalog_guard_audit.json').write_text(json.dumps(scope['MAIN_CATALOG_GUARD'].audit(), indent=2, default=str))
    from export_evidence import export
    export(scope, out)
    stage_export(scope, out, contract)
    reuse = os.environ.get('K2_REUSE_CHANNELS')
    if reuse:
        # Preserve the CPU-phase provenance (receipt, guard/cache/PubChem audits, source cells, log) next to the GPU run.
        import shutil
        dst = out/'cpu_phase'; dst.mkdir(exist_ok=True)
        src = Path(reuse)
        for f in list(src.glob('*.json')) + list((src/'eng').glob('*.json')):
            shutil.copy2(f, dst/(f.parent.name+'__'+f.name if f.parent != src else f.name))
        if (src/'cells').is_dir():
            shutil.copytree(src/'cells', dst/'cells', dirs_exist_ok=True)
        if Path(str(src)+'.log').is_file():
            shutil.copy2(str(src)+'.log', dst/'cpu_phase.log')
    (out/'k2_run_info.json').write_text(json.dumps(dict(frozen_sha256=FROZEN_SHA256, contract=str(a.contract),
        input=str(a.input), seconds=time.monotonic()-started,
        reference_audit=scope.get('_EXTERNAL_REFERENCE_STATE', {}).get('k2_reference_audit'),
        reused_channels_from=reuse), indent=2, default=str))
    print('K2 FINISHED', round(time.monotonic()-started), 's', flush=True)


if __name__ == '__main__':
    main()
