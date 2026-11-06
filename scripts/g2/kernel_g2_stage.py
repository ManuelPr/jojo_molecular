"""S3 kernel stage: insert G2-generated structures into the final answer lists of gated (type-3-like) molecules.

Runs after the notebook has written submission.csv. Inputs: test spectra (test.parquet), the gated molecule ids written by the
gated genfix cell 39 (g3b_gated.json), the G2 decoder checkpoint, and two sanpier-kit bundles (public + own_w384_s7).
Per gated molecule: fingerprint = mean sigmoid fp head of the own bundle over the spectra; formula = formula of the current
rank-1 answer; N samples with formula masking; keep parsed, exact formula, new metric identities; neural z-ensemble
0.5 z(public) + 0.5 z(own) over current list + generated; the KINS best generated go right after the last list member
with a higher score, never above position MINPOS; list cut to 25. Same rule as scripts/g2/g4_insert_eval.py.
Fail-safe: any error leaves submission.csv unchanged; a report json says what happened.
"""
import json
import math
import time
import traceback
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


def _metric_key(smiles, _cache={}):
    """Stereo-stripped InChIKey14 WITHOUT tautomer canonicalisation (the official tautomer step costs 50-150 ms per NP
    and dominated the runtime). A tautomer of a listed structure may slip in as a duplicate answer: it wastes a slot but
    cannot lower first-match MRR."""
    if smiles in _cache:
        return _cache[smiles]
    from rdkit import Chem, RDLogger
    RDLogger.DisableLog('rdApp.*')
    key = None
    try:
        m = Chem.MolFromSmiles(smiles)
        if m is not None:
            Chem.RemoveStereochemistry(m)
            key = Chem.MolToInchiKey(m)[:14]
    except Exception:
        key = None
    _cache[smiles] = key
    return key


def _formula(smiles):
    from rdkit import Chem, RDLogger
    from rdkit.Chem import rdMolDescriptors
    RDLogger.DisableLog('rdApp.*')
    m = Chem.MolFromSmiles(smiles) if isinstance(smiles, str) else None
    return rdMolDescriptors.CalcMolFormula(m) if m is not None else None


def _counts(formula, elements):
    import re
    c = Counter()
    for e, k in re.findall(r'([A-Z][a-z]?)(\d*)', formula):
        c[e] += int(k) if k else 1
    return [c.get(e, 0) for e in elements], set(c) - set(elements)


def _load_kit(bundle, device):
    import importlib.util
    import sys
    import types
    import torch
    pkg = '_g2kit_' + str(abs(hash(str(bundle))))
    p = types.ModuleType(pkg); p.__path__ = [str(bundle)]; sys.modules[pkg] = p
    for name in ['features', 'model']:
        spec = importlib.util.spec_from_file_location(pkg + '.' + name, Path(bundle) / (name + '.py'))
        mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
    cfg = json.loads((Path(bundle) / 'config.json').read_text())
    model = sys.modules[pkg + '.model'].SpectrumCandidateModel(cfg).to(device)
    ck = torch.load(Path(bundle) / 'final_model.pt', map_location=device, weights_only=True)
    model.load_state_dict(ck['state_dict']); model.eval()
    return model, sys.modules[pkg + '.features'], cfg


def _spectra_tensors(feat, cfg, rows, device):
    import torch
    rec = []
    for r in rows.itertuples(index=False):
        try:
            pk, n = feat.peaks(r.ms2_mzs, r.ms2_normalized_intensities, r.precursor_mz, cfg['max_peaks'])
            if n < cfg['min_peaks']:
                continue
            m, a = feat.metadata(r.precursor_mz, r.adduct, r.ionization_mode, getattr(r, 'collision_energy_ev', None))
            rec.append((pk, n, m, a))
        except (ValueError, TypeError):
            continue
    if not rec:
        return None
    return (torch.tensor(np.stack([v[0] for v in rec]), device=device),
            torch.tensor([v[1] for v in rec], device=device, dtype=torch.long),
            torch.tensor(np.stack([v[2] for v in rec]), device=device),
            torch.tensor([v[3] for v in rec], device=device, dtype=torch.long))


_FP_CACHE = {}


def _structure_fp(feat, s, nbits):
    """Kit fingerprint (tautomer-canonical Morgan r2, exactly features.structure) cached across both scorers."""
    k = (s, nbits)
    if k not in _FP_CACHE:
        try:
            _FP_CACHE[k] = feat.structure(s, nbits)[-1]
        except Exception:
            _FP_CACHE[k] = None
    return _FP_CACHE[k]


def _neural(kit, x, smiles, device):
    import torch
    model, feat, cfg = kit
    fps = [_structure_fp(feat, s, cfg['fp_bits']) for s in smiles]
    ok = [f is not None for f in fps]
    F = torch.tensor(np.stack([f if f is not None else np.zeros(cfg['fp_bits']) for f in fps]), device=device, dtype=torch.float32)
    with torch.inference_mode():
        M = model.encode_molecules(F)
        Z, P = model.encode_spectra(*x)
        comb = (Z @ M.T) / cfg['temperature'] + cfg['fp_score_weight'] * (P @ F.T / cfg['fp_bits'])
    s = comb.mean(0).float().cpu().numpy()
    s[~np.array(ok)] = np.nan
    return s


def run(work, test_parquet, gated_json, g2_dir, pub_bundle, own_bundle, n=256, kins=3, minpos=2, device='cuda',
        time_budget_s=3600, topm=20):
    import torch
    import sys
    t0 = time.time()
    work = Path(work)
    rep = dict(status='started', changed=0, inserted=0, gated=0, errors=0)
    sub_path = work / 'submission.csv'
    try:
        sys.path.insert(0, str(g2_dir))
        from g2 import Generator
        sub = pd.read_csv(sub_path, dtype=str, keep_default_na=False)
        gated = set(json.loads(Path(gated_json).read_text()))
        rep['gated'] = len(gated)
        te = pd.read_parquet(test_parquet)
        te['molecule_id'] = te.molecule_id.astype(str)
        gen = Generator(g2_dir, device)
        pub, own = _load_kit(pub_bundle, device), _load_kit(own_bundle, device)
        out = []
        for mid, smiles in zip(sub.molecule_id.astype(str), sub.smiles.astype(str)):
            L = [s for s in smiles.split(';') if s]
            new = L
            if mid in gated and L and time.time() - t0 < time_budget_s:
                try:
                    rows = te[te.molecule_id == mid]
                    xo = _spectra_tensors(own[1], own[2], rows, device)
                    xp = _spectra_tensors(pub[1], pub[2], rows, device)
                    f = _formula(L[0])
                    if xo is not None and xp is not None and f:
                        with torch.inference_mode():
                            fp = torch.sigmoid(own[0].encode_spectra(*xo)[1]).mean(0).float().cpu().numpy()
                        counts, extra = _counts(f, gen.elements)
                        if not extra:
                            have = {_metric_key(s) for s in L}
                            cnt, repr_ = Counter(), {}
                            import re as _re
                            max_len = min(165, len(_re.findall(r'\[[^\]]+]|Br|Cl|.', L[0])) + 25)
                            for s in gen.sample(fp, counts, n=n, max_len=max_len):
                                if s and _formula(s) == f:
                                    k = _metric_key(s)
                                    if k and k not in have:
                                        cnt[k] += 1; repr_.setdefault(k, s)
                            G = [repr_[k] for k, _ in cnt.most_common(topm)]
                            if G:
                                allc = L + G
                                z = []
                                for kit, x in ((pub, xp), (own, xo)):
                                    v = _neural(kit, x, allc, device)
                                    v = np.where(np.isnan(v), np.nanmin(v) if np.isfinite(v).any() else 0.0, v)
                                    z.append((v - v.mean()) / max(v.std(), 1e-6))
                                e = dict(zip(allc, 0.5 * z[0] + 0.5 * z[1]))
                                cand = sorted(G, key=lambda s: -e[s])[:kins]
                                new = list(L)
                                for s in cand:
                                    pos = max(minpos - 1, max([j + 1 for j, t in enumerate(new) if e.get(t, -1e9) > e[s]], default=0))
                                    new.insert(min(pos, len(new)), s)
                                new = new[:25]
                                rep['inserted'] += sum(s in new for s in cand)
                except Exception as ex:
                    rep['errors'] += 1
                    if rep['errors'] <= 3:
                        print('G2 STAGE molecule error', mid, repr(ex), flush=True)
                    new = L
            if new != L:
                rep['changed'] += 1
            out.append(';'.join(new) if new else smiles)
        res = sub.copy(); res['smiles'] = out
        assert len(res) == len(sub) and (res.smiles.str.split(';').map(len) <= 25).all()
        assert all(len(set(x.split(';'))) == len(x.split(';')) for x in res.smiles)
        (work / 'submission_pre_g2.csv').write_text(sub_path.read_text())
        res.to_csv(work / 'submission.tmp.csv', index=False)
        Path(work / 'submission.tmp.csv').replace(sub_path)
        rep['status'] = 'applied'
    except Exception:
        rep['status'] = 'failed: ' + traceback.format_exc()[-600:]
    rep['seconds'] = round(time.time() - t0, 1)
    (work / 'g2_stage_report.json').write_text(json.dumps(rep, indent=1))
    print('G2 STAGE', json.dumps({k: v for k, v in rep.items() if k != 'status'}), rep['status'][:200], flush=True)
    return rep
