"""Finalize the single F0 submission authorized on 23 October 2026.

No implicit retry of the submission mutation. Polling and output downloads are
read-only. Credentials are handled by Kaggle outside the repository.
"""
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
KERNEL = 'mperni/casmi26-f0-gu-v492-research-control'
COMPETITION = 'enveda-CASMI26-molecule-id-mass-spectra'
MESSAGE = 'F0-GuV492-r1-caa9feda: unchanged prediction code; pinned research mounts FPNet5/panel10/assets6/prior10/knowledge9; historical 0.464 mounts unverified. No G3 changes.'


def main():
    from kaggle.api.kaggle_api_extended import KaggleApi
    import pandas as pd
    out = ROOT / 'artifacts/kaggle/f0-gu-v1'
    out.mkdir(parents=True, exist_ok=True)
    state_path = out / 'finalizer-state.json'
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    state = dict(kernel=KERNEL, version=1, authorization='User 2026-10-23: farei la submission a priori',
                 status='waiting_for_notebook')
    def save():
        state['updated_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        state_path.write_text(json.dumps(state, indent=2) + '\n')
    api = KaggleApi()
    api.authenticate()
    # Reconcile first: a killed client must never cause a duplicate submission.
    existing = [r for r in api.competition_submissions(COMPETITION) if r.description == MESSAGE]
    if existing:
        state.update(status='submitted', submission_ref=existing[0].ref, reconciled=True)
        save()
        return
    if previous.get('status') in ('submit_started', 'submit_response_uncertain', 'submitted'):
        raise RuntimeError('Previous submit attempt requires reconciliation; refusing another mutation')
    save()
    started = time.monotonic()
    try:
        while time.monotonic() - started < 10800:
            response = api.kernels_status(KERNEL)
            status = str(response.status).upper()
            state['notebook_status'] = status
            save()
            if 'COMPLETE' in status:
                break
            if 'ERROR' in status or 'CANCEL' in status:
                state.update(status='notebook_failed', failure_message=response.failure_message)
                save()
                return
            time.sleep(45)
        else:
            state['status'] = 'notebook_wait_timeout'
            save()
            return
        if not all((out/name).is_file() for name in ['submission.csv', 'v43_execution_receipt.json']):
            api.kernels_output(KERNEL, str(out), file_pattern=r'^(submission\.csv|v43_execution_receipt\.json|e004_verification\.json|v43_mounted_input_hashes\.json)$', page_size=500, quiet=True)
        receipt = json.loads((out/'v43_execution_receipt.json').read_text())
        submission = out/'submission.csv'
        assert receipt['submission']['sha256'] == hashlib.sha256(submission.read_bytes()).hexdigest()
        assert receipt['main_errors'] == 0
        assert receipt['processed_molecules'] >= 12
        assert receipt['processed_molecules'] + receipt['placeholder_rows'] == receipt['input_molecules']
        frame = pd.read_csv(submission, dtype=str, keep_default_na=False)
        assert list(frame.columns) == ['molecule_id', 'smiles']
        assert frame.molecule_id.is_unique and len(frame) == receipt['input_molecules']
        assert frame.smiles.map(lambda s: 1 <= len(s.split(';')) <= 25 and all(s.split(';'))).all()
        state.update(status='submit_started', visible_receipt_sha256=hashlib.sha256((out/'v43_execution_receipt.json').read_bytes()).hexdigest(),
                     visible_processed=receipt['processed_molecules'], visible_placeholder_rows=receipt['placeholder_rows'])
        save()
        try:
            result = api.competition_submit_code('submission.csv', MESSAGE, COMPETITION,
                                                 kernel=KERNEL, kernel_version=1, quiet=True)
        except Exception:
            state['status'] = 'submit_response_uncertain'
            save()
            raise
        state.update(status='submitted', submission_ref=result.ref, message=result.message)
        save()
        print(json.dumps(state, indent=2), flush=True)
    except Exception as exc:
        state['error_type'] = type(exc).__name__
        if state['status'] != 'submit_response_uncertain':
            state['status'] = 'finalizer_failed'
        save()
        raise


if __name__ == '__main__':
    main()
