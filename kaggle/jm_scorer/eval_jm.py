"""Evaluate one or more saved JM runs (or a merged ensemble dir) on the train_jm holdout."""
import argparse
import json
from pathlib import Path
import sys

import torch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE/'upstream')]
import train_jm  # noqa: E402
from model import SpectrumCandidateModel  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('runs', nargs='+', help='dirs with config.json + final_model.pt')
    p.add_argument('--data-config', required=True, help='training config whose work/split/validation settings to use')
    a = p.parse_args()
    cfg = json.loads(Path(a.data_config).read_text())
    data = train_jm.JMData(cfg)
    sets = train_jm.validation_sets(data, cfg)
    device = torch.device('cuda')
    for run in a.runs:
        mcfg = json.loads((Path(run)/'config.json').read_text())
        model = SpectrumCandidateModel(mcfg).to(device)
        model.load_state_dict(torch.load(Path(run)/'final_model.pt', map_location=device, weights_only=True)['state_dict'])
        metrics, _ = train_jm.validate(model, data, sets, device, {**cfg, **{k: mcfg[k] for k in ('temperature', 'fp_score_weight', 'fp_bits')}})
        print(json.dumps(dict(run=run, **{k: round(v, 4) for k, v in metrics.items()})), flush=True)


if __name__ == '__main__':
    main()
