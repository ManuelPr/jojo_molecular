"""Experimental G3 inference: five saved LightGBM folds, arithmetic mean scores.

Only observable F0 evidence enters features. No validation labels are mounted.
"""
G3_BASE_FEATURES = ['fusion_score', 'rank', 'ranker_score', 'library_confidence',
                    'fingerprint_single_score', 'fingerprint_merged_score',
                    'fingerprint_cosine', 'prior', 'iceberg_score',
                    'glacier_real_score', 'glacier_proxy_score', 'eligible_proxy']
_G3_MAIN = {}


def _g3_capture(mid, candidates, matrix, names, scores, library, prior):
    import numpy as np
    index = {str(name): i for i, name in enumerate(names)}
    result = []
    for j, pid in enumerate(candidates.pid):
        row = dict(candidate_smiles=str(candidates.smiles[j]), ranker_score=float(scores[j]),
                   library_confidence=float(library), prior=float(prior[pid]) if 0 <= pid < len(prior) else None)
        for target, source in [('fingerprint_single_score', 'fz_single'),
                               ('fingerprint_merged_score', 'fz_merged'), ('fingerprint_cosine', 'fp_cos')]:
            value = matrix[j, index[source]] if source in index else np.nan
            row[target] = float(value) if np.isfinite(value) else None
        result.append(row)
    _G3_MAIN[str(mid)] = result


def _g3_features(frame):
    import numpy as np
    out = frame[G3_BASE_FEATURES].astype(float).replace([np.inf, -np.inf], np.nan)
    for name in G3_BASE_FEATURES:
        out[name + '_missing'] = out[name].isna().astype(float)
    for name in ['iceberg_score', 'glacier_real_score', 'glacier_proxy_score']:
        group = frame.query_identity
        mean = out[name].groupby(group).transform('mean')
        std = out[name].groupby(group).transform('std').clip(lower=1e-6)
        out[name + '_query_z'] = (out[name] - mean) / std
    return out


def _g3_predict(frame, directory, folds=range(5)):
    from pathlib import Path
    import json
    import numpy as np
    import pandas as pd
    import lightgbm as lgb
    x = _g3_features(frame)
    values = []
    for fold in folds:
        prep = json.loads((Path(directory)/f'preprocessing-fold{fold}.json').read_text())
        assert list(x.columns) == prep['features'], 'G3 feature contract changed'
        matrix = ((x.fillna(pd.Series(prep['median'])) - pd.Series(prep['mean']))
                  / pd.Series(prep['std'])).to_numpy(dtype=np.float32)
        assert np.isfinite(matrix).all(), 'G3 nonfinite feature matrix'
        model = lgb.Booster(model_file=str(Path(directory)/f'lightgbm-fold{fold}.txt'))
        values.append(model.predict(matrix, num_threads=2))
    return np.mean(values, axis=0)


def _g3_rows(mid, candidates, scores, scope):
    import math
    import numpy as np
    identity = scope['metric_identity']
    raw = {}
    for row in _G3_MAIN.get(str(mid), []):
        key = identity(row['candidate_smiles'])
        if key is not None:
            raw.setdefault(key[0], row)  # Same first representative as research export.
    group = scope['te'].loc[scope['te'].molecule_id.astype(str).eq(str(mid))]
    real_h = any(r.adduct == '[M+H]+' and r.ionization_mode == 'positive' for r in group.itertuples())
    eligible = not real_h and any(r.adduct in ('[M+NH4]+', '[M-H2O+H]+')
                                 and r.ionization_mode == 'positive' for r in group.itertuples())
    def lookup(table, smiles, source_key):
        value = table.get(str(mid), {}).get(smiles, table.get(str(mid), {}).get(source_key))
        return float(value) if value is not None and math.isfinite(float(value)) else None
    result = []
    for rank, (smiles, score) in enumerate(zip(candidates, scores), 1):
        key = identity(smiles)
        assert key is not None
        source_key = scope['chem'].score_key(smiles) or smiles
        row = dict(query_identity=str(mid), candidate_smiles=smiles,
                   candidate_scorer_identity=key[0], rank=rank, fusion_score=float(score),
                   eligible_proxy=eligible,
                   iceberg_score=lookup(scope['ICE_SCORES'], smiles, source_key),
                   glacier_real_score=lookup(scope['G3_GL_REAL_SCORES'], smiles, source_key),
                   glacier_proxy_score=lookup(scope['GL_SCORES'], smiles, source_key) if eligible else None)
        previous = raw.get(key[0], {})
        for name in ['ranker_score', 'library_confidence', 'fingerprint_single_score',
                     'fingerprint_merged_score', 'fingerprint_cosine', 'prior']:
            row[name] = previous.get(name, np.nan)
        result.append(row)
    assert len({r['candidate_scorer_identity'] for r in result}) == len(result)
    return result


def _g3_run(scope, directory):
    from pathlib import Path
    import hashlib
    import json
    import time
    import pandas as pd
    start = time.monotonic()
    directory = Path(directory)
    manifest = json.loads((directory/'g3_fusion_manifest.json').read_text())
    for name, expected in manifest['files_sha256'].items():
        assert Path(name).name == name
        assert hashlib.sha256((directory/name).read_bytes()).hexdigest() == expected, name
    control = Path('submission.csv').read_bytes()
    Path('submission_f0_control.csv').write_bytes(control)
    frame = pd.read_csv('submission.csv', dtype=str, keep_default_na=False)
    records = []
    for mid, engine in scope['ENG'].items():
        if str(mid) not in scope['PREFUSION_LISTS']:
            continue
        first = [s for s in scope['PREFUSION_LISTS'][str(mid)] if s and s != 'CCO']
        candidates, scores, _ = scope['metric_fusion'](
            first, engine.get('smiles', []), scope['metric_identity'],
            alpha=scope['ALPHA'], offset=scope['KRR'], limit=40)
        assert candidates, f'G3 empty candidate pool: {mid}'
        records.extend(_g3_rows(str(mid), candidates, scores, scope))
    evidence = pd.DataFrame(records)
    expected = set(scope['te'].molecule_id.astype(str))
    assert set(evidence.query_identity) == expected
    evidence['g3_score'] = _g3_predict(evidence, directory)
    answers = {}
    for mid, group in evidence.groupby('query_identity', sort=False):
        ranked = group.sort_values(['g3_score', 'rank'], ascending=[False, True], kind='stable')
        answers[str(mid)] = ';'.join(ranked.candidate_smiles.head(25))
    before = dict(zip(frame.molecule_id, frame.smiles))
    frame['smiles'] = [answers.get(mid, answer) for mid, answer in frame.itertuples(index=False)]
    assert frame.molecule_id.is_unique and frame.smiles.map(lambda s: bool(s) and 1 <= len(s.split(';')) <= 25).all()
    frame.to_csv('submission.csv', index=False)
    evidence.to_parquet('g3_candidate_scores.parquet', index=False)
    receipt = dict(kernel_recipe='F0 plus experimental G3 LightGBM five-fold mean',
                   output_rows=len(frame), processed_queries=len(expected),
                   changed_rows=sum(before[mid] != answer for mid, answer in answers.items()),
                   control_sha256=hashlib.sha256(control).hexdigest(),
                   submission_sha256=hashlib.sha256(Path('submission.csv').read_bytes()).hexdigest(),
                   model_manifest_sha256=hashlib.sha256((directory/'g3_fusion_manifest.json').read_bytes()).hexdigest(),
                   main_errors=int(scope['n_err']), inference_seconds=time.monotonic()-start,
                   experimental=True, validation='Five-fold ensemble deployment; its leaderboard performance is unmeasured.')
    Path('g3_submission_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print('G3_SUBMISSION_RECEIPT', json.dumps(receipt), flush=True)
    return receipt
