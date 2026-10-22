"""Build offline experimental kernels; never submit to the competition."""
import argparse
import ast
import base64
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build_probe(device='cpu'):
    stack = ROOT / 'artifacts/pubchem_glacier/research/stack/PROVENANCE.json'
    aux = ROOT / 'artifacts/pubchem_glacier/aux_wheels/auxiliary_manifest.json'
    constants = 'STACK_PROVENANCE_SHA256 = ' + repr(sha256(stack.read_bytes()).hexdigest()) + '\n'
    constants += 'AUXILIARY_SHA256 = ' + repr(sha256(aux.read_bytes()).hexdigest()) + '\n'
    constants += 'PROBE_DEVICE = ' + repr(device) + '\n'
    reference = ROOT / 'artifacts/pubchem_glacier/probe_v3/probe_raw.npz'
    constants += 'CPU_REFERENCE_B64 = ' + repr(base64.b64encode(reference.read_bytes()).decode() if device == 'cuda' else '') + '\n'
    code = constants + (ROOT / 'kaggle/forward_environment.py').read_text() + '\n' + (ROOT / 'kaggle/pubchem_glacier_probe.py').read_text()
    output = ROOT / 'kaggle/pubchem_glacier_probe_bundle'
    output.mkdir(exist_ok=True)
    compile(code, 'probe.py', 'exec')
    (output / 'probe.py').write_text(code, encoding='utf-8')
    meta = dict(id='mperni/casmi26-pubchem-glacier-probe', title='CASMI26 PubChem GLACIER Probe', code_file='probe.py', language='python', kernel_type='script', is_private=True, enable_gpu=device=='cuda', enable_internet=False,
                dataset_sources=['ahmedberatozer/casmi26-pubchem-tier', 'prvsiyan/casmi26-forward-reference-stack', 'mperni/casmi26-forward-aux-wheels/2'], competition_sources=[], kernel_sources=[], model_sources=[])
    (output / 'kernel-metadata.json').write_text(json.dumps(meta, indent=2))
    print(json.dumps({'bundle': str(output), 'kernel_sha256': sha256(code.encode()).hexdigest()}))


def build_experiment(scope='smoke', features_only=False):
    from build_public_baseline_bundle import extract_predictor
    pinned = json.loads((ROOT / 'configs/public_baseline_manifest.json').read_text())
    upstream = ROOT / 'third_party/public_four_channel/upstream.py'
    if sha256(upstream.read_bytes()).hexdigest() != pinned['upstream_sha256']:
        raise ValueError('Frozen baseline source changed')
    prefix, _ = extract_predictor(upstream.read_text())
    plan = json.loads((ROOT / 'configs/public_baseline_development.json').read_text())
    experiment = json.loads((ROOT / 'configs/pubchem_glacier_experiment.json').read_text())
    experiment['query_limit'] = 16 if scope == 'smoke' else 0
    experiment['features_only'] = features_only
    stack = ROOT / 'artifacts/pubchem_glacier/research/stack/PROVENANCE.json'
    aux = ROOT / 'artifacts/pubchem_glacier/aux_wheels/auxiliary_manifest.json'
    constants = '\n'.join([
        'PINNED_MANIFEST = ' + repr(pinned), 'DEVELOPMENT_PLAN = ' + repr(plan),
        'EXPERIMENT = ' + repr(experiment),
        'STACK_PROVENANCE_SHA256 = ' + repr(sha256(stack.read_bytes()).hexdigest()),
        'AUXILIARY_SHA256 = ' + repr(sha256(aux.read_bytes()).hexdigest()),
    ]) + '\n'
    modules = ['kaggle/public_baseline_preflight.py', 'kaggle/forward_environment.py',
               'src/casmi26/pubchem_retrieval.py', 'src/casmi26/forward_ranking.py']
    helpers = '\n'.join((ROOT / name).read_text() for name in modules)
    code = constants + helpers + '\n' + prefix + '\n' + (ROOT / 'kaggle/pubchem_glacier_runtime.py').read_text()
    compile(code, 'experiment.py', 'exec')
    output = ROOT / 'kaggle/pubchem_glacier_bundle'
    output.mkdir(exist_ok=True)
    (output / 'experiment.py').write_text(code, encoding='utf-8')
    kernel_slug = ('casmi26-pubchem-glacier-features-full' if scope=='full' else 'casmi26-pubchem-glacier-features') if features_only else 'casmi26-pubchem-glacier-experiment'
    title = ('CASMI26 PubChem GLACIER Features Full' if scope=='full' else 'CASMI26 PubChem GLACIER Features') if features_only else 'CASMI26 PubChem GLACIER Experiment'
    meta = dict(id='mperni/'+kernel_slug, title=title, code_file='experiment.py', language='python', kernel_type='script',
                is_private=True, enable_gpu=not features_only, enable_internet=False,
                dataset_sources=['prvsiyan/coconut-casmi26-candidates/2', 'prvsiyan/casmi26-fp-models-v2/1', 'prvsiyan/casmi26-ranker-features/6',
                                 'mperni/casmi26-baseline-assets', *experiment['asset_sources'].values()],
                competition_sources=['enveda-CASMI26-molecule-id-mass-spectra'], kernel_sources=[], model_sources=[])
    (output / 'kernel-metadata.json').write_text(json.dumps(meta, indent=2))
    manifest = {'scope': scope, 'configuration': experiment, 'kernel_sha256': sha256(code.encode()).hexdigest(),
                'stack_provenance_sha256': sha256(stack.read_bytes()).hexdigest(), 'auxiliary_sha256': sha256(aux.read_bytes()).hexdigest(),
                'baseline_upstream_sha256': pinned['upstream_sha256'], 'cohort_plan_sha256': plan['plan_sha256']}
    (output / 'build_manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'bundle': str(output), **manifest}, indent=2))


def build_forward(cache_root):
    cache_root = Path(cache_root)
    cache_manifest = cache_root / 'feature_manifest.json'
    cache = json.loads(cache_manifest.read_text())
    config = cache['configuration']
    for name, key in [('forward_input.json', 'forward_input_sha256'), ('experiment_candidates.json', 'candidates_sha256')]:
        if sha256((cache_root/name).read_bytes()).hexdigest() != cache[key]:
            raise ValueError('Local feature cache checksum mismatch')
    stack = ROOT / 'artifacts/pubchem_glacier/research/stack/PROVENANCE.json'
    aux = ROOT / 'artifacts/pubchem_glacier/aux_wheels/auxiliary_manifest.json'
    baseline = json.loads((ROOT/'configs/public_baseline_manifest.json').read_text())
    wheel = next(v['sha256'] for k,v in baseline['files'].items() if k.startswith('rdkit-'))
    constants = '\n'.join([
        'EXPERIMENT = ' + repr(config), 'CACHE_MANIFEST_SHA256 = ' + repr(sha256(cache_manifest.read_bytes()).hexdigest()),
        'STACK_PROVENANCE_SHA256 = ' + repr(sha256(stack.read_bytes()).hexdigest()),
        'AUXILIARY_SHA256 = ' + repr(sha256(aux.read_bytes()).hexdigest()), 'SCORER_WHEEL_SHA256 = '+repr(wheel),
    ]) + '\n'
    tree = ast.parse((ROOT/'kaggle/pubchem_glacier_runtime.py').read_text())
    functions = [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'scorer_key','save_json','rank_keys','evaluate'}]
    code = constants + (ROOT/'kaggle/forward_environment.py').read_text() + '\n' + (ROOT/'src/casmi26/forward_ranking.py').read_text()
    runtime = (ROOT/'kaggle/pubchem_glacier_forward.py').read_text()
    # Runtime defines scorer imports before using the shared function definitions.
    before, after = runtime.split('cache_manifest = find', 1)
    code += '\n' + before + '\n' + ast.unparse(ast.Module(body=functions,type_ignores=[])) + '\ncache_manifest = find' + after
    output = ROOT/'kaggle/pubchem_glacier_forward_bundle'
    output.mkdir(exist_ok=True)
    compile(code,'forward.py','exec')
    (output/'forward.py').write_text(code,encoding='utf-8')
    metadata = dict(id='mperni/casmi26-pubchem-glacier-forward',title='CASMI26 PubChem GLACIER Forward',code_file='forward.py',language='python',kernel_type='script',
                    is_private=True,enable_gpu=True,enable_internet=False,machine_shape='NvidiaTeslaT4',
                    dataset_sources=['mperni/casmi26-baseline-assets',config['asset_sources']['glacier_reference'],config['asset_sources']['auxiliary']],
                    competition_sources=[],kernel_sources=['mperni/casmi26-pubchem-glacier-features-full' if cache['query_count']==188 else 'mperni/casmi26-pubchem-glacier-features'],model_sources=[])
    (output/'kernel-metadata.json').write_text(json.dumps(metadata,indent=2))
    manifest=dict(kernel_sha256=sha256(code.encode()).hexdigest(),cache_manifest_sha256=sha256(cache_manifest.read_bytes()).hexdigest(),query_count=cache['query_count'])
    (output/'build_manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--experiment', choices=['smoke', 'full'])
    parser.add_argument('--features-only', action='store_true')
    parser.add_argument('--forward-cache')
    parser.add_argument('--probe-device', choices=['cpu', 'cuda'], default='cpu')
    arguments = parser.parse_args()
    if arguments.forward_cache:
        build_forward(arguments.forward_cache)
    elif arguments.experiment:
        build_experiment(arguments.experiment, features_only=arguments.features_only)
    else:
        build_probe(arguments.probe_device)
