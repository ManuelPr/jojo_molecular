"""Merge several JM scorer runs into one ensemble run directory (config.json + final_model.pt)."""
import argparse
import json
from pathlib import Path

import torch

SHARED = ['fp_bits', 'max_peaks', 'min_peaks', 'temperature', 'fp_score_weight']
MEMBER = ['width', 'heads', 'layers', 'embedding', 'dropout', 'mol_hidden', 'mol_layers']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('runs', nargs='+')
    p.add_argument('--out', required=True)
    a = p.parse_args()
    cfgs = [json.loads((Path(r)/'config.json').read_text()) for r in a.runs]
    for k in SHARED:
        assert len({json.dumps(c[k]) for c in cfgs}) == 1, f'members disagree on {k}'
    cfg = {k: cfgs[0][k] for k in SHARED}
    cfg['members'] = [{k: c[k] for k in MEMBER if k in c} for c in cfgs]
    cfg['member_runs'] = [str(r) for r in a.runs]
    state = {}
    for i, r in enumerate(a.runs):
        for k, v in torch.load(Path(r)/'final_model.pt', map_location='cpu', weights_only=True)['state_dict'].items():
            state[f'members.{i}.{k}'] = v
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out/'config.json').write_text(json.dumps(cfg, indent=2))
    torch.save(dict(state_dict=state), out/'final_model.pt')
    print(json.dumps(cfg, indent=1))


if __name__ == '__main__':
    main()
