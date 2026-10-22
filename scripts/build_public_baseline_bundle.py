"""Build a pinned, offline control from the credited historical public fork.

Never pushes or submits. The original ranking loop is lifted verbatim into a
function; validation masks and the output contract live outside that function.
"""
from hashlib import sha256
import json
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[1]


def extract_predictor(source: str) -> tuple[str, str]:
    prefix, rest = source.split("te = pq.read_table(TEST).to_pandas()", 1)
    loop = rest.split("rows, diag = [], []", 1)[1].split("# Build & strictly audit submission", 1)[0]
    predictor = "def public_predict(mols):\n    rows, diag = [], []\n" + textwrap.indent(loop, "    ") + "\n    return rows, diag\n"
    compile(predictor, "public_predict", "exec")
    return prefix, predictor


def build() -> Path:
    upstream_path = ROOT / "third_party/public_four_channel/upstream.py"
    source = upstream_path.read_text(encoding="utf-8")
    prefix, predictor = extract_predictor(source)
    assets = ROOT / "artifacts/public_baseline/assets"
    inventory = {}
    for folder in sorted(assets.iterdir()):
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix not in {".zip", ".whl"}:
                inventory[path.name] = {"sha256": sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}
    runtime_wheel = ROOT / "kaggle/assets/rdkit-2026.3.3-cp313-cp313-manylinux_2_28_x86_64.whl"
    inventory[runtime_wheel.name] = {"sha256": sha256(runtime_wheel.read_bytes()).hexdigest(), "bytes": runtime_wheel.stat().st_size}
    required = {"coco_fp.npy", "coco_mass.npy", "coco_meta.pkl", "fp_bits.npy", "rank_train.npz", "fp_single_s2.pt", "fp_merged_m1.pt"}
    if not required.issubset(inventory):
        raise ValueError(f"Missing assets: {required - inventory.keys()}")
    manifest = {
        "upstream_repository": "https://github.com/shiferaxa/casmi26",
        "upstream_commit": "c75b3fe090c80c8b56572a74d81447a30f9981b9",
        "upstream_path": "kaggle/fork_base/notebook.py",
        "upstream_sha256": sha256(upstream_path.read_bytes()).hexdigest(),
        "upstream_license": "Apache-2.0",
        "asset_license": "CC-BY-NC-SA-4.0; RDKit wheel retains upstream terms",
        "files": inventory,
        "ranking_changes": [],
        "wrapper_changes": ["fail-fast assets/channels", "development validation masks", "scorer deduplication without padding or added candidates"],
    }
    # Rebuild from the committed development-only snapshot, not private/sealed
    # artifacts. Altering this cohort requires an explicit config revision.
    payload = json.loads((ROOT / "configs/public_baseline_development.json").read_text())
    if set(payload) != {"identity_keys", "query_spectrum_ids", "plan_sha256"}:
        raise ValueError("Unexpected validation payload fields")
    if len(payload["identity_keys"]) != 188 or len(payload["query_spectrum_ids"]) != 876:
        raise ValueError("Frozen development cohort drift")
    config = ROOT / "configs/public_baseline_manifest.json"
    if json.loads(config.read_text()) != manifest:
        raise ValueError("Pinned source/assets changed; revise the manifest explicitly before creating a new control")
    bundle = ROOT / "kaggle/public_baseline_bundle"
    bundle.mkdir(parents=True, exist_ok=True)
    preflight = (ROOT / "kaggle/public_baseline_preflight.py").read_text(encoding="utf-8")
    runtime = (ROOT / "kaggle/public_baseline_runtime.py").read_text(encoding="utf-8")
    code = "PINNED_MANIFEST = " + repr(manifest) + "\nDEVELOPMENT_PLAN = " + repr(payload) + "\n" + preflight + "\n" + prefix + "\n" + predictor + "\n" + runtime
    compile(code, str(bundle / "public_baseline_kernel.py"), "exec")
    (bundle / "public_baseline_kernel.py").write_text(code, encoding="utf-8")
    metadata = {"id": "mperni/casmi26-public-baseline-control", "title": "CASMI26 Public Baseline Control", "code_file": "public_baseline_kernel.py", "language": "python", "kernel_type": "script", "is_private": True, "enable_gpu": False, "enable_internet": False,
                "dataset_sources": ["prvsiyan/coconut-casmi26-candidates/2", "prvsiyan/casmi26-fp-models-v2/1", "prvsiyan/casmi26-ranker-features/6", "mperni/casmi26-baseline-assets"], "competition_sources": ["enveda-CASMI26-molecule-id-mass-spectra"], "kernel_sources": [], "model_sources": []}
    (bundle / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"bundle": str(bundle), "source_hash": manifest["upstream_sha256"], "kernel_hash": sha256(code.encode()).hexdigest(), "development_identities": len(payload["identity_keys"]), "development_spectra": len(payload["query_spectrum_ids"]), "asset_count": len(inventory)}, indent=2))
    return bundle


if __name__ == "__main__":
    build()
