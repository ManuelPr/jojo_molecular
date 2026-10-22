"""Replay a prespecified conservative PubChem route on paired cached evidence."""

from hashlib import sha256
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ranking = load(ROOT / 'src/casmi26/forward_ranking.py')
selective = load(ROOT / 'src/casmi26/selective_pubchem.py')
reciprocal_rank, submission_smiles, paired_bootstrap = ranking.reciprocal_rank, ranking.submission_smiles, ranking.paired_bootstrap
eligible_for_pubchem, external_ranked_keys, insert_external = selective.eligible_for_pubchem, selective.external_ranked_keys, selective.insert_external


def evaluate():
    features = ROOT / 'artifacts/pubchem_glacier/features_full_v1'
    forward_root = ROOT / 'artifacts/pubchem_glacier/forward_full_v2'
    manifest = json.loads((features / 'feature_manifest.json').read_text())
    if not manifest['complete'] or manifest['query_count'] != 188:
        raise ValueError('Incomplete paired feature cache')
    for name, field in [('experiment_candidates.json', 'candidates_sha256'),
                        ('forward_input.json', 'forward_input_sha256')]:
        if sha256((features / name).read_bytes()).hexdigest() != manifest[field]:
            raise ValueError('Feature-cache checksum mismatch')
    report = json.loads((forward_root / 'experiment_report.json').read_text())
    if not report['complete'] or not report['forward_executed'] or report['cache_manifest_sha256'] != sha256((features / 'feature_manifest.json').read_bytes()).hexdigest():
        raise ValueError('Incomplete or mismatched forward run')
    records = json.loads((features / 'experiment_candidates.json').read_text())
    items = json.loads((features / 'forward_input.json').read_text())
    raw = json.loads((forward_root / 'forward_scores.json').read_text())
    forward = {item['id']: dict(zip(item['candidates'], raw[item['id']]['glacier'])) for item in items}
    output = {}
    for cohort, base_name, pubchem_name in [
        ('known_catalog', 'expanded', 'pubchem'),
        ('catalog_withheld_proxy', 'catalog_withheld_baseline', 'catalog_withheld_pubchem'),
    ]:
        before, after, changed, top1_changed, gated, truth_external = [], [], 0, 0, 0, 0
        for row in records:
            base = row['variants'][base_name]
            pubchem = row['variants'][pubchem_name]
            fw = forward.get(row['identity'], {})
            original = submission_smiles(base, fw, weight=2., forward_top_k=40, library_gate=.9)
            mapping = dict(zip(base['smiles'], base['keys']))
            mapping.update(zip(pubchem['smiles'], pubchem['keys']))
            external = external_ranked_keys(pubchem)
            truth_external += row['identity'] in {key for key, _ in external}
            active = eligible_for_pubchem(base, library_gate=.9, probability_gate=.3) and bool(external)
            if active:
                gated += 1
                revised = insert_external(original, external, mapping.get, slots=(4, 8, 12, 16, 20))
            else:
                revised = original
            original_keys = [mapping[s] for s in original]
            revised_keys = [mapping[s] for s in revised]
            before.append(reciprocal_rank(original_keys, row['identity']))
            after.append(reciprocal_rank(revised_keys, row['identity']))
            changed += revised_keys != original_keys
            top1_changed += bool(original_keys and revised_keys and original_keys[0] != revised_keys[0])
        output[cohort] = dict(query_count=len(records), before_mrr=float(np.mean(before)),
                              selective_mrr=float(np.mean(after)), gate_activated=gated,
                              changed_rows=changed, changed_top1=top1_changed,
                              truth_in_pubchem_candidates=truth_external,
                              paired_delta=paired_bootstrap(before, after))
    output['source'] = dict(feature_manifest_sha256=sha256((features / 'feature_manifest.json').read_bytes()).hexdigest(),
                            forward_report_sha256=sha256((forward_root / 'experiment_report.json').read_bytes()).hexdigest())
    destination = ROOT / 'artifacts/selective_pubchem/offline_replay.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    evaluate()
