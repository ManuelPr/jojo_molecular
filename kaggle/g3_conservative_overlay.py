"""Keep F0 top one and candidate set; use G3 scores only to reorder its tail."""
def conservative_order(original, scores, identity):
    assert original and len(original) <= 25
    def score(smiles):
        key = identity(smiles)
        return scores.get(key[0], float('-inf')) if key is not None else float('-inf')
    return original[:1] + sorted(original[1:], key=score, reverse=True)


_g3_unrestricted_run = _g3_run


def _g3_run(scope, directory):
    from pathlib import Path
    import hashlib
    import json
    import pandas as pd
    receipt = _g3_unrestricted_run(scope, directory)
    control = pd.read_csv('submission_f0_control.csv', dtype=str, keep_default_na=False)
    evidence = pd.read_parquet('g3_candidate_scores.parquet')
    by_query = {str(mid): dict(zip(group.candidate_scorer_identity, group.g3_score))
                for mid, group in evidence.groupby('query_identity')}
    answers = []
    changed = 0
    for mid, answer in control.itertuples(index=False):
        original = answer.split(';')
        ranked = conservative_order(original, by_query.get(str(mid), {}), scope['metric_identity'])
        assert ranked[0] == original[0] and sorted(ranked) == sorted(original)
        value = ';'.join(ranked)
        changed += value != answer
        answers.append(value)
    control['smiles'] = answers
    control.to_csv('submission.csv', index=False)
    receipt.update(kernel_recipe='F0 top1 and exact top25 set preserved; G3 five-fold mean tail ordering',
                   changed_rows=changed, top1_changes=0, candidate_set_changes=0,
                   submission_sha256=hashlib.sha256(Path('submission.csv').read_bytes()).hexdigest(),
                   experimental=True)
    Path('g3_submission_receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print('G3_CONSERVATIVE_RECEIPT', json.dumps(receipt), flush=True)
    return receipt
