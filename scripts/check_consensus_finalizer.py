"""No-network safety checks for the single authorized submission finalizer."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import finalize_pubchem_consensus as worker


def check(fail_audit):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        state = root / 'artifacts/pubchem_consensus'; state.mkdir(parents=True)
        bundle = root / 'kaggle/pubchem_consensus_submission_bundle'; bundle.mkdir(parents=True)
        notebook = bundle / 'pubchem_consensus.ipynb'
        notebook.write_text(json.dumps(dict(cells=[dict(source=['pass'])])))
        calls = []
        def pull(kernel, path, metadata):
            Path(path).mkdir(); shutil.copyfile(notebook, Path(path) / 'server.ipynb')
        def download(*args, **kwargs):
            (state / f'output_v{worker.VERSION}').mkdir()
        def audit(*args, **kwargs):
            if fail_audit:
                raise RuntimeError('Injected audit failure')
            (state / f'output_v{worker.VERSION}/independent_audit.json').write_text(json.dumps(dict(passed=True, output_rows=400, replay_rows=400)))
        def submit(*args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(ref=123, message='fake receipt')
        api = SimpleNamespace(kernels_status=lambda k: SimpleNamespace(status='COMPLETE', failure_message=''),
                              kernels_pull=pull, kernels_output=download,
                              competition_submissions=lambda *a, **k: [], competition_submit_code=submit)
        with patch.multiple(worker, ROOT=root, STATE=state, BUILD_SHA=sha256(notebook.read_bytes()).hexdigest(),
                            DEADLINE=datetime(2099, 1, 1, tzinfo=timezone.utc)), \
             patch.object(worker, 'authenticate', return_value=api), \
             patch.object(worker.subprocess, 'run', side_effect=audit):
            if fail_audit:
                try: worker.main()
                except RuntimeError as e: assert str(e) == 'Injected audit failure'
                else: raise AssertionError('Audit failure was ignored')
                assert not calls and not (state / 'submit_intent.json').exists()
            else:
                worker.main()
                assert len(calls) == 1 and calls[0][1]['kernel_version'] == worker.VERSION
                try: worker.main()
                except RuntimeError as e: assert 'intent already exists' in str(e)
                else: raise AssertionError('Duplicate submission was allowed')
                assert len(calls) == 1


if __name__ == '__main__':
    check(True)
    check(False)
    print('PASS: failed audit prevents submit; successful audit submits once; repeat is blocked. No network calls made.')
