"""No network: exercise the at-most-once boundary with a fake Kaggle client."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest

path = Path(__file__).resolve().parents[2] / 'scripts/finalize_fastweb_f0_submission.py'
spec = importlib.util.spec_from_file_location('f0_finalizer', path)
finalizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finalizer)


def install_fake(monkeypatch, tmp_path):
    class FakeAPI:
        calls = 0

        def authenticate(self):
            pass

        def competition_submissions(self, competition):
            return []

        def kernels_status(self, kernel):
            return types.SimpleNamespace(status='COMPLETE')

        def kernels_output(self, kernel, directory, **kwargs):
            out = Path(directory)
            data = 'molecule_id,smiles\n' + ''.join(f'{i},CCO\n' for i in range(12))
            (out/'submission.csv').write_text(data)
            receipt = dict(submission=dict(sha256=hashlib.sha256(data.encode()).hexdigest()),
                           main_errors=0, processed_molecules=12, placeholder_rows=0, input_molecules=12)
            (out/'v43_execution_receipt.json').write_text(json.dumps(receipt))

        def competition_submit_code(self, *args, **kwargs):
            type(self).calls += 1
            assert kwargs['kernel_version'] == 1
            return types.SimpleNamespace(ref=999, message='fake submission')

    module = types.ModuleType('kaggle.api.kaggle_api_extended')
    module.KaggleApi = FakeAPI
    monkeypatch.setitem(sys.modules, 'kaggle.api.kaggle_api_extended', module)
    monkeypatch.setattr(finalizer, 'ROOT', tmp_path)
    return FakeAPI


def test_success_cannot_be_submitted_again_without_reconciliation(monkeypatch, tmp_path):
    client = install_fake(monkeypatch, tmp_path)
    finalizer.main()
    assert client.calls == 1
    with pytest.raises(RuntimeError, match='refusing another mutation'):
        finalizer.main()
    assert client.calls == 1


def test_uncertain_response_blocks_another_mutation(monkeypatch, tmp_path):
    client = install_fake(monkeypatch, tmp_path)
    state = tmp_path/'artifacts/kaggle/f0-gu-v1/finalizer-state.json'
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps(dict(status='submit_response_uncertain')))
    with pytest.raises(RuntimeError, match='refusing another mutation'):
        finalizer.main()
    assert client.calls == 0
