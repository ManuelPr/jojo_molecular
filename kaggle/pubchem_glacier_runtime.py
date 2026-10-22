"""Paired development ablations; explicit candidate-source holdout proxy."""
from functools import lru_cache
from rdkit.Chem.MolStandardize import rdMolStandardize
import hashlib
import importlib.metadata
import gc
import json
import time

torch.set_num_threads(4)
if _MODEL is None or len(_MODEL[0]) != 1 or len(_MODEL[1]) != 1 or len(RANKERS) != 8:
    raise RuntimeError('Frozen baseline evidence channels missing')
if len(L['ik']) != 2_539_608:
    raise RuntimeError('Baseline spectral library drift')


@lru_cache(maxsize=100_000)
def scorer_key(smi):
    mol = Chem.MolFromSmiles(smi)
    if mol is None:
        raise ValueError('Invalid candidate SMILES')
    Chem.RemoveStereochemistry(mol)
    mol = rdMolStandardize.TautomerEnumerator().Canonicalize(mol)
    key = Chem.MolToInchiKey(mol)[:14]
    if len(key) != 14:
        raise ValueError('Invalid scorer identity')
    return key


def save_json(name, value):
    Path(name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def development_query():
    wanted = {int(sid.rsplit('_', 1)[1]) - 1 for sid in DEVELOPMENT_PLAN['query_spectrum_ids']}
    cols = ['inchikey14', 'normalized_smiles', 'precursor_mz', 'adduct', 'ionization_mode', 'instrument_type', 'collision_energy_ev', 'ms2_mzs', 'ms2_normalized_intensities']
    selected_rows, offset = [], 0
    for batch in pq.ParquetFile(TRAIN).iter_batches(batch_size=65536, columns=cols):
        positions = sorted(i-offset for i in wanted if offset <= i < offset + batch.num_rows)
        if positions:
            selected_rows.extend(batch.take(pa.array(positions, type=pa.int64())).to_pylist())
        offset += batch.num_rows
    if len(selected_rows) != len(wanted):
        raise RuntimeError('Development spectrum extraction mismatch')
    frame = pd.DataFrame(selected_rows)
    frame['nm'] = neutral_mass(frame.precursor_mz.values.astype(np.float64), frame.adduct.values)
    frame['canonical_key'] = [scorer_key(s) for s in frame.normalized_smiles]
    if set(frame.canonical_key) != set(DEVELOPMENT_PLAN['identity_keys']):
        raise RuntimeError('Development identities changed')
    return frame


def evidence(sub):
    mass = float(np.median(sub.nm))
    spectra = [(r.ms2_mzs, r.ms2_normalized_intensities) for r in sub.itertuples()]
    direct = lib_sim(L, spectra, mass)
    analogs = analog_sim(L, spectra, mass, rep, rep_key, rep_nm)
    ids, similarities = [], []
    for key, similarity in analogs:
        index = pool.k2i.get(key, -1)
        if index >= 0:
            ids.append(index); similarities.append(similarity)
    analog_fp = pool.fps(np.asarray(ids)) if ids else None
    logits = model_logits(sub)
    if logits is None or not np.isfinite(logits).all():
        raise RuntimeError('Missing fingerprint logits')
    return mass, spectra, direct, analog_fp, np.asarray(similarities, np.float32), logits


def coarse_prune(indices, direct, mass, limit=80):
    if len(indices) <= limit:
        return indices
    values = np.array([direct.get(pool.keys[i], 0.) for i in indices], np.float32)
    score = values * 100. - np.abs(pool.mass[indices] - mass)
    return indices[np.argsort(-score)[:limit]]


def score_variant(indices, external, sub, ev, fragment_cache):
    mass, spectra, direct, afp, similarity, logits = ev
    smis = [str(pool.smiles[i]) for i in indices]
    keys = [scorer_key(s) for s in smis]
    fingerprints = list(pool.fps(indices)) if len(indices) else []
    library_scores = [direct.get(pool.keys[i], 0.) for i in indices]
    masses = [float(pool.mass[i]) for i in indices]
    external_flags = [0.] * len(indices)
    seen = set(keys)
    added = 0
    for candidate in external:
        if candidate['key'] in seen:
            continue
        seen.add(candidate['key']); added += 1
        smis.append(candidate['entry'].smiles)
        keys.append(candidate['key'])
        fingerprints.append(candidate['fingerprint'])
        library_scores.append(0.)
        masses.append(candidate['entry'].mass)
        external_flags.append(1.)
    if not smis:
        return {'smiles': [], 'keys': [], 'probabilities': [], 'library_max': 0., 'added_pubchem': 0}
    ion_mode = float(np.mean([1. if m == 'positive' else -1. for m in sub.ionization_mode]))
    missing = list(dict.fromkeys(s for s in smis if s not in fragment_cache))
    if missing:
        fragment_cache.update(zip(missing, frag_scores(missing, spectra, ion_mode)))
    fragment = np.asarray([fragment_cache[s] for s in smis], np.float32)
    features = rank_features(np.stack(fingerprints), np.asarray(library_scores, np.float32), afp, similarity, logits, fragment)[:, :NFEAT]
    if not np.isfinite(features).all():
        raise RuntimeError('Nonfinite candidate feature')
    probabilities = rank_proba(features)
    return {'smiles': smis, 'keys': keys, 'probabilities': probabilities.tolist(),
            'library_max': float(max(library_scores)), 'added_pubchem': added,
            'features': features.tolist(), 'external_flags': external_flags,
            'mass_error_ppm': ((np.asarray(masses)-mass)/mass*1e6).tolist()}


def rank_keys(variant, forward=None, weight=0.):
    if not variant['smiles']:
        return []
    scores = variant['probabilities']
    if forward is not None:
        # The shared GPU cache is a compute optimization, not extra evidence.
        # Each ablation may use only the candidates it independently selected.
        selected = ranked_unique(variant['smiles'], scores, scorer_key, top_k=EXPERIMENT['forward_top_k'])
        permitted = {variant['smiles'][i] for i in selected}
        scores = fuse_forward(scores, [forward.get(s) if s in permitted else None for s in variant['smiles']], weight,
                              protected=variant['library_max'] >= EXPERIMENT['library_gate'])
    # Preserve the successful control's top25-then-deduplicate writer exactly.
    # Do not count a deduplication backfill change as a model improvement.
    order = np.argsort(-np.asarray(scores))[:25]
    return list(dict.fromkeys(variant['keys'][i] for i in order))


def forward_spectra(sub):
    result = []
    for row in sub.itertuples():
        values = np.asarray(row.collision_energy_ev if row.collision_energy_ev is not None else [], dtype=float).reshape(-1)
        values = values[np.isfinite(values)]
        # The original reference runner only supports positive protonated GLACIER queries.
        if row.ionization_mode != 'positive' or row.adduct != '[M+H]+' or not len(values):
            continue
        instrument = str(row.instrument_type).lower()
        token = 'Orbitrap' if 'orbitrap' in instrument else ('QTOF' if 'tof' in instrument else 'Unknown')
        result.append({'mz': np.asarray(row.ms2_mzs, float).tolist(), 'it': np.asarray(row.ms2_normalized_intensities, float).tolist(),
                       'precursor_mz': float(row.precursor_mz), 'adduct': row.adduct, 'ce': float(values.mean()),
                       'instrument': token, 'mode': row.ionization_mode})
    return result


def forward_eligible(smi):
    mol = Chem.MolFromSmiles(smi)
    elements = {'C', 'N', 'P', 'O', 'S', 'Si', 'I', 'H', 'Cl', 'F', 'Br', 'B', 'Se', 'Fe', 'Co', 'As', 'Na', 'K'}
    return mol is not None and 0 < mol.GetNumHeavyAtoms() <= 100 and '.' not in smi and all(a.GetSymbol() in elements for a in mol.GetAtoms())


def evaluate(records, forward):
    names = list(records[0]['variants'])
    baseline_rr = [reciprocal_rank(rank_keys(r['variants']['baseline80']), r['identity']) for r in records]
    output = {'query_count': len(records), 'variants': {}, 'weights': EXPERIMENT['forward_weights'], 'per_query': records}
    for name in names:
        unforwarded = [reciprocal_rank(rank_keys(r['variants'][name]), r['identity']) for r in records]
        grid = {str(w): [reciprocal_rank(rank_keys(r['variants'][name], forward.get(r['identity'], {}), w), r['identity']) for r in records]
                for w in EXPERIMENT['forward_weights']}
        folds = [int(hashlib.sha256(r['identity'].encode()).hexdigest()[:8], 16) % 5 for r in records]
        chosen, oof = {}, []
        for fold in sorted(set(folds)):
            train = [i for i,f in enumerate(folds) if f != fold]
            if not train:
                raise RuntimeError('Insufficient identities for cross-fitted calibration')
            choice = max(EXPERIMENT['forward_weights'], key=lambda w: (float(np.mean([grid[str(w)][i] for i in train])), -w))
            chosen[str(fold)] = choice
        oof = [grid[str(chosen[str(f)])][i] for i,f in enumerate(folds)]
        for i, record in enumerate(records):
            record.setdefault('metrics', {})[name] = {'base_rr': unforwarded[i], 'forward_oof_rr': oof[i], 'fold': folds[i],
                                                       'weight': chosen[str(folds[i])], 'truth_in_candidates': record['identity'] in record['variants'][name]['keys']}
        output['variants'][name] = {'mrr_at_25': float(np.mean(unforwarded)), 'forward_oof_mrr_at_25': float(np.mean(oof)),
            'hit_at_1': float(np.mean(np.asarray(unforwarded) == 1)), 'recall_at_25': float(np.mean(np.asarray(unforwarded) > 0)),
            'candidate_recall': float(np.mean([r['identity'] in r['variants'][name]['keys'] for r in records])),
            'forward_delta_vs_same_pool': paired_bootstrap(unforwarded, oof), 'base_delta_vs_baseline80': paired_bootstrap(baseline_rr, unforwarded),
            'selected_weight_by_fold': chosen, 'weight_grid_mrr_diagnostic_only': {w: float(np.mean(values)) for w,values in grid.items()}}
    output['limitations'] = ['Unknown development overlap in pretrained fingerprint models and public ranker training',
                            'Reference canonical alias masking limited to query 30ppm windows',
                            'Catalog-withheld proxy hides development identities jointly from base pool; PubChem candidates are independently retrieved',
                            'GLACIER covers positive [M+H]+ spectra with finite CE only; unsupported cases retain base ranking',
                            'Five-fold calibration is nested only within this fixed development cohort, not the sealed holdout']
    return output


query = development_query()
holdout_keys = set(DEVELOPMENT_PLAN['identity_keys'])
all_groups = list(query.groupby('canonical_key'))
forbidden = set(query.inchikey14)
window_canonical = {}
for key, sub in all_groups:
    mass = float(np.median(sub.nm))
    indices = pool.window(mass, CFG.PPM_FALLBACK)
    identities = {int(i): scorer_key(pool.smiles[i]) for i in indices}
    window_canonical[key] = identities
    forbidden.update(pool.keys[i] for i,k in identities.items() if k in holdout_keys)
allowed = ~np.isin(L['ik'], list(forbidden))
original_lib_window = lib_window


def masked_library_window(library, target, tolerance):
    positions = original_lib_window(library, target, tolerance)
    return positions[allowed[positions]]


lib_window = masked_library_window
visible_rep = ~np.isin(rep_key, list(forbidden))
rep, rep_key, rep_nm = rep[visible_rep], rep_key[visible_rep], rep_nm[visible_rep]
groups = sorted(all_groups, key=lambda item: hashlib.sha256(item[0].encode()).hexdigest())
if EXPERIMENT['query_limit']:
    groups = groups[:EXPERIMENT['query_limit']]
pc = PubChemMassIndex.from_directory(Path(find_file('pc_mass.npy')).parent)
if len(pc.mass) != 105_875_489:
    raise RuntimeError('Pinned PubChem entry count changed')
records, items = [], []
for number, (key, sub) in enumerate(groups):
    started = time.time()
    ev = evidence(sub)
    mass, spectra, direct, afp, similarities, logits = ev
    indices = pool.window(mass, CFG.PPM_WIN)
    if not len(indices):
        indices = pool.window(mass, CFG.PPM_FALLBACK)
    novel_indices = np.asarray([i for i in indices if window_canonical[key][int(i)] not in holdout_keys], dtype=int)
    pool_keys = set(window_canonical[key].values())
    novel_pool_keys = pool_keys - holdout_keys
    _fp_init()
    e_selected = np.flatnonzero(BITS < 4096)
    e_bits, e_logits = BITS[e_selected], logits[e_selected]
    coarse_cache, full_cache = {}, {}

    def coarse(smi):
        if smi not in coarse_cache:
            mol = Chem.MolFromSmiles(smi)
            coarse_cache[smi] = None if mol is None else float(_g['m2'].GetFingerprintAsNumPy(mol)[e_bits] @ e_logits)
        return coarse_cache[smi]

    def full_fp(smi):
        if smi not in full_cache:
            value = fp_and_mass(smi)
            full_cache[smi] = None if value is None else value[0]
        return full_cache[smi]

    args = dict(coarse_score=coarse, full_fingerprint=full_fp, logits=logits, canonical_key=scorer_key,
                coarse_limit=EXPERIMENT['pubchem_coarse_limit'], top_k=EXPERIMENT['pubchem_top_k'])
    external, pc_diag = screen_pubchem(pc, mass, EXPERIMENT['pubchem_ppm'], exclude_keys=pool_keys, **args)
    novel_external, novel_diag = screen_pubchem(pc, mass, EXPERIMENT['pubchem_ppm'], exclude_keys=novel_pool_keys, **args)
    fragment_cache = {}
    variants = {
        'baseline80': score_variant(coarse_prune(indices, direct, mass), [], sub, ev, fragment_cache),
        'expanded': score_variant(indices, [], sub, ev, fragment_cache),
        'pubchem': score_variant(indices, external, sub, ev, fragment_cache),
        'catalog_withheld_baseline': score_variant(coarse_prune(novel_indices, direct, mass), [], sub, ev, fragment_cache),
        'catalog_withheld_pubchem': score_variant(novel_indices, novel_external, sub, ev, fragment_cache),
    }
    record = {'identity': key, 'spectra_count': len(sub), 'base_mass_window_candidates': len(indices),
              'pubchem': pc_diag, 'catalog_withheld_pubchem': novel_diag, 'pubchem_truth_retained': key in {c['key'] for c in novel_external},
              'variants': variants, 'elapsed_seconds': time.time()-started}
    forward_candidates = []
    for variant in variants.values():
        order = ranked_unique(variant['smiles'], variant['probabilities'], scorer_key, top_k=EXPERIMENT['forward_top_k'])
        forward_candidates.extend(variant['smiles'][i] for i in order)
    forward_candidates = list(dict.fromkeys(forward_candidates))
    eligible = [s for s in forward_candidates if forward_eligible(s)]
    record['forward_candidates_requested'] = len(forward_candidates)
    record['forward_candidates_eligible'] = len(eligible)
    measured = forward_spectra(sub)
    record['covered_spectra'] = len(measured)
    records.append(record)
    if measured and eligible:
        items.append({'id': key, 'candidates': eligible, 'spectra': measured})
    if number % 5 == 0 or number == len(groups)-1:
        save_json('experiment_progress.json', {'phase': 'features', 'completed': number+1, 'expected': len(groups), 'elapsed_seconds': time.time()-T0})
        save_json('experiment_candidates.json', records)
        print('[EXPERIMENT] Features', number+1, '/', len(groups), 'seconds', round(time.time()-T0, 1), flush=True)

save_json('forward_input.json', items)
feature_manifest = {
    'complete': True, 'configuration': EXPERIMENT, 'query_count': len(records),
    'reference_spectra_visible': int(allowed.sum()), 'masked_raw_keys': len(forbidden),
    'elapsed_seconds': time.time()-T0, 'cohort_plan_sha256': DEVELOPMENT_PLAN['plan_sha256'],
    'kernel_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'forward_input_sha256': file_hash('forward_input.json'),
    'candidates_sha256': file_hash('experiment_candidates.json'),
}
save_json('feature_manifest.json', feature_manifest)
if EXPERIMENT.get('features_only'):
    before = [reciprocal_rank(rank_keys(r['variants']['baseline80']), r['identity']) for r in records]
    summary = {'complete': True, 'forward_executed': False, 'manifest': feature_manifest, 'variants': {}}
    for name in records[0]['variants']:
        scores = [reciprocal_rank(rank_keys(r['variants'][name]), r['identity']) for r in records]
        summary['variants'][name] = {'mrr_at_25': float(np.mean(scores)), 'hit_at_1': float(np.mean(np.asarray(scores)==1)),
            'recall_at_25': float(np.mean(np.asarray(scores)>0)),
            'candidate_recall': float(np.mean([r['identity'] in r['variants'][name]['keys'] for r in records])),
            'paired_delta_vs_baseline80': paired_bootstrap(before, scores)}
    save_json('feature_report.json', summary)
    print('[EXPERIMENT] FEATURE CACHE COMPLETE', json.dumps(summary), flush=True)
    raise SystemExit(0)
del query, L, pool, rep, rep_key, rep_nm
gc.collect()
torch.cuda.empty_cache()
pkg = Path(find_file('PROVENANCE.json')).parent
aux = Path(find_file('auxiliary_manifest.json')).parent
python, child_env = prepare_forward_environment(pkg, aux, '/kaggle/tmp/fwd_experiment_site',
    provenance_hash=STACK_PROVENANCE_SHA256, auxiliary_hash=AUXILIARY_SHA256, device='cuda')
command = [python, str(pkg/'runner/fwd_runner.py'), str(pkg), 'batch', 'forward_input.json', 'forward_scores.json',
           '--models', 'glacier', '--stack', 'none', '--device', 'cuda', '--bs', str(EXPERIMENT['forward_batch_size']), '--budget', '7200']
print('[EXPERIMENT] GLACIER items', len(items), flush=True)
result = subprocess.run(command, capture_output=True, text=True, env=child_env, timeout=7500)
Path('forward_run.log').write_text(result.stdout + '\n' + result.stderr)
meta = json.loads(Path('forward_scores.json.meta.json').read_text())
if result.returncode != 0 or meta['status'] != 'ok' or meta['errors'] or meta['items_done'] != len(items) or meta['device'] != 'cuda':
    raise RuntimeError('GLACIER incomplete or failed: ' + json.dumps(meta))
raw_forward = json.loads(Path('forward_scores.json').read_text())
forward = {}
for item in items:
    scores = raw_forward[item['id']]['glacier']
    if len(scores) != len(item['candidates']) or not np.isfinite(np.asarray(scores, float)).all():
        raise RuntimeError('Missing/nonfinite supported GLACIER predictions')
    forward[item['id']] = dict(zip(item['candidates'], scores))
report = evaluate(records, forward)
report.update(configuration=EXPERIMENT, forward_meta=meta, total_elapsed_seconds=time.time()-T0,
              reference_spectra_visible=int(allowed.sum()), masked_raw_keys=len(forbidden), complete=True,
              parent_rdkit=importlib.metadata.version('rdkit'), cohort_plan_sha256=DEVELOPMENT_PLAN['plan_sha256'])
save_json('experiment_report.json', report)
print('[EXPERIMENT] COMPLETE', json.dumps({k:v for k,v in report.items() if k != 'per_query'}), flush=True)
