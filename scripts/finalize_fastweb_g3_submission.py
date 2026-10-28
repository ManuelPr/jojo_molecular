"""Wait for the authorized G3 notebook, audit its output, submit once."""
import argparse
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
KERNEL = 'mperni/casmi26-f0-g3-lightgbm-experiment'
COMPETITION = 'enveda-CASMI26-molecule-id-mass-spectra'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', type=int, required=True)
    p.add_argument('--conservative', action='store_true')
    a = p.parse_args()
    from kaggle.api.kaggle_api_extended import KaggleApi
    import pandas as pd
    kernel = 'mperni/casmi26-f0-g3-conservative-tail' if a.conservative else KERNEL
    bundle = 'fastweb_g3_conservative_bundle' if a.conservative else 'fastweb_g3_bundle'
    prefix = 'g3-conservative' if a.conservative else 'g3-lightgbm'
    out = ROOT/f'artifacts/kaggle/{prefix}-v{a.version}'
    out.mkdir(parents=True, exist_ok=True)
    statepath = out/'submission-state.json'
    old = json.loads(statepath.read_text()) if statepath.exists() else {}
    message = f'G3-LGBM-fivefold-v{a.version}: F0 fixed research mounts plus five-fold mean learned fusion; experimental user-authorized leaderboard test; upstream pretrained overlap unverified.'
    if a.conservative:
        message = f'G3-conservative-tail-v{a.version}: preserve F0 top1 and exact top25 candidate set; reorder tail by unchanged G3 fivefold ensemble. User-authorized experiment.'
    api = KaggleApi()
    api.authenticate()
    state = dict(kernel=kernel, version=a.version, status='waiting_for_notebook')
    def save():
        state['updated_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        statepath.write_text(json.dumps(state, indent=2)+'\n')
    found = [r for r in api.competition_submissions(COMPETITION) if r.description == message]
    if found:
        state.update(status='submitted', submission_ref=found[0].ref, reconciled=True)
        save()
        return
    assert old.get('status') not in ['submitted', 'submit_started', 'submit_response_uncertain'], 'Reconcile prior mutation before restarting'
    save()
    try:
        started = time.monotonic()
        while time.monotonic()-started < 32400:
            response = api.kernels_status(kernel)
            state['notebook_status'] = str(response.status)
            save()
            if 'COMPLETE' in str(response.status).upper():
                break
            if any(word in str(response.status).upper() for word in ['ERROR', 'CANCEL']):
                state.update(status='notebook_failed', failure_message=response.failure_message)
                save()
                return
            time.sleep(45)
        else:
            state['status'] = 'wait_timeout'
            save()
            return
        api.kernels_output(kernel, str(out), file_pattern=r'^(submission\.csv|g3_submission_receipt\.json)$', page_size=500, quiet=True)
        receipt = json.loads((out/'g3_submission_receipt.json').read_text())
        assert receipt['main_errors'] == 0 and receipt['processed_queries'] >= 12
        assert receipt['submission_sha256'] == hashlib.sha256((out/'submission.csv').read_bytes()).hexdigest()
        expected = json.loads((ROOT/'kaggle'/bundle/'build-manifest.json').read_text())
        assert receipt['model_manifest_sha256'] == expected['model_manifest_sha256']
        if a.conservative:
            assert receipt['top1_changes'] == 0 and receipt['candidate_set_changes'] == 0
            assert receipt['kernel_recipe'] == 'F0 top1 and exact top25 set preserved; G3 five-fold mean tail ordering'
        frame = pd.read_csv(out/'submission.csv', dtype=str, keep_default_na=False)
        assert list(frame.columns) == ['molecule_id', 'smiles']
        assert len(frame) == receipt['output_rows'] and frame.molecule_id.is_unique
        assert frame.smiles.map(lambda s: bool(s) and 1 <= len(s.split(';')) <= 25).all()
        state['status'] = 'submit_started'
        save()
        try:
            result = api.competition_submit_code('submission.csv', message, COMPETITION, kernel=kernel,
                                                 kernel_version=a.version, quiet=True)
        except Exception:
            state['status'] = 'submit_response_uncertain'
            save()
            raise
        state.update(status='submitted', submission_ref=result.ref)
        save()
        print(json.dumps(state), flush=True)
    except Exception as exc:
        state['error_type'] = type(exc).__name__
        if state['status'] != 'submit_response_uncertain':
            state['status'] = 'failed'
        save()
        raise


if __name__ == '__main__':
    main()
