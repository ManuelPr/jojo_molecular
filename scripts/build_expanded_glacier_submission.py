"""Build a self-contained hidden-rerun-safe inference kernel; never submit."""
import ast
from hashlib import sha256
import json
from pathlib import Path
from build_public_baseline_bundle import extract_predictor

ROOT=Path(__file__).resolve().parents[1]


def build():
    pinned=json.loads((ROOT/'configs/public_baseline_manifest.json').read_text())
    source=(ROOT/'third_party/public_four_channel/upstream.py').read_text()
    if sha256((ROOT/'third_party/public_four_channel/upstream.py').read_bytes()).hexdigest()!=pinned['upstream_sha256']:
        raise ValueError('Baseline source drift')
    prefix,_=extract_predictor(source)
    device="dev = 'cuda' if torch.cuda.is_available() else 'cpu'"
    if prefix.count(device)!=1:
        raise ValueError('Unexpected fingerprint device setup')
    prefix=prefix.replace(device,"dev = 'cpu'")
    configuration={'candidate_pool':'train+COCONUT','prune80':False,'pubchem':False,
                   'forward_model':'GLACIER MassSpecGym','forward_top_k':40,'forward_weight':2.,
                   'library_gate':.9,'forward_batch_size':4,'fingerprint_device':'cpu',
                   'writer':'top25 raw then scorer identity dedup; no backfill',
                   'development_oof_mrr':.7736663207668064}
    stack=ROOT/'artifacts/pubchem_glacier/research/stack/PROVENANCE.json'
    aux=ROOT/'artifacts/pubchem_glacier/aux_wheels/auxiliary_manifest.json'
    constants='\n'.join(['PINNED_MANIFEST = '+repr(pinned),'SUBMISSION_CONFIG = '+repr(configuration),
        'STACK_PROVENANCE_SHA256 = '+repr(sha256(stack.read_bytes()).hexdigest()),
        'AUXILIARY_SHA256 = '+repr(sha256(aux.read_bytes()).hexdigest())])+'\n'
    tree=ast.parse((ROOT/'kaggle/pubchem_glacier_runtime.py').read_text())
    names={'scorer_key','save_json','evidence','score_variant','forward_spectra','forward_eligible'}
    helpers=ast.unparse(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]))
    imports='from functools import lru_cache\nfrom rdkit.Chem.MolStandardize import rdMolStandardize\n'
    code=constants+(ROOT/'kaggle/public_baseline_preflight.py').read_text()+'\n'+prefix+'\n'+imports+'\n'+helpers+'\n'
    code+=(ROOT/'kaggle/forward_environment.py').read_text()+'\n'+(ROOT/'src/casmi26/forward_ranking.py').read_text()+'\n'
    code+=(ROOT/'kaggle/expanded_glacier_submission.py').read_text()
    compile(code,'expanded_glacier.py','exec')
    output=ROOT/'kaggle/expanded_glacier_submission_bundle'
    output.mkdir(exist_ok=True)
    (output/'expanded_glacier.py').write_text(code,encoding='utf-8')
    metadata=dict(id='mperni/casmi26-expanded-glacier-submission',title='CASMI26 Expanded GLACIER Submission',
        code_file='expanded_glacier.py',language='python',kernel_type='script',is_private=True,
        enable_gpu=True,enable_internet=False,machine_shape='NvidiaTeslaT4',
        dataset_sources=['prvsiyan/coconut-casmi26-candidates/2','prvsiyan/casmi26-fp-models-v2/1',
                         'prvsiyan/casmi26-ranker-features/6','mperni/casmi26-baseline-assets',
                         'prvsiyan/casmi26-forward-reference-stack/2','mperni/casmi26-forward-aux-wheels/2'],
        competition_sources=['enveda-CASMI26-molecule-id-mass-spectra'],kernel_sources=[],model_sources=[])
    (output/'kernel-metadata.json').write_text(json.dumps(metadata,indent=2))
    manifest={'configuration':configuration,'kernel_sha256':sha256(code.encode()).hexdigest(),
              'upstream_sha256':pinned['upstream_sha256'],'stack_provenance_sha256':sha256(stack.read_bytes()).hexdigest(),
              'auxiliary_sha256':sha256(aux.read_bytes()).hexdigest(),
              'hidden_rerun':'reads actual test.parquet and sample; no prediction-cache parents or embedded test IDs'}
    (output/'build_manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2))
    return output


if __name__=='__main__':
    build()
