import gzip

import numpy as np
import pyarrow.parquet as pq
import pytest
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

from casmi26.atlas import clean_peaks, convert_file, iter_mgf, read_exclusions
from casmi26.chemistry import canonical_inchikey14


def block(smiles="CCO", ce=10, adduct="[M+H]+", peaks="10 1\n20 2\n20 3\n30 1", extra=""):
    mol = Chem.MolFromSmiles(smiles)
    return (f"BEGIN IONS\nSMILES={smiles}\nINCHIKEY={Chem.MolToInchiKey(mol)}\n"
            f"FORMULA={rdMolDescriptors.CalcMolFormula(mol)}\nPEPMASS=100 999\n"
            f"ADDUCT={adduct}\nCOLLISION_ENERGY={ce}\n{extra}{peaks}\nEND IONS\n")


def source(tmp_path, content):
    path = tmp_path / "fixture.mgf.gz"
    path.write_bytes(gzip.compress(content.encode()))
    return path


def test_merge_duplicate_peaks_preserves_precision():
    mz, it = clean_peaks([(20, 2), (10, 1), (20, 3), (20.00001, 1),
                          (-1, 3), (30, float("nan")), (40, 0)])
    np.testing.assert_array_equal(mz, [10, 20, 20.00001])
    np.testing.assert_allclose(it, [.2, 1, .2])


def test_energy_quantiles_and_training_schema(tmp_path):
    path = source(tmp_path, "".join(block(ce=ce) for ce in [50, 10, 40, 20, 30]))
    result = convert_file(path, tmp_path / "out", quantiles=(0, .5, 1))
    rows = pq.read_table(result["output"]).to_pylist()
    assert sorted(r["collision_energy_ev"] for r in rows) == [10, 30, 50]
    assert all(r["precursor_mz"] == 100 and r["is_simulated"] for r in rows)
    assert all(r["smiles"] == r["normalized_smiles"] == "CCO" for r in rows)
    assert all(r["ms2_mzs"] == [10, 20, 30] for r in rows)
    assert result["counts"]["written_structures"] == 1
    assert convert_file(path, tmp_path / "out", quantiles=(0, .5, 1))["cache_hit"]


def test_tautomer_exclusion_uses_official_identity(tmp_path):
    keto, enol = "CC(C)=O", "CC(O)=C"
    assert canonical_inchikey14(keto) == canonical_inchikey14(enol)
    path = source(tmp_path, block(keto) + block(enol))
    report = convert_file(path, tmp_path / "excluded", excluded={canonical_inchikey14(keto)})
    assert report["counts"]["excluded_identity_spectra"] == 2
    assert report["counts"]["written_spectra"] == 0
    assert pq.read_table(report["output"]).num_rows == 0
    merged = convert_file(path, tmp_path / "merged")
    assert merged["counts"]["written_spectra"] == 1


def test_real_atlas_non_idempotent_identity_is_rejected(tmp_path):
    # C16H12O7 atlas example: default maxTransforms changes the selected tautomer
    # when prepare.py canonicalizes the exported canonical SMILES a second time.
    smiles = "O=C1CC=CC(c2oc3cc(O)cc(O)c3c(=O)c2O)C(=O)C1"
    path = source(tmp_path, block(smiles))
    report = convert_file(path, tmp_path / "out")
    assert report["counts"]["unstable_identity_structures"] == 1
    assert report["counts"]["written_spectra"] == 0
    assert report["unstable_identities"] == ["YYZRAUMZRSHSLQ"]


def test_cap_independent_of_file_order(tmp_path):
    content = [block(s) for s in ["CCO", "COC", "CCC", "CCN"]]
    path = source(tmp_path, "".join(content))
    first = convert_file(path, tmp_path / "first", max_structures=2)
    path = source(tmp_path, "".join(reversed(content)))
    second = convert_file(path, tmp_path / "second", max_structures=2)
    assert set(pq.read_table(first["output"])["inchikey14"].to_pylist()) == set(
        pq.read_table(second["output"])["inchikey14"].to_pylist())
    assert first["counts"]["cap_dropped_structures"] == 2


@pytest.mark.parametrize("bad", ["<html>error</html>", "BEGIN IONS\nSMILES=CCO\n", "END IONS\n"])
def test_broken_source_fails_without_publishing(tmp_path, bad):
    path = source(tmp_path, bad)
    with pytest.raises(ValueError):
        convert_file(path, tmp_path / "out")
    assert not list((tmp_path / "out").glob("*.parquet"))


def test_resume_rejects_configuration_change_and_corruption(tmp_path):
    path = source(tmp_path, block())
    out = tmp_path / "out"
    result = convert_file(path, out)
    with pytest.raises(ValueError, match="stale"):
        convert_file(path, out, seed=1)
    (out / "fixture.parquet").write_bytes(b"broken")
    with pytest.raises(ValueError, match="stale"):
        convert_file(path, out)
    fixed = convert_file(path, out, force=True)
    assert fixed["output_sha256"] == result["output_sha256"]


def test_unsupported_adduct_is_never_relabelled_positive(tmp_path):
    path = source(tmp_path, block(adduct="[M-H]-") + block(ce=float("nan")))
    report = convert_file(path, tmp_path / "out")
    assert report["counts"]["unsupported_adduct_spectra"] == 1
    assert report["counts"]["invalid_metadata_spectra"] == 1
    assert report["counts"]["written_spectra"] == 0


def test_exclusion_provenance_and_validation(tmp_path):
    path = tmp_path / "excluded.txt"
    key = canonical_inchikey14("CCO")
    path.write_text(f"# frozen identities\n{key}\n{key}\n")
    keys, sources = read_exclusions([path])
    assert keys == {key}
    assert sources[0]["identities"] == 1
    assert len(sources[0]["sha256"]) == 64
    path.write_text("invalid\n")
    with pytest.raises(ValueError, match="14-letter"):
        read_exclusions([path])


def test_selective_parser_skips_unselected_peak_materialization(tmp_path):
    path = source(tmp_path, block(peaks="unused nonnumeric") + block(ce=20))
    records = list(iter_mgf(path, selected={1}))
    assert len(records) == 1 and records[0][0] == 1
    assert len(records[0][2]) == 4
