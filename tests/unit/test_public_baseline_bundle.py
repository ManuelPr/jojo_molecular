"""Verify ranking-source parity and official output identity handling."""
import ast
import importlib.util
import json
from functools import lru_cache
from pathlib import Path

import pytest
import numpy as np
from rdkit import Chem
from rdkit.Chem.MolStandardize import rdMolStandardize
from casmi26.chemistry import neutral_mass_from_mz

ROOT = Path(__file__).resolve().parents[2]


def test_generated_predictor_keeps_upstream_ranking_loop():
    source = (ROOT / "third_party/public_four_channel/upstream.py").read_text(encoding="utf-8")
    original = next(node for node in ast.parse(source).body if isinstance(node, ast.For) and ast.unparse(node.target) == '(gi, (mid, sub))')
    spec = importlib.util.spec_from_file_location("builder", ROOT / "scripts/build_public_baseline_bundle.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    generated = ast.parse(builder.extract_predictor(source)[1])
    predictor = next(node for node in generated.body if isinstance(node, ast.FunctionDef) and node.name == "public_predict")
    copied = next(node for node in predictor.body if isinstance(node, ast.For))
    assert ast.dump(copied, include_attributes=False) == ast.dump(original, include_attributes=False)


def writer_namespace():
    tree = ast.parse((ROOT / "kaggle/public_baseline_runtime.py").read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {"scorer_key", "unique_predictions"}]
    namespace = {"Chem": Chem, "rdMolStandardize": rdMolStandardize, "lru_cache": lru_cache}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "writer_test", "exec"), namespace)
    return namespace


def test_writer_preserves_order_and_deduplicates_stereoisomers():
    ns = writer_namespace()
    guesses = ["C[C@H](O)C(=O)O", "CCO", "C[C@@H](O)C(=O)O"]
    assert ns["unique_predictions"](";".join(guesses)) == guesses[:2]


def test_writer_rejects_invalid_candidates_instead_of_filling():
    ns = writer_namespace()
    with pytest.raises(ValueError):
        ns["unique_predictions"]("CCO;invalid")


def test_bundle_does_not_embed_sealed_membership():
    payload = json.loads((ROOT / "configs/public_baseline_development.json").read_text())
    assert set(payload) == {"identity_keys", "query_spectrum_ids", "plan_sha256"}
    assert len(payload["identity_keys"]) == 188
    assert len(payload["query_spectrum_ids"]) == 876


@pytest.mark.parametrize("adduct", ["[M+H]+", "[M+NH4]+", "[M-H2O+H]+", "[M-2H2O+H]+", "[M+Na]+", "[M+K]+", "[M-H]-", "[M-H2O-H]-", "[M+CH2O2-H]-", "[M+Cl]-"])
def test_public_adduct_physics_agrees_with_local_conversion_within_001_ppm(adduct):
    tree = ast.parse((ROOT / "third_party/public_four_channel/upstream.py").read_text(encoding="utf-8"))
    names = {"MASS", "E", "PROTON", "H2O", "NH4", "FORMATE", "ACETATE", "ADDUCTS"}
    nodes = [node for node in tree.body if
             (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in node.targets)) or
             (isinstance(node, ast.FunctionDef) and node.name == "neutral_mass")]
    namespace = {"np": np}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "public_adducts", "exec"), namespace)
    multiplier, charge, delta = namespace["ADDUCTS"][adduct]
    mz = (450.5 * multiplier + delta) / charge
    actual = namespace["neutral_mass"](np.array([mz]), np.array([adduct]))[0]
    assert actual == pytest.approx(450.5, abs=1e-7)
    # Local Na/K constants are rounded: Na differs by 2.701e-6 Da.
    # Bound the physical discrepancy relative to the 8.5ppm retrieval window,
    # rather than claiming that the two implementations are byte-identical.
    local = neutral_mass_from_mz(mz, adduct)
    assert abs(actual - local) / actual * 1e6 < 0.01
