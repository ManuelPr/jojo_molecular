"""Fail before expensive cluster runs when CUDA or the training input is unusable."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from casmi26.data import SHARED_COLUMNS, TRAIN_LABEL_COLUMNS


@pytest.fixture
def probe(monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts/cluster_preflight.py"
    spec = importlib.util.spec_from_file_location("cluster_preflight", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "version", lambda name: "2026.3.3" if name == "rdkit" else "1.0")
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        version=SimpleNamespace(cuda=None),
        cuda=SimpleNamespace(is_available=lambda: False),
    ))
    return module


def test_required_cuda_does_not_silently_fall_back_to_cpu(probe):
    result = probe.check_runtime(require_cuda=True)
    assert not result["passed"]
    assert not result["gpu_forward_backward_passed"]
    assert any("working CUDA GPU" in error for error in result["errors"])


def test_cpu_check_accepts_labelled_train_and_rejects_test_parquet(probe, tmp_path):
    train = tmp_path / "train.parquet"
    pq.write_table(pa.table({key: [None] for key in SHARED_COLUMNS | TRAIN_LABEL_COLUMNS}), train)
    result = probe.check_runtime(train=train)
    assert result["passed"]
    assert result["train"]["has_training_labels"]
    test = tmp_path / "test.parquet"
    pq.write_table(pa.table({key: [None] for key in SHARED_COLUMNS}), test)
    assert not probe.check_runtime(train=test)["passed"]


def test_missing_input_is_reported_before_training(probe, tmp_path):
    result = probe.check_runtime(train=tmp_path / "missing.parquet")
    assert not result["passed"]
    assert any("does not exist" in error for error in result["errors"])


def test_visible_gpu_with_broken_kernel_is_rejected(probe, monkeypatch):
    def fail_kernel(*args, **kwargs):
        raise RuntimeError("no kernel image is available for execution on the device")

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        version=SimpleNamespace(cuda="12.8"),
        cuda=SimpleNamespace(is_available=lambda: True, device_count=lambda: 1,
                             get_device_properties=lambda i: SimpleNamespace(name="GPU", total_memory=1024)),
        randn=fail_kernel,
    ))
    result = probe.check_runtime(require_cuda=True)
    assert result["cuda_available"]
    assert not result["passed"]
    assert "no kernel image" in result["torch_error"]
