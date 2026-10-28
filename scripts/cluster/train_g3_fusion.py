"""Fixed five-fold diagnostic fusion comparison on cached F0 candidate pools.

Fold assignment uses official truth identities only to prevent identity overlap.
Truth labels and identities never enter the model features. No model promotion.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = ['fusion_score', 'rank', 'ranker_score', 'library_confidence',
            'fingerprint_single_score', 'fingerprint_merged_score',
            'fingerprint_cosine', 'prior', 'iceberg_score',
            'glacier_real_score', 'glacier_proxy_score', 'eligible_proxy']


def assign_folds(truth, n=5):
    identities = sorted(set(truth.values()), key=lambda k: hashlib.sha256(k.encode()).hexdigest())
    mapping = {key: i % n for i, key in enumerate(identities)}
    return {query: mapping[key] for query, key in truth.items()}


def features(frame):
    out = frame[FEATURES].astype(float).replace([np.inf, -np.inf], np.nan)
    for name in FEATURES:
        out[name + '_missing'] = out[name].isna().astype(float)
    for name in ['iceberg_score', 'glacier_real_score', 'glacier_proxy_score']:
        group = frame.query_identity
        mean = out[name].groupby(group).transform('mean')
        std = out[name].groupby(group).transform('std').clip(lower=1e-6)
        out[name + '_query_z'] = (out[name] - mean) / std
    return out


def score_queries(frame, scores):
    ranked = frame.assign(prediction=scores).sort_values(
        ['query_identity', 'prediction', 'rank'], ascending=[True, False, True], kind='stable')
    ranked['output_rank'] = ranked.groupby('query_identity').cumcount() + 1
    truth = ranked.loc[ranked.true_candidate & ranked.output_rank.le(25)]
    return (1 / truth.set_index('query_identity').output_rank).reindex(
        sorted(frame.query_identity.unique()), fill_value=0.)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--control', type=Path, required=True)
    p.add_argument('--contract', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--neural-device', default='cuda')
    a = p.parse_args()
    import lightgbm as lgb
    import torch
    start = time.monotonic()
    a.output.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(2)
    torch.manual_seed(20261023)
    np.random.seed(20261023)
    if a.neural_device == 'cuda':
        assert torch.cuda.is_available(), 'No silent CPU fallback for GPU challenger'
    device = torch.device(a.neural_device)
    frame = pd.read_parquet(a.control / 'candidate_evidence.parquet').sort_values(
        ['query_identity', 'rank']).reset_index(drop=True)
    truth = json.loads(a.contract.read_text())['truth']
    assert set(frame.query_identity) == set(truth)
    assert not frame.duplicated(['query_identity', 'candidate_scorer_identity']).any()
    foldmap = assign_folds(truth)
    frame['fold'] = frame.query_identity.map(foldmap)
    x = features(frame)
    predictions = {name: np.full(len(frame), np.nan) for name in ['lightgbm', 'neural_listwise']}
    timings = []
    for fold in range(5):
        mask = frame.fold.ne(fold).to_numpy()
        # LambdaRank requires at least one positive candidate in a training group.
        covered = frame.groupby('query_identity').true_candidate.transform('any').to_numpy()
        train = mask & covered
        test = ~mask
        assert train.any() and test.any()
        assert set(frame.loc[train, 'query_identity']).isdisjoint(frame.loc[test, 'query_identity'])
        trainkeys = {truth[q] for q in frame.loc[train, 'query_identity']}
        assert trainkeys.isdisjoint({truth[q] for q in frame.loc[test, 'query_identity']})
        median = x.loc[train].median().fillna(0.)
        filled = x.fillna(median)
        mean = filled.loc[train].mean()
        std = filled.loc[train].std().fillna(1.).clip(lower=1e-4)
        matrix = ((filled - mean) / std).to_numpy(dtype=np.float32)
        assert np.isfinite(matrix).all()
        y = frame.true_candidate.to_numpy(dtype=np.int32)
        tick = time.monotonic()
        ranker = lgb.LGBMRanker(objective='lambdarank', n_estimators=120,
                               num_leaves=15, min_child_samples=40,
                               learning_rate=.03, reg_lambda=1.,
                               random_state=20261023 + fold, n_jobs=2, verbosity=-1)
        sizes = frame.loc[train].groupby('query_identity', sort=False).size().to_numpy()
        ranker.fit(matrix[train], y[train], group=sizes)
        predictions['lightgbm'][test] = ranker.predict(matrix[test])
        ranker.booster_.save_model(str(a.output / f'lightgbm-fold{fold}.txt'))
        lgb_seconds = time.monotonic() - tick
        # One padded batch of candidate lists; identity groups stay indivisible.
        groups = list(frame.loc[train].groupby('query_identity', sort=False).groups.values())
        width = max(map(len, groups))
        batch = np.zeros((len(groups), width, matrix.shape[1]), dtype=np.float32)
        valid = np.zeros((len(groups), width), dtype=bool)
        labels = np.zeros((len(groups), width), dtype=np.float32)
        for i, indices in enumerate(groups):
            indices = np.asarray(indices)
            batch[i, :len(indices)] = matrix[indices]
            valid[i, :len(indices)] = True
            labels[i, :len(indices)] = y[indices]
        labels /= labels.sum(axis=1, keepdims=True)
        torch.manual_seed(20261023 + fold)
        model = torch.nn.Sequential(torch.nn.Linear(matrix.shape[1], 64), torch.nn.SiLU(),
                                    torch.nn.Linear(64, 64), torch.nn.SiLU(),
                                    torch.nn.Linear(64, 1)).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=.002, weight_decay=.01)
        tensor = torch.as_tensor(batch, device=device)
        valid_tensor = torch.as_tensor(valid, device=device)
        targets = torch.as_tensor(labels, device=device)
        tick = time.monotonic()
        for _ in range(60):
            optimizer.zero_grad(set_to_none=True)
            logits = model(tensor).squeeze(-1).masked_fill(~valid_tensor, -1e4)
            loss = -(targets * torch.log_softmax(logits, dim=1)).sum(dim=1).mean()
            assert torch.isfinite(loss), 'Nonfinite listwise loss'
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
            optimizer.step()
        model.eval()
        with torch.inference_mode():
            predictions['neural_listwise'][test] = model(
                torch.as_tensor(matrix[test], device=device)).squeeze(-1).cpu().numpy()
        torch.save(model.state_dict(), a.output / f'neural-fold{fold}.pt')
        (a.output / f'preprocessing-fold{fold}.json').write_text(json.dumps(dict(
            features=list(x.columns), median=median.to_dict(), mean=mean.to_dict(), std=std.to_dict()), indent=2))
        timings.append(dict(fold=fold, lightgbm_seconds=lgb_seconds,
                            neural_seconds=time.monotonic()-tick, final_train_loss=float(loss.detach())))
    paired = pd.read_parquet(a.control / 'paired_queries.parquet')
    rr = paired.pivot(index='query_identity', columns='arm', values='rr_at25').sort_index()
    for name, values in predictions.items():
        assert np.isfinite(values).all()
        frame[name + '_oof_score'] = values
        rr[name] = score_queries(frame, values)
    baseline = rr.protonated_ice_fallback
    library = frame.groupby('query_identity').library_confidence.max().ge(.9).reindex(rr.index)
    results = {}
    for name in rr:
        delta = rr[name] - baseline
        rng = np.random.default_rng(20261023)
        boot = rng.choice(delta.to_numpy(), (5000, len(rr)), replace=True).mean(axis=1)
        results[name] = dict(mrr_at25=float(rr[name].mean()), delta=float(delta.mean()),
                             paired_diagnostic_bootstrap95=np.quantile(boot, [.025, .975]).tolist(),
                             regressions=int(delta.lt(0).sum()), improvements=int(delta.gt(0).sum()),
                             protected_library_count=int(library.sum()),
                             protected_library_delta=float(delta[library].mean()) if library.any() else None)
    frame.to_parquet(a.output / 'oof_candidate_scores.parquet', index=False)
    rr.to_csv(a.output / 'oof_query_rr.csv')
    report = dict(results=results, folds=foldmap, queries=len(rr), features=list(x.columns),
                  timings=timings, wall_seconds=time.monotonic()-start, neural_device=str(device),
                  peak_torch_vram_bytes=torch.cuda.max_memory_allocated() if device.type=='cuda' else None,
                  evidence_sha256=hashlib.sha256((a.control/'candidate_evidence.parquet').read_bytes()).hexdigest(),
                  model_promoted=False,
                  limitations=['Public-panel diagnostics; upstream pretrained exposure remains unverified.',
                               'Fixed five-fold out-of-fold comparison; no tuning or sealed evaluation.',
                               'Bootstrap describes query variation and omits fold-training dependence.',
                               'Learned challengers replace final heuristic order on the same candidate pool.'])
    (a.output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
