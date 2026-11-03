"""Genfix (discussion 752356) for the frozen 0.465 pipeline: Engine 1 keeps its base run exactly; a second run of the
same engine with wider class-3 generation contributes only the structures the base list lacks, inserted at their rank in
the wide run, on the base run's score scale (score of the candidate they push down). List-relative ranker features make
an ungated wide run re-score the base candidates (T1 type-1 cost -0.007, public -0.010 reported in 752356); insertion
keeps them as they are (emulated on final lists: T1 -0.0002, K6 type 3 +0.037, scripts/unseen/eval_gen_insert.py).

patch_cell39(source, gen_cfg) returns the patched source of pipeline cell 39. The function is self-contained so that
scripts/build_c477_genwide.py can copy its source into the Kaggle runner, and scripts/cluster/k2_runner.py (K2_GENFIX)
replays exactly the same code on the benches.
"""


def patch_cell39(source, gen_cfg):
    anchor = "                    if len(smis) >= TOPN: break\n"
    tail = "print('errors', n_err, '| popularity re-ranked lists', n_pp)\n"
    assert source.count(anchor) == 1 and source.count(tail) == 1, 'GENFIX: cell 39 anchors changed'
    pre = (
        "import dataclasses as _gf_dc\n"
        "assert V.E is E and hasattr(E, 'cfg'), 'GENFIX: V1FE does not wrap the main engine'\n"
        "_GF_BASE = E.cfg\n"
        "_GF_WIDE = _gf_dc.replace(E.cfg, " + gen_cfg + ")\n"
        "GF_STATS = dict(calls=0, lists_changed=0, inserted=0, errors=0)\n"
        "def _gf_insert(spectra, target, smis, keys, scs, forms, pids_):\n"
        "    GF_STATS['calls'] += 1\n"
        "    try:\n"
        "        E.cfg = _GF_WIDE\n"
        "        try:\n"
        "            C2, X2, F2, n2, _ = V.run(spectra, target)\n"
        "        finally:\n"
        "            E.cfg = _GF_BASE\n"
        "        if not len(C2.pid):\n"
        "            return\n"
        "        s2 = rank_score(np.concatenate([X2, F2], 1), list(FEATURES) + list(n2))\n"
        "        have, seen, new, r = set(keys), set(), [], 0\n"
        "        for i in np.argsort(-s2, kind='stable'):\n"
        "            k = C2.key[i]\n"
        "            if k in seen: continue\n"
        "            seen.add(k)\n"
        "            if k not in have: new.append((r, i))\n"
        "            r += 1\n"
        "            if r >= TOPN: break\n"
        "        if not new:\n"
        "            return\n"
        "        S, K, Sc, Fo, Pi = list(smis), list(keys), list(scs), list(forms), list(pids_)\n"
        "        for r, i in new:\n"
        "            pos = min(r, len(S))\n"
        "            sc = Sc[pos] if pos < len(Sc) else (Sc[-1] if Sc else float(s2[i]))\n"
        "            S.insert(pos, C2.smiles[i]); K.insert(pos, C2.key[i]); Sc.insert(pos, sc)\n"
        "            Fo.insert(pos, C2.formula[i]); Pi.insert(pos, int(C2.pid[i]))\n"
        "        smis[:], keys[:], scs[:], forms[:], pids_[:] = S[:TOPN], K[:TOPN], Sc[:TOPN], Fo[:TOPN], Pi[:TOPN]\n"
        "        GF_STATS['lists_changed'] += 1; GF_STATS['inserted'] += len(new)\n"
        "    except Exception as e:\n"
        "        GF_STATS['errors'] += 1\n"
        "        print('GENFIX ERROR', repr(e), flush=True)\n"
    )
    source = source.replace(anchor, anchor + "            _gf_insert(spectra, target, smis, keys, scs, forms, pids_)\n")
    source = source.replace(tail, tail + "print('GENFIX', GF_STATS, flush=True)\n"
                            "assert GF_STATS['calls'] > 0 and GF_STATS['errors'] <= max(2, GF_STATS['calls'] // 50), GF_STATS\n")
    return pre + source
