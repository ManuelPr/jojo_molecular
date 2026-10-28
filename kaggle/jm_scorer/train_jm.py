"""JM scorer trainer: sanpier's contrastive objective plus same-formula PubChem negatives,
multi-spectrum molecule embeddings, timsTOF oversampling and an Enveda-180 holdout scored
against realistic candidates (train isomers + PubChem isomers absent from train)."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
import torch
from torch.nn import functional as F

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE/'upstream')]
import train as upstream  # noqa: E402  (sanpier train.py; resolves `model` to ours)
from model import SpectrumCandidateModel  # noqa: E402


class JMData(upstream.Data):
    def __init__(self, cfg):
        super().__init__(cfg)
        root = Path(cfg['work'])
        lib = self.spec.original_molecule_id.astype(str).values
        self.tims = lib == 'enveda-180'
        has_tims = np.zeros(len(self.mol), bool)
        has_tims[self.spec.mol_idx.values[self.tims]] = True
        self.has_tims = has_tims
        # Holdout: hashed fraction of molecules that have Enveda-180 timsTOF spectra (hidden-test domain).
        h = np.array([int(hashlib.sha256((str(cfg.get('split_seed', 20261028))+k).encode()).hexdigest()[:8], 16)/2**32 for k in self.mol.key])
        val = has_tims & (h < cfg['val_fraction'])
        self.val = np.where(val)[0]
        self.train = np.where(~val)[0]
        self.tims_by_mol = {i: r[self.tims[r]] for i, r in self.by_mol.items() if self.has_tims[i]}
        # source 0 = competition train.parquet; >0 = external (e.g. simulated atlas spectra).
        real = self.spec.source.values == 0
        self.real_by_mol = {i: r[real[r]] for i, r in self.by_mol.items()}
        self.has_real = np.array([len(self.real_by_mol.get(i, ())) > 0 for i in range(len(self.mol))])
        bank_dir = Path(cfg.get('bank_dir') or root/'pubchem_bank')
        bank = pd.read_parquet(bank_dir/'bank.parquet')
        self.bank_fp = np.load(bank_dir/'bank_fp_packed.npy')
        rows = bank.groupby('formula', sort=False).indices
        # A structure never serves as its own negative (atlas/external molecules can also sit in the bank).
        bank_key = bank.key.values
        self.bank_rows = [r[bank_key[r] != k] if len(r) else r for r, k in
                          ((rows.get(f, np.empty(0, np.int64)), k) for f, k in zip(self.mol.formula.values, self.mol.key.values))]
        print('JMData', dict(train=len(self.train), val=len(self.val), tims_molecules=int(has_tims.sum()),
                             bank=len(bank), bank_formulas=len(rows)), flush=True)

    def bank_fps(self, rows):
        return np.unpackbits(self.bank_fp[rows], axis=1)


def validation_sets(data, cfg):
    """Truth first, then same-formula train isomers, PubChem isomers and nearby-mass train fill."""
    rng = np.random.default_rng(cfg.get('split_seed', 20261028))
    all_ids = np.arange(len(data.mol))
    pools = upstream.hard_pools(data.mol, all_ids, cfg['val_train_candidates'])
    sets = {}
    for i in data.val[:cfg['max_validation_molecules']]:
        i = int(i)
        bank = data.bank_rows[i]
        if len(bank) > cfg['val_pubchem_candidates']:
            bank = rng.choice(bank, cfg['val_pubchem_candidates'], replace=False)
        fps = np.concatenate([np.asarray(data.fp[np.r_[i, pools[i]]]), data.bank_fps(bank)]).astype(np.uint8)
        kind = np.r_[0, np.ones(len(pools[i]), np.int8), np.full(len(bank), 2, np.int8)]
        sets[i] = (fps, kind)
    return sets


@torch.inference_mode()
def validate(model, data, sets, device, cfg):
    model.eval()
    rows = []
    for i, (fps, kind) in sets.items():
        sr = data.tims_by_mol[i]
        z, p = model.encode_spectra(*data.batch(sr[:64], device))
        z, p = z.mean(0), p.mean(0)
        fp = torch.tensor(fps, device=device, dtype=torch.float32)
        s = ((model.encode_molecules(fp)@z)/cfg['temperature']+cfg['fp_score_weight']*(fp@p)/cfg['fp_bits']).float().cpu().numpy()
        row = dict(key=data.mol.key.iloc[i], candidates=len(s), pubchem=int((kind == 2).sum()))
        for name, mask in (('all', kind >= 1), ('train', kind == 1), ('pubchem', kind == 2)):
            rank = 1+int(np.sum(s[mask] >= s[0]))
            row['rr_'+name] = 1/rank if rank <= 25 else 0.
            row['top1_'+name] = int(rank == 1)
        rows.append(row)
    frame = pd.DataFrame(rows)
    metrics = {k: float(frame[k].mean()) for k in frame.columns if k.startswith(('rr_', 'top1_'))}
    metrics['rr_pubchem_only_with_pubchem'] = float(frame.loc[frame.pubchem > 0, 'rr_pubchem'].mean())
    return metrics, frame


def sample_negatives(rng, rows, count):
    if len(rows) == 0:
        return np.zeros(count, np.int64), np.ones(count, bool)
    picked = rng.choice(rows, count, replace=len(rows) < count)
    masked = np.zeros(count, bool)
    _, first = np.unique(picked, return_index=True)
    masked[np.setdiff1d(np.arange(count), first)] = True
    return picked, masked


def train(cfg):
    out = Path(cfg['output'])
    out.mkdir(parents=True, exist_ok=True)
    (out/'config.json').write_text(json.dumps(cfg, indent=2))
    device = torch.device(cfg.get('device', 'cuda'))
    upstream.seed_all(cfg['seed'])
    rng = np.random.default_rng(cfg['seed'])
    torch.set_num_threads(4)
    data = JMData(cfg)
    ids = data.train
    pools = upstream.hard_pools(data.mol, ids, cfg['negative_pool'])
    weights = np.where(data.has_tims[ids], cfg['tims_boost'], 1.)
    weights = np.where(data.has_real[ids], weights, cfg.get('external_molecule_weight', 1.))
    weights /= weights.sum()
    sets = validation_sets(data, cfg)
    model = SpectrumCandidateModel(cfg).to(device)
    print('params', sum(p.numel() for p in model.parameters())/1e6, 'M', flush=True)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg['lr'], weight_decay=cfg['weight_decay'])
    total = cfg['steps']
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1., (s+1)/cfg['warmup']) * 0.5*(1+math.cos(math.pi*min(s, total)/total)))
    counts = np.zeros(cfg['fp_bits'])
    for st in range(0, len(ids), 4096):
        counts += np.asarray(data.fp[ids[st:st+4096]]).sum(0)
    pos_weight = torch.tensor(np.clip((len(ids)-counts)/(counts+1), 1, 20), device=device, dtype=torch.float32)
    B, K, KP, S = cfg['batch_size'], cfg['hard_negatives'], cfg['pubchem_negatives'], cfg['spectra_per_molecule']
    # bf16 on Ampere/Hopper; fp16 + loss scaling on GPUs without fast bf16 (Kaggle T4/P100).
    amp_dtype = torch.bfloat16 if cfg.get('amp', 'bf16') == 'bf16' else torch.float16
    scaler = torch.amp.GradScaler(device.type, enabled=amp_dtype == torch.float16)
    best, history, started, losses = -1., [], time.monotonic(), []
    deadline = started+cfg['hours']*3600
    for step in range(1, total+1):
        model.train()
        batch_ids = rng.choice(ids, B, replace=False, p=weights)
        spec_rows, owner = [], []
        for b, i in enumerate(batch_ids):
            rows = data.by_mol[int(i)]
            if data.has_real[i] and rng.random() < cfg.get('real_spectrum_prob', 1.):
                rows = data.real_by_mol[int(i)]
            if data.has_tims[i] and rng.random() < cfg['tims_spectrum_prob']:
                rows = data.tims_by_mol[int(i)]
            k = int(rng.integers(1, S+1))
            spec_rows.extend(rng.choice(rows, min(k, len(rows)), replace=False))
            owner.extend([b]*min(k, len(rows)))
        owner_t = torch.tensor(owner, device=device)
        neg = np.stack([rng.choice(pools[int(i)], K, replace=len(pools[int(i)]) < K) for i in batch_ids])
        dup = np.isin(neg, batch_ids)
        for r in range(B):
            _, first = np.unique(neg[r], return_index=True)
            dup[r, np.setdiff1d(np.arange(K), first)] = True
        pc = [sample_negatives(rng, data.bank_rows[int(i)], KP) for i in batch_ids]
        pc_rows, pc_mask = np.stack([p[0] for p in pc]), np.stack([p[1] for p in pc])
        fp = torch.tensor(np.asarray(data.fp[batch_ids]), device=device, dtype=torch.float32)
        negfp = torch.tensor(np.asarray(data.fp[neg.reshape(-1)]), device=device, dtype=torch.float32)
        pcfp = torch.tensor(data.bank_fps(pc_rows.reshape(-1)), device=device, dtype=torch.float32)
        with torch.autocast(device.type, dtype=amp_dtype):
            z, pred = model.encode_spectra(*data.batch(np.asarray(spec_rows), device, augment=True))
            # Mean over each molecule's sampled spectra, as at inference.
            n = torch.zeros(B, device=device).index_add_(0, owner_t, torch.ones(len(owner), device=device))[:, None]
            z = torch.zeros(B, z.shape[1], device=device, dtype=z.dtype).index_add_(0, owner_t, z)/n
            pred = torch.zeros(B, pred.shape[1], device=device, dtype=pred.dtype).index_add_(0, owner_t, pred)/n
            m = model.encode_molecules(fp)
            nm = model.encode_molecules(negfp).reshape(B, K, -1)
            positive = z@m.T/cfg['temperature']
            negative = torch.einsum('bd,bkd->bk', z, nm)/cfg['temperature']
            # Fingerprint-head agreement is part of the inference score; train it in the same softmax.
            w = cfg['fp_score_weight']/cfg['fp_bits']
            positive = positive+cfg['fp_in_softmax']*w*(pred.float()@fp.T)
            negative = negative+cfg['fp_in_softmax']*w*torch.einsum('bf,bkf->bk', pred.float(), negfp.reshape(B, K, -1))
            negative = negative.masked_fill(torch.tensor(dup, device=device), float('-inf'))
            if KP:
                pm = model.encode_molecules(pcfp).reshape(B, KP, -1)
                pubchem = torch.einsum('bd,bkd->bk', z, pm)/cfg['temperature']
                pubchem = pubchem+cfg['fp_in_softmax']*w*torch.einsum('bf,bkf->bk', pred.float(), pcfp.reshape(B, KP, -1))
                pubchem = pubchem.masked_fill(torch.tensor(pc_mask, device=device), float('-inf'))
            else:
                pubchem = positive[:, :0]
            logits = torch.cat([positive, negative, pubchem], 1).float()
            retrieval = F.cross_entropy(logits, torch.arange(B, device=device), label_smoothing=cfg['label_smoothing'])
            auxiliary = F.binary_cross_entropy_with_logits(pred.float(), fp, pos_weight=pos_weight)
            loss = retrieval+cfg['aux_weight']*auxiliary
        if not torch.isfinite(loss):
            raise RuntimeError('Nonfinite loss')
        opt.zero_grad(set_to_none=True)
        scaler.scale(loss).backward()
        scaler.unscale_(opt)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
        scaler.step(opt)
        scaler.update()
        sched.step()
        losses.append(float(loss.detach()))
        last = step == total or time.monotonic() > deadline
        if step % cfg['eval_every'] == 0 or last:
            metrics, frame = validate(model, data, sets, device, cfg)
            record = dict(step=step, loss=float(np.mean(losses)), lr=sched.get_last_lr()[0],
                          minutes=(time.monotonic()-started)/60, **metrics)
            losses = []
            history.append(record)
            ckpt = dict(state_dict={k: v.detach().cpu() for k, v in model.state_dict().items()}, step=step)
            upstream.atomic_save(ckpt, out/'last_model.pt')
            if metrics[cfg['select_metric']] > best:
                best = metrics[cfg['select_metric']]
                upstream.atomic_save(ckpt, out/'final_model.pt')
                frame.to_csv(out/'validation_predictions.csv', index=False)
            (out/'training_history.json').write_text(json.dumps(history, indent=2))
            print(json.dumps(record), flush=True)
        if last:
            break
    (out/'training_result.json').write_text(json.dumps(dict(best=best, select_metric=cfg['select_metric'], steps=step), indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--set', nargs='*', default=[], help='key=json overrides')
    a = p.parse_args()
    cfg = json.loads(Path(a.config).read_text())
    for kv in a.set:
        k, v = kv.split('=', 1)
        cfg[k] = json.loads(v)
    cfg['output'] = a.output
    train(cfg)


if __name__ == '__main__':
    main()
