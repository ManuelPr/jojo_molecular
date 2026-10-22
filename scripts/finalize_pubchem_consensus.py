"""Finish the one explicitly authorized submission, with a persistent no-retry guard.

Runs using the Kaggle SDK interpreter; chemical audit uses the repository venv.
No new kernel is pushed. At most one submit request can be made per intent file.
"""
import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import subprocess
import time

from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.kaggle_creds import KaggleCredentials

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'artifacts/pubchem_consensus'
KERNEL = 'mperni/casmi26-pubchem-forward-consensus'
COMPETITION = 'enveda-CASMI26-molecule-id-mass-spectra'
VERSION = 2
BUILD_SHA = 'aa23745fbb0ca5955f5bf9eed8e0aaac3cf88af9fd84e42a0daeddb35f068586'
MESSAGE = 'PCFC-v2-aa23745f: v89 plus confident PubChem lead restoration on strict forward agreement; full400 audit passed; JSON identity repair.'
# User authorized the final submission for October 15, Europe/Rome (UTC+2).
DEADLINE = datetime(2026, 10, 15, 22, 0, tzinfo=timezone.utc)


def state(phase, **extra):
    value = dict(phase=phase, checked_at_utc=datetime.now(timezone.utc).isoformat(), **extra)
    temporary = STATE / 'finalizer_state.tmp'
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(STATE / 'finalizer_state.json')
    print(json.dumps(value), flush=True)


def authenticate():
    api = KaggleApi(); api.authenticate()
    credentials = KaggleCredentials.load(client=api.build_kaggle_client())
    credentials.refresh_access_token()
    api = KaggleApi(); api.authenticate()
    return api


def require_today():
    if datetime.now(timezone.utc) >= DEADLINE:
        raise RuntimeError('Authorized local calendar day ended; no submission sent.')


def main():
    STATE.mkdir(exist_ok=True)
    # An interrupted or ambiguous submission must be inspected, never retried.
    intent = STATE / 'submit_intent.json'
    if intent.exists():
        raise RuntimeError('Submission intent already exists; inspect official history instead of retrying.')
    bundle = ROOT / 'kaggle/pubchem_consensus_submission_bundle'
    notebook = bundle / 'pubchem_consensus.ipynb'
    assert sha256(notebook.read_bytes()).hexdigest() == BUILD_SHA
    api = authenticate(); refreshed = time.monotonic()
    errors = 0
    while True:
        require_today()
        try:
            if time.monotonic() - refreshed > 1200:
                api = authenticate(); refreshed = time.monotonic()
            status = api.kernels_status(KERNEL)
            phase = str(status.status).split('.')[-1]
            state('kernel_' + phase.lower(), kernel=KERNEL, error=status.failure_message)
            errors = 0
        except Exception:
            errors += 1
            if errors >= 3:
                raise
            time.sleep(60)
            api = authenticate(); refreshed = time.monotonic()
            continue
        if phase == 'COMPLETE':
            break
        if phase not in {'RUNNING', 'QUEUED'}:
            raise RuntimeError('Kernel did not complete: ' + phase)
        time.sleep(60)
    server = STATE / f'server_v{VERSION}'
    api.kernels_pull(KERNEL, str(server), metadata=True)
    pulled = next(server.glob('*.ipynb'))
    original = json.loads(notebook.read_text(encoding='utf-8'))
    actual = json.loads(pulled.read_text(encoding='utf-8'))
    assert [''.join(c['source']) for c in actual['cells']] == [''.join(c['source']) for c in original['cells']]
    output = STATE / f'output_v{VERSION}'
    state('downloading_outputs')
    api.kernels_output(KERNEL + f'/{VERSION}', str(output),
        file_pattern=r'^(reproduction_complete\.json|submission.*\.csv|e004_.*\.json|experiment_.*\.(json|csv)|retrieval_experiment_audit\.(json|csv)|pubchem_consensus_.*\.(json|csv))$',
        page_size=200)
    state('independent_audit')
    with (STATE / 'audit_stdout.log').open('w') as log:
        subprocess.run([str(ROOT / '.venv/Scripts/python.exe'),
                        'scripts/audit_pubchem_consensus_submission.py', str(output)],
                       cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)
    audit = json.loads((output / 'independent_audit.json').read_text())
    assert audit['passed'] and audit['output_rows'] == audit['replay_rows'] == 400
    require_today()
    api = authenticate()
    previous = api.competition_submissions(COMPETITION, page_size=100)
    matches = [s for s in previous if s.description == MESSAGE]
    if matches:
        state('already_submitted', refs=[str(s.ref) for s in matches])
        return
    # Exclusive durable intent precedes the single network mutation.
    with intent.open('x') as f:
        json.dump(dict(kernel=KERNEL, version=VERSION, message=MESSAGE,
                       notebook_sha256=BUILD_SHA, audit=audit,
                       authorized_by='User requested one more type-2 submission on 2026-10-15'), f, indent=2)
    state('submitting_once')
    response = api.competition_submit_code('submission.csv', MESSAGE, COMPETITION,
                                          kernel=KERNEL, kernel_version=VERSION)
    if not response.ref:
        raise RuntimeError('No submission reference returned; inspect history before any further action.')
    receipt = dict(ref=str(response.ref), message=response.message, kernel=KERNEL, version=VERSION,
                   submitted_at_utc=datetime.now(timezone.utc).isoformat())
    (STATE / 'submission_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    state('submitted', **receipt)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        state('stopped', error=str(error), intent_exists=(STATE / 'submit_intent.json').exists())
        raise
