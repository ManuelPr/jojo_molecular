"""Validation and writer around public_predict; ranking remains upstream."""
from functools import lru_cache
import importlib.metadata
from rdkit.Chem.MolStandardize import rdMolStandardize

torch.set_num_threads(4)
if not HAVE_RDKIT or _MODEL is None or len(_MODEL[0]) != 1 or len(_MODEL[1]) != 1:
    raise RuntimeError("All four evidence channels are mandatory")
if NFEAT != 31 or len(RANKERS) != 8 or len(L["ik"]) != 2_539_608:
    raise RuntimeError("Public baseline shape contract mismatch")


@lru_cache(maxsize=100_000)
def scorer_key(smi):
    mol = Chem.MolFromSmiles(smi)
    if mol is None:
        raise ValueError("Invalid public candidate SMILES")
    Chem.RemoveStereochemistry(mol)
    mol = rdMolStandardize.TautomerEnumerator().Canonicalize(mol)
    key = Chem.MolToInchiKey(mol)[:14]
    if len(key) != 14:
        raise ValueError("Invalid public candidate identity")
    return key


def unique_predictions(text):
    seen, out = set(), []
    for smi in text.split(";"):
        key = scorer_key(smi)
        if key not in seen:
            seen.add(key)
            out.append(smi)
    if not 1 <= len(out) <= 25:
        raise RuntimeError("Invalid candidate count")
    return out


def save_json(name, value):
    Path(name).write_text(json.dumps(value, indent=2) + "\n")


def score_development():
    """Known-structure/own-spectra-hidden diagnostic on fixed development.

    All development raw-key aliases found in each 30ppm candidate window are
    masked jointly. Remaining aliases outside these windows are an explicit
    limitation; no claim of pristine pretrained-model/ranker holdout is made.
    """
    global rep, rep_key, rep_nm, lib_window
    wanted = {int(sid.rsplit("_", 1)[1]) - 1 for sid in DEVELOPMENT_PLAN["query_spectrum_ids"]}
    cols = ["inchikey14", "normalized_smiles", "precursor_mz", "adduct", "ionization_mode", "instrument_type", "collision_energy_ev", "ms2_mzs", "ms2_normalized_intensities"]
    query_rows, offset = [], 0
    for batch in pq.ParquetFile(TRAIN).iter_batches(batch_size=65536, columns=cols):
        selected = sorted(i - offset for i in wanted if offset <= i < offset + batch.num_rows)
        if selected:
            query_rows.extend(batch.take(pa.array(selected, type=pa.int64())).to_pylist())
        offset += batch.num_rows
    if len(query_rows) != len(wanted):
        raise RuntimeError("Development query extraction mismatch")
    query = pd.DataFrame(query_rows)
    query["nm"] = neutral_mass(query.precursor_mz.values.astype(np.float64), query.adduct.values)
    query["canonical_key"] = [scorer_key(smi) for smi in query.normalized_smiles]
    if set(query.canonical_key) != set(DEVELOPMENT_PLAN["identity_keys"]):
        raise RuntimeError("Development canonical identities mismatch")
    groups = list(query.groupby("canonical_key"))
    forbidden = set(query.inchikey14)
    window_keys = {}
    diagnostics = {}
    for key, sub in groups:
        mass = float(np.median(sub.nm))
        indices = pool.window(mass, CFG.PPM_FALLBACK)
        keys = {int(i): scorer_key(pool.smiles[i]) for i in indices}
        window_keys[key] = keys
        forbidden.update(pool.keys[i] for i, canonical in keys.items() if canonical == key)
        tight = pool.window(mass, CFG.PPM_WIN)
        used = tight if len(tight) else indices
        truth_indices = [i for i in used if keys[int(i)] == key]
        diagnostics[key] = {"window_candidates": len(used), "truth_in_window": bool(truth_indices)}
    original_window = lib_window
    originals = (rep, rep_key, rep_nm)
    allowed = ~np.isin(L["ik"], list(forbidden))

    def hidden_window(library, target, tolerance):
        indices = original_window(library, target, tolerance)
        return indices[allowed[indices]]

    mask = ~np.isin(rep_key, list(forbidden))
    rep, rep_key, rep_nm = rep[mask], rep_key[mask], rep_nm[mask]
    lib_window = hidden_window
    results = []
    try:
        for number, (key, sub) in enumerate(groups):
            rows, diag = public_predict([(key, sub)])
            guesses = unique_predictions(rows[0][1])
            keys = [scorer_key(smi) for smi in guesses]
            rank = keys.index(key) + 1 if key in keys else None
            item = {"identity": key, "rank": rank, "reciprocal_rank": 0.0 if rank is None else 1.0 / rank, **diagnostics[key]}
            results.append(item)
            if number % 10 == 0 or number == len(groups) - 1:
                save_json("public_validation_progress.json", {"completed": len(results), "expected": len(groups), "mrr_at_25": float(np.mean([x["reciprocal_rank"] for x in results]))})
                print("[CONTROL] Development", number + 1, "/", len(groups), flush=True)
    finally:
        rep, rep_key, rep_nm = originals
        lib_window = original_window
    summary = {"scope": "fixed development; own-identity spectral references hidden", "plan_sha256": DEVELOPMENT_PLAN["plan_sha256"], "query_count": len(results), "spectrum_count": len(query), "mrr_at_25": float(np.mean([r["reciprocal_rank"] for r in results])), "hit_at_1": float(np.mean([r["rank"] == 1 for r in results])), "recall_at_25": float(np.mean([r["rank"] is not None for r in results])), "truth_in_mass_window": float(np.mean([r["truth_in_window"] for r in results])), "reference_spectra_visible": int(allowed.sum()), "masked_raw_identity_keys": len(forbidden), "limitations": ["Unknown identity overlap in pretrained models and public ranker training", "Canonical alias search limited to query 30ppm windows", "Protocol reference universe differs from frozen E6; comparison is end-to-end, not an isolated ranking ablation"], "per_query": results}
    save_json("public_validation_report.json", summary)
    print("[CONTROL] Development MRR@25", summary["mrr_at_25"], flush=True)
    return summary


# Write the full inference output first; no validation mask applies here.
te = pq.read_table(TEST).to_pandas()
te["nm"] = neutral_mass(te.precursor_mz.values.astype(np.float64), te.adduct.values)
if not np.isfinite(te.nm).all():
    raise RuntimeError("Unsupported or invalid query neutral mass")
rows, diag = public_predict(list(te.groupby("molecule_id")))
raw = pd.DataFrame(rows, columns=["molecule_id", "smiles"])
raw.to_csv("public_raw_predictions.csv", index=False)
sample = pd.read_csv(SAMPLE, dtype={"molecule_id": str})
raw["molecule_id"] = raw.molecule_id.astype(str)
if raw.molecule_id.duplicated().any() or set(raw.molecule_id) != set(sample.molecule_id):
    raise RuntimeError("Prediction/sample ID mismatch")
raw["smiles"] = [";".join(unique_predictions(s)) for s in raw.smiles]
submission = sample[["molecule_id"]].merge(raw, on="molecule_id", how="left", validate="one_to_one")
if submission.smiles.isna().any():
    raise RuntimeError("Missing output")
submission.to_csv("submission.csv", index=False)
counts = submission.smiles.str.split(";").map(len)
save_json("public_inference_report.json", {"query_count": len(submission), "spectrum_count": len(te), "candidate_pool_count": len(pool.mass), "reference_spectra": len(L["ik"]), "analog_representatives": len(rep), "ranker_count": len(RANKERS), "fingerprint_models": len(_MODEL[0]) + len(_MODEL[1]), "min_candidates": int(counts.min()), "max_candidates": int(counts.max()), "raw_fallback_rows": len(rows) - len(diag), "submission_sha256": file_hash("submission.csv"), "elapsed_seconds": time.time() - T0, "diagnostics": diag, "versions": {name: importlib.metadata.version(name) for name in ["numpy", "pandas", "pyarrow", "rdkit", "scikit-learn", "numba", "torch"]}})
validation = score_development()
save_json("public_control_complete.json", {"complete": True, "validation_mrr_at_25": validation["mrr_at_25"], "elapsed_seconds": time.time() - T0, "submission_sha256": file_hash("submission.csv")})
