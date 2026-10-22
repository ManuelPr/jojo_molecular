"""Re-evaluate an immutable model score cache with the current fusion rules."""
import argparse
import ast
from functools import lru_cache
from hashlib import sha256
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
from rdkit import Chem
from rdkit.Chem.MolStandardize import rdMolStandardize
from casmi26.forward_ranking import fuse_forward, ranked_unique, reciprocal_rank, paired_bootstrap

ROOT=Path(__file__).resolve().parents[1]


def replay(features, source, output):
    features,source,output=Path(features),Path(source),Path(output)
    cache=json.loads((features/'feature_manifest.json').read_text())
    prior=json.loads((source/'experiment_report.json').read_text())
    if prior['cache_manifest_sha256']!=sha256((features/'feature_manifest.json').read_bytes()).hexdigest():
        raise ValueError('Prior GPU result uses a different cache')
    items=json.loads((features/'forward_input.json').read_text())
    raw=json.loads((source/'forward_scores.json').read_text())
    scores={i['id']:dict(zip(i['candidates'],raw[i['id']]['glacier'])) for i in items}
    records=json.loads((features/'experiment_candidates.json').read_text())
    tree=ast.parse((ROOT/'kaggle/pubchem_glacier_runtime.py').read_text())
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'scorer_key','rank_keys','evaluate'}]
    namespace=dict(globals(),EXPERIMENT=cache['configuration'])
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'fusion_replay','exec'),namespace)
    report=namespace['evaluate'](records,scores)
    report.update({k:v for k,v in prior.items() if k not in {'query_count','variants','per_query','weights','limitations'}})
    report['replay_note']='Variant-local forward budget enforced; GPU predictions reused unchanged'
    report['fusion_source_sha256']=sha256((ROOT/'kaggle/pubchem_glacier_runtime.py').read_bytes()).hexdigest()
    output.mkdir(parents=True,exist_ok=True)
    (output/'experiment_report.json').write_text(json.dumps(report,indent=2)+'\n')
    shutil.copyfile(source/'forward_scores.json',output/'forward_scores.json')
    print(json.dumps({k:v for k,v in report.items() if k in {'variants','replay_note'}},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--features',required=True)
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',required=True)
    a=parser.parse_args()
    replay(a.features,a.source,a.output)
