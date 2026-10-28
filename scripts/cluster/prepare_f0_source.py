"""Extract the pinned F0 source and proxy modules without executing upstream code.

This is preparation, not an end-to-end reproduction or a training entry point.
Source attribution remains in the extracted modules and original notebook.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

SOURCE_SHA256 = "3b05fe5620f0bfe3acb319c782761acb61c61d283d8835b415a4d671cd841aa4"


def prepare(notebook: Path, output: Path) -> dict:
    actual = hashlib.sha256(notebook.read_bytes()).hexdigest()
    if actual != SOURCE_SHA256:
        raise ValueError(f"F0 source hash mismatch: {actual}")
    nb = json.loads(notebook.read_text())
    source = "\n\n".join("".join(c["source"]) for c in nb["cells"]
                           if c["cell_type"] == "code")
    tree = ast.parse(source)
    wanted = {"ENG_FILES", "N1_CORE_SRC", "N1_DRIVER_SRC",
              "N1_CORE_SHA256", "N1_DRIVER_SHA256"}
    values = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        name = getattr(node.targets[0], "id", None)
        if name not in wanted:
            continue
        value = node.value
        if (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                and isinstance(value.func.value, ast.Constant)
                and value.func.value.value == "" and value.func.attr == "join"
                and len(value.args) == 1 and not value.keywords):
            values[name] = "".join(ast.literal_eval(value.args[0]))
        else:
            values[name] = ast.literal_eval(value)
    if wanted != values.keys():
        raise ValueError(f"Missing source contracts: {wanted - values.keys()}")
    modules = dict(values["ENG_FILES"])
    modules["glb_core.py"] = values["N1_CORE_SRC"]
    modules["glb_driver.py"] = values["N1_DRIVER_SRC"]
    for filename, key in (("glb_core.py", "N1_CORE_SHA256"),
                          ("glb_driver.py", "N1_DRIVER_SHA256")):
        if hashlib.sha256(modules[filename].encode()).hexdigest() != values[key]:
            raise ValueError(f"Embedded module hash mismatch: {filename}")
    # Validate everything before writing any source. Never import these modules.
    for name, text in modules.items():
        if Path(name).name != name:
            raise ValueError(f"Unexpected module path: {name}")
        compile(text, name, "exec")
    output.mkdir(parents=True, exist_ok=True)
    for name, text in modules.items():
        (output / name).write_text(text)
    (output / "upstream_source.py").write_text(source)
    report = {
        "source_notebook": "guhongbin/casmi26-v492-dg-v19",
        "source_version": 1, "script_version_id": 361010883,
        "source_sha256": actual, "executed_upstream": False,
        "modules_sha256": {n: hashlib.sha256(t.encode()).hexdigest()
                           for n, t in modules.items()},
        "ready_for_end_to_end": False,
        "remaining": ["stage and audit historical input versions",
                      "adapt filesystem and isolate simulator dependencies",
                      "exclude evaluation identities from all references",
                      "export candidate/evidence tables before paired G1"],
    }
    (output / "source-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.notebook, args.output), indent=2))


if __name__ == "__main__":
    main()
