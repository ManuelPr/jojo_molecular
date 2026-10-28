import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

path = Path(__file__).resolve().parents[2] / 'scripts/cluster/train_g3_fusion.py'
spec = importlib.util.spec_from_file_location('g3_fusion', path)
g3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g3)


def test_identity_aliases_stay_in_same_fold():
    truth = {f'query{i}': f'identity{i // 2}' for i in range(20)}
    folds = g3.assign_folds(truth)
    assert len(set(folds.values())) == 5
    for i in range(0, 20, 2):
        assert folds[f'query{i}'] == folds[f'query{i+1}']


def test_features_ignore_truth_and_preserve_missing_evidence():
    frame = pd.DataFrame({name: [1., 2., np.nan] for name in g3.FEATURES})
    frame['query_identity'] = ['a', 'a', 'b']
    frame['true_candidate'] = [True, False, False]
    before = g3.features(frame)
    frame['true_candidate'] = ~frame.true_candidate
    pd.testing.assert_frame_equal(before, g3.features(frame))
    assert before.iceberg_score_missing.tolist() == [0., 0., 1.]
    assert pd.isna(before.iloc[2].iceberg_score)


def test_query_metric_keeps_missing_truth_in_denominator():
    frame = pd.DataFrame(dict(query_identity=['a', 'a', 'b'],
                              rank=[1, 2, 1], true_candidate=[False, True, False]))
    result = g3.score_queries(frame, np.array([3., 2., 1.]))
    assert result.to_dict() == {'a': .5, 'b': 0.}
