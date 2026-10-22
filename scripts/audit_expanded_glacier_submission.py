"""Independently validate the complete inference artifact before official submit."""
import argparse
import csv
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
import numpy as np
from rdkit import RDLogger
from casmi26.chemistry import canonical_inchikey14
from casmi26.forward_ranking import submission_smiles

ROOT=Path(__file__).resolve().parents[1]


def quiet_chemistry():
    RDLogger.DisableLog('rdApp.*')


def chemical_keys(smiles,workers=4):
    unique=sorted(set(smiles))
    with ProcessPoolExecutor(max_workers=workers,initializer=quiet_chemistry) as pool:
        keys=list(pool.map(canonical_inchikey14,unique,chunksize=32))
    return dict(zip(unique,keys))


def audit(output):
    output=Path(output)
    load=lambda name:json.loads((output/name).read_text())
    digest=lambda path:sha256(path.read_bytes()).hexdigest()
    report=load('submission_complete.json')
    features=load('inference_feature_manifest.json')
    build=json.loads((ROOT/'kaggle/expanded_glacier_submission_bundle/build_manifest.json').read_text())
    if not report['complete'] or report['kernel_sha256']!=build['kernel_sha256'] or report['configuration']!=build['configuration']:
        raise ValueError('Incomplete or changed inference configuration')
    if report['feature_manifest_sha256']!=digest(output/'inference_feature_manifest.json'):
        raise ValueError('Feature manifest checksum mismatch')
    for name,key in [('inference_candidates.json','candidates_sha256'),('forward_input.json','forward_input_sha256')]:
        if digest(output/name)!=features[key]:
            raise ValueError('Candidate/forward input checksum mismatch')
    with (ROOT/'data/sample_submission.csv').open(newline='') as stream:
        expected=[r['molecule_id'] for r in csv.DictReader(stream)]
    with (output/'submission.csv').open(newline='') as stream:
        reader=csv.DictReader(stream)
        if reader.fieldnames!=['molecule_id','smiles']:
            raise ValueError('Incorrect CSV columns')
        rows=list(reader)
    records=load('inference_candidates.json')
    if len(expected)!=400 or len(set(expected))!=400 or [r['molecule_id'] for r in rows]!=expected:
        raise ValueError('Incorrect rehearsal identity order/count')
    by_id={r['molecule_id']:r for r in records}
    if len(records)!=400 or set(by_id)!=set(expected) or report['query_count']!=400 or features['query_count']!=400:
        raise ValueError('Incomplete feature/inference records')
    items=load('forward_input.json')
    forward={}
    meta=report['forward_meta']
    if items:
        if meta['status']!='ok' or meta['errors'] or meta['device']!='cuda' or meta['items_done']!=len(items):
            raise ValueError('Forward model incomplete')
        raw=load('forward_scores.json')
        if set(raw)!={i['id'] for i in items}:
            raise ValueError('Incorrect forward identities')
        for i in items:
            scores=raw[i['id']]['glacier']
            if len(scores)!=len(i['candidates']) or not np.isfinite(scores).all():
                raise ValueError('Invalid forward scores')
            forward[i['id']]=dict(zip(i['candidates'],scores))
    config=report['configuration']
    # Normalize each unique output structure once, independently of the
    # producer's keys. Windows spawn workers only inside the guarded CLI entry.
    normalized=chemical_keys([s for row in rows for s in row['smiles'].split(';')])
    counts=[]
    for row in rows:
        record=by_id[row['molecule_id']]
        variant=record['variant']
        guesses=submission_smiles(variant,forward.get(row['molecule_id'],{}),weight=config['forward_weight'],
            forward_top_k=config['forward_top_k'],library_gate=config['library_gate'])
        if record['empty_window_fallback']:
            if variant['smiles']:
                raise ValueError('Incorrect fallback flag')
            guesses=['CCO']
        actual=row['smiles'].split(';')
        if actual!=guesses:
            raise ValueError('Production ranking/writer replay mismatch')
        keys=[normalized[s] for s in actual]
        if not 1<=len(keys)<=25 or None in keys or len(keys)!=len(set(keys)):
            raise ValueError('Invalid output molecular identities')
        counts.append(len(keys))
    if report['reference_spectra']!=2_539_608 or report['candidate_pool_count']!=712_199:
        raise ValueError('Incomplete inference reference universe')
    if not np.isfinite(report['elapsed_seconds']) or report['elapsed_seconds']>=32400:
        raise ValueError('Inference exceeds competition runtime limit')
    if report['submission_sha256']!=digest(output/'submission.csv'):
        raise ValueError('Submission checksum mismatch')
    if report['empty_window_fallbacks']!=sum(r['empty_window_fallback'] for r in records):
        raise ValueError('Incorrect fallback count')
    result={'passed':True,'query_count':400,'writer_replay_queries':400,'min_candidates':min(counts),
        'max_candidates':max(counts),'forward_queries':len(items),'empty_window_fallbacks':report['empty_window_fallbacks'],
        'protected_library_queries':sum(r['variant']['library_max']>=config['library_gate'] for r in records),
        'unique_output_smiles_chemically_checked':len(normalized),
        'elapsed_seconds':report['elapsed_seconds'],'submission_sha256':report['submission_sha256'],
        'kernel_sha256':report['kernel_sha256'],'official_submission_performed':False}
    (output/'independent_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args()
    RDLogger.DisableLog('rdApp.*')
    print(json.dumps(audit(args.output),indent=2))
