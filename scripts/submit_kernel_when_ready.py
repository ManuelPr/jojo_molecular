"""Wait for a Kaggle notebook version, check its submission.csv, submit it once."""
import argparse
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
COMPETITION = 'enveda-CASMI26-molecule-id-mass-spectra'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kernel', required=True)
    p.add_argument('--version', type=int, required=True)
    p.add_argument('--message', required=True)
    p.add_argument('--tag', required=True, help='artifacts/kaggle/<tag>/ state directory')
    a = p.parse_args()
    from kaggle.api.kaggle_api_extended import KaggleApi
    import pandas as pd
    out = ROOT/'artifacts/kaggle'/a.tag
    out.mkdir(parents=True, exist_ok=True)
    statepath = out/'submission-state.json'
    old = json.loads(statepath.read_text()) if statepath.exists() else {}
    assert old.get('status') not in ['submitted', 'submit_started', 'submit_response_uncertain'], 'Reconcile prior mutation before restarting'
    api = KaggleApi()
    api.authenticate()
    state = dict(kernel=a.kernel, version=a.version, message=a.message, status='waiting_for_notebook')
    def save():
        state['updated_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        statepath.write_text(json.dumps(state, indent=2)+'\n')
    if any(r.description == a.message for r in api.competition_submissions(COMPETITION)):
        state.update(status='submitted', reconciled=True)
        save()
        return
    save()
    try:
        started = time.monotonic()
        while time.monotonic()-started < 32400:
            response = api.kernels_status(a.kernel)
            state['notebook_status'] = str(response.status)
            save()
            if 'COMPLETE' in str(response.status).upper():
                break
            if any(word in str(response.status).upper() for word in ['ERROR', 'CANCEL']):
                state.update(status='notebook_failed', failure_message=response.failure_message)
                save()
                return
            time.sleep(60)
        else:
            state['status'] = 'wait_timeout'
            save()
            return
        api.kernels_output(a.kernel, str(out), file_pattern=r'^submission\.csv$', page_size=500, quiet=True)
        frame = pd.read_csv(out/'submission.csv', dtype=str, keep_default_na=False)
        assert list(frame.columns) == ['molecule_id', 'smiles']
        assert frame.molecule_id.is_unique
        assert frame.smiles.map(lambda s: bool(s) and 1 <= len(s.split(';')) <= 25).all()
        state.update(status='submit_started', rows=len(frame))
        save()
        try:
            result = api.competition_submit_code('submission.csv', a.message, COMPETITION, kernel=a.kernel,
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
