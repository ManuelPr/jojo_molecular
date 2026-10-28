import gzip
import importlib.util
import io
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("atlas_download", Path(__file__).resolve().parents[2] / "scripts/cluster/atlas_download.py")
download = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(download)


class Response(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {}


MGF = b"BEGIN IONS\nSMILES=CCO\n10 1\nEND IONS\n"


def test_unknown_length_obeys_byte_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(download.urllib.request, "urlopen", lambda *a, **k: Response(MGF * 100))
    result = download.fetch("C2H6O", tmp_path, 80)
    assert result["status"] == "too_large"
    assert not list(tmp_path.iterdir())


def test_html_and_truncated_mgf_are_not_cached(monkeypatch, tmp_path):
    for body in [b"<html>Error</html>", MGF.removesuffix(b"END IONS\n")]:
        monkeypatch.setattr(download.urllib.request, "urlopen", lambda *a, **k: Response(body))
        assert download.fetch("C2H6O", tmp_path, 1000)["status"] == "invalid_mgf"
        assert not list(tmp_path.iterdir())


def test_truncated_response_at_complete_block_is_not_cached(monkeypatch, tmp_path):
    monkeypatch.setattr(download.urllib.request, "urlopen", lambda *a, **k:
                        Response(MGF, {"Content-Length": str(len(MGF) * 2)}))
    assert download.fetch("C2H6O", tmp_path, 1000)["status"] == "invalid_mgf"
    assert not list(tmp_path.iterdir())


def test_download_receipt_and_cache_integrity(monkeypatch, tmp_path):
    monkeypatch.setattr(download.urllib.request, "urlopen", lambda *a, **k: Response(MGF))
    result = download.fetch("C2H6O", tmp_path, 1000)
    assert result["status"] == "ok" and result["raw_bytes"] == len(MGF)
    assert result["spectra"] == 1 and len(result["sha256"]) == 64
    assert download.fetch("C2H6O", tmp_path, 1000)["status"] == "cached"
    (tmp_path / "C2H6O.mgf.gz").write_bytes(gzip.compress(MGF)[:-8])
    with pytest.raises(EOFError):
        download.fetch("C2H6O", tmp_path, 1000)


def test_rejects_formula_path_traversal(tmp_path):
    with pytest.raises(ValueError, match="Invalid formula"):
        download.fetch("../C2H6O", tmp_path, 1000)
