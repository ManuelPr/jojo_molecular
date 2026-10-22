"""Exercise the exact GPU branch skipped by the library-confident public test."""
import ast
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def build():
    production=ROOT/'kaggle/expanded_glacier_submission_bundle'
    build=json.loads((production/'build_manifest.json').read_text())
    pinned=json.loads((ROOT/'configs/public_baseline_manifest.json').read_text())
    source=(ROOT/'third_party/public_four_channel/upstream.py').read_text()
    tree=ast.parse(source)
    finder=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='find_file')
    runtime=ast.parse((ROOT/'kaggle/expanded_glacier_submission.py').read_text())
    branch=next(n for n in runtime.body if isinstance(n,ast.If) and isinstance(n.test,ast.Name) and n.test.id=='items')
    fixture=json.loads((ROOT/'artifacts/pubchem_glacier/probe_v3/probe_input.json').read_text())
    constants='\n'.join(['PINNED_MANIFEST = '+repr(pinned),'SUBMISSION_CONFIG = '+repr(build['configuration']),
        'STACK_PROVENANCE_SHA256 = '+repr(build['stack_provenance_sha256']),
        'AUXILIARY_SHA256 = '+repr(build['auxiliary_sha256'])])+'\n'
    code=constants+(ROOT/'kaggle/public_baseline_preflight.py').read_text()+'\n'
    code+='import glob\nimport numpy as np\n'+ast.unparse(finder)+'\n'
    code+=(ROOT/'kaggle/forward_environment.py').read_text()+'\n'
    code+='items = '+repr(fixture)+'\nforward = {}\nmeta = {}\n'
    code+="Path('forward_input.json').write_text(json.dumps(items))\n"+ast.unparse(branch)+'\n'
    code+="Path('submission_branch_probe_complete.json').write_text(json.dumps({'complete':True,'scope':'compatibility only; not accuracy or production predictions','source_kernel_sha256':"+repr(build['kernel_sha256'])+",'forward_meta':meta,'forward_scores':forward},indent=2))\n"
    code+="print('[BRANCH PROBE] COMPLETE', json.dumps(meta), flush=True)\n"
    compile(code,'branch_probe.py','exec')
    output=ROOT/'kaggle/expanded_glacier_branch_probe_bundle';output.mkdir(exist_ok=True)
    (output/'branch_probe.py').write_text(code,encoding='utf-8')
    metadata=json.loads((production/'kernel-metadata.json').read_text())
    metadata.update(id='mperni/casmi26-expanded-glacier-branch-probe',title='CASMI26 Expanded GLACIER Branch Probe',code_file='branch_probe.py')
    (output/'kernel-metadata.json').write_text(json.dumps(metadata,indent=2))
    print(json.dumps({'probe_kernel_sha256':sha256(code.encode()).hexdigest(),'production_kernel_sha256':build['kernel_sha256']}))


if __name__=='__main__':
    build()
