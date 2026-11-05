"""G2: formula + fingerprint conditioned SMILES decoder (MSNovelist-style), trained from scratch on our structure set.

train:  g2.py train --data artifacts/G2/data_v1 --out artifacts/G2/run_v1 --gpu 1
sample: from g2 import Generator; Generator(run_dir, device).sample(fp_probs, counts, n=256) -> list of SMILES
The condition is a 2048-bit Morgan r2 fingerprint (probabilities; training uses true bits with a prediction-like noise
model) plus heavy-atom counts of the molecular formula. Sampling masks every token that would exceed the formula's remaining
heavy atoms and allows EOS only when all are used; hydrogens are checked after parsing.
"""
import argparse
import json
import math
import os
import re
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

TOKEN_RE = re.compile(r'(\[[^\]]+]|Br|Cl|Si|Se|B|C|N|O|S|P|F|I|b|c|n|o|s|p|se|\(|\)|\.|=|#|-|\+|\\|/|:|~|@|\?|>|\*|\$|%[0-9]{2}|[0-9])')
SPECIAL = ['<pad>', '<bos>', '<eos>']
HEAVY = ['C', 'N', 'O', 'S', 'P', 'F', 'Cl', 'Br', 'I', 'Si', 'B', 'Se']


def token_element(t):
    s = t[1:-1] if t.startswith('[') else t
    m = re.match(r'\d*([A-Z][a-z]?|[a-z][a-z]?)', s)
    if not m:
        return None
    e = m.group(1)
    e = e.capitalize() if e.islower() else e
    return e if e in HEAVY else None


class Vocab:
    def __init__(self, tokens):
        self.itos = SPECIAL + list(tokens)
        self.stoi = {t: i for i, t in enumerate(self.itos)}
        self.delta = np.zeros((len(self.itos), len(HEAVY)), np.int64)
        for i, t in enumerate(self.itos):
            e = token_element(t) if i >= len(SPECIAL) else None
            if e is not None:
                self.delta[i, HEAVY.index(e)] = 1

    def encode(self, s):
        toks = TOKEN_RE.findall(s)
        if ''.join(toks) != s or any(t not in self.stoi for t in toks):
            return None
        return [1] + [self.stoi[t] for t in toks] + [2]


class Decoder(nn.Module):
    def __init__(self, n_vocab, d=512, layers=6, heads=8, mem_tokens=16, max_len=170, fp_bits=2048, n_elem=13, dropout=0.1):
        super().__init__()
        self.mem_tokens, self.d = mem_tokens, d
        self.fp = nn.Sequential(nn.Linear(fp_bits, 1024), nn.GELU(), nn.Dropout(dropout), nn.Linear(1024, mem_tokens * d))
        self.formula = nn.Sequential(nn.Linear(n_elem * 2, 256), nn.GELU(), nn.Linear(256, d))
        self.tok = nn.Embedding(n_vocab, d)
        self.pos = nn.Embedding(max_len, d)
        layer = nn.TransformerDecoderLayer(d, heads, 4 * d, dropout, batch_first=True, norm_first=True, activation='gelu')
        self.dec = nn.TransformerDecoder(layer, layers)
        self.norm = nn.LayerNorm(d)
        self.head = nn.Linear(d, n_vocab)

    def memory(self, fp, counts):
        c = counts.float()
        f = torch.cat([torch.log1p(c), (c > 0).float()], -1)
        m = self.fp(fp).view(fp.shape[0], self.mem_tokens, self.d)
        return torch.cat([m, self.formula(f)[:, None]], 1)

    def forward(self, tokens, mem):
        L = tokens.shape[1]
        x = self.tok(tokens) + self.pos(torch.arange(L, device=tokens.device))[None]
        mask = torch.triu(torch.full((L, L), float('-inf'), device=tokens.device), 1)
        h = self.dec(x, mem, tgt_mask=mask, tgt_key_padding_mask=tokens.eq(0))
        return self.head(self.norm(h))


def noisy_fp(bits, rng):
    """Prediction-like fingerprint: on bits mostly high, some missed; few false positives; 20% clean."""
    n = bits.shape[0]
    on = bits.astype(bool)
    out = np.where(on, rng.uniform(0.35, 1.0, bits.shape), rng.uniform(0.0, 0.08, bits.shape))
    miss = on & (rng.random(bits.shape) < 0.25)
    out[miss] = rng.uniform(0.0, 0.35, miss.sum())
    fpos = (~on) & (rng.random(bits.shape) < 0.006)
    out[fpos] = rng.uniform(0.35, 0.9, fpos.sum())
    clean = rng.random(n) < 0.2
    out[clean] = bits[clean]
    return out.astype(np.float32)


class DS(torch.utils.data.Dataset):
    def __init__(self, smiles, counts, fps, vocab, augment):
        self.smiles, self.counts, self.fps, self.vocab, self.augment = smiles, counts, fps, vocab, augment

    def __len__(self):
        return len(self.smiles)

    def __getitem__(self, i):
        s = self.smiles[i]
        if self.augment and np.random.random() < 0.5:
            from rdkit import Chem, RDLogger
            RDLogger.DisableLog('rdApp.*')
            m = Chem.MolFromSmiles(s)
            if m is not None:
                r = Chem.MolToSmiles(m, doRandom=True, canonical=False, isomericSmiles=False)
                if len(TOKEN_RE.findall(r)) <= 160:
                    s = r
        ids = self.vocab.encode(s) or self.vocab.encode(self.smiles[i])
        return np.asarray(ids, np.int64), np.unpackbits(self.fps[i]).astype(np.uint8), self.counts[i]


def collate(batch):
    L = max(len(b[0]) for b in batch)
    tok = np.zeros((len(batch), L), np.int64)
    for j, b in enumerate(batch):
        tok[j, :len(b[0])] = b[0]
    rng = np.random.default_rng()
    fp = noisy_fp(np.stack([b[1] for b in batch]), rng)
    cnt = np.stack([b[2] for b in batch]).astype(np.int64)
    return torch.from_numpy(tok), torch.from_numpy(fp), torch.from_numpy(cnt)


def train(a):
    os.environ.setdefault('CUDA_VISIBLE_DEVICES', a.gpu)
    data, out = Path(a.data), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    import pandas as pd
    meta = json.loads((data/'meta.json').read_text())
    st = pd.read_parquet(data/'structures.parquet')
    counts, fps = np.load(data/'counts.npy'), np.load(data/'fp_packed.npy')
    vocab = Vocab(meta['vocab'])
    cfg = dict(d=a.d, layers=a.layers, heads=8, mem_tokens=16, max_len=170, n_elem=len(meta['elements']), vocab=meta['vocab'],
               elements=meta['elements'], epochs=a.epochs, lr=a.lr, batch=a.batch, data=str(data))
    (out/'config.json').write_text(json.dumps(cfg, indent=1))
    tr, va = np.where(st.split == 'train')[0], np.where(st.split == 'val')[0]
    mk = lambda idx, aug: DS(st.smiles.to_numpy()[idx], counts[idx], fps[idx], vocab, aug)  # noqa: E731
    dl = torch.utils.data.DataLoader(mk(tr, True), batch_size=a.batch, shuffle=True, num_workers=a.workers, collate_fn=collate,
                                     drop_last=True, persistent_workers=True, prefetch_factor=4)
    dv = torch.utils.data.DataLoader(mk(va, False), batch_size=a.batch, shuffle=False, num_workers=2, collate_fn=collate)
    dev = torch.device('cuda')
    model = Decoder(len(vocab.itos), d=a.d, layers=a.layers, n_elem=len(meta['elements'])).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01, betas=(0.9, 0.98))
    total = a.epochs * len(dl)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1, s / 2000) * 0.5 * (1 + math.cos(math.pi * min(1, s / total))))
    print('params', sum(p.numel() for p in model.parameters()) / 1e6, 'M; steps', total, flush=True)
    step, best, t0, hist = 0, 1e9, time.time(), []
    for ep in range(a.epochs):
        model.train()
        for tok, fp, cnt in dl:
            tok, fp, cnt = tok.to(dev, non_blocking=True), fp.to(dev, non_blocking=True), cnt.to(dev, non_blocking=True)
            with torch.autocast('cuda', dtype=torch.bfloat16):
                logits = model(tok[:, :-1], model.memory(fp, cnt))
                loss = F.cross_entropy(logits.float().reshape(-1, logits.shape[-1]), tok[:, 1:].reshape(-1), ignore_index=0)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step(); sched.step(); step += 1
            if step % 500 == 0:
                print(f'ep {ep} step {step}/{total} loss {loss.item():.4f} {time.time()-t0:.0f}s', flush=True)
        model.eval(); vl, vn = 0.0, 0
        with torch.no_grad(), torch.autocast('cuda', dtype=torch.bfloat16):
            for tok, fp, cnt in dv:
                tok, fp, cnt = tok.to(dev), fp.to(dev), cnt.to(dev)
                logits = model(tok[:, :-1], model.memory(fp, cnt))
                vl += F.cross_entropy(logits.float().reshape(-1, logits.shape[-1]), tok[:, 1:].reshape(-1), ignore_index=0,
                                      reduction='sum').item()
                vn += tok[:, 1:].ne(0).sum().item()
        hist.append(dict(epoch=ep, val_token_nll=vl / vn, seconds=time.time() - t0))
        print('VAL', hist[-1], flush=True)
        torch.save(dict(state_dict=model.state_dict(), cfg=cfg), out/'last.pt')
        if vl / vn < best:
            best = vl / vn
            torch.save(dict(state_dict=model.state_dict(), cfg=cfg), out/'best.pt')
        (out/'history.json').write_text(json.dumps(hist, indent=1))


class Generator:
    def __init__(self, run, device='cuda', ckpt='best.pt'):
        ck = torch.load(Path(run)/ckpt, map_location=device, weights_only=False)
        cfg = ck['cfg']
        self.vocab, self.elements, self.device = Vocab(cfg['vocab']), cfg['elements'], torch.device(device)
        self.model = Decoder(len(self.vocab.itos), d=cfg['d'], layers=cfg['layers'], n_elem=cfg['n_elem']).to(self.device)
        self.model.load_state_dict(ck['state_dict']); self.model.eval()
        self.delta = torch.tensor(self.vocab.delta, device=self.device)
        self.heavy_idx = [self.elements.index(e) for e in HEAVY]

    @torch.no_grad()
    def sample(self, fp, counts, n=256, temperature=1.0, max_len=165):
        """fp: (2048,) probabilities; counts: element counts in self.elements order. Returns raw SMILES strings."""
        dev = self.device
        fp_t = torch.tensor(np.asarray(fp, np.float32), device=dev)[None].expand(n, -1)
        cnt = torch.tensor(np.asarray(counts, np.int64), device=dev)[None].expand(n, -1)
        mem = self.model.memory(fp_t, cnt)
        remaining = cnt[:, self.heavy_idx].clone()
        tok = torch.full((n, 1), 1, dtype=torch.long, device=dev)
        done = torch.zeros(n, dtype=torch.bool, device=dev)
        for _ in range(max_len):
            with torch.autocast('cuda', dtype=torch.bfloat16):
                logits = self.model(tok, mem)[:, -1].float()
            over = (self.delta[None] > remaining[:, None]).any(-1)          # tokens that exceed the formula
            logits[over] = -1e9
            logits[:, 0] = -1e9; logits[:, 1] = -1e9
            can_end = remaining.eq(0).all(-1)
            logits[~can_end, 2] = -1e9
            nxt = torch.multinomial(F.softmax(logits / temperature, -1), 1)[:, 0]
            nxt = torch.where(done, torch.zeros_like(nxt), nxt)
            remaining = remaining - self.delta[nxt] * (~done)[:, None]
            done = done | nxt.eq(2)
            tok = torch.cat([tok, nxt[:, None]], 1)
            if done.all():
                break
        out = []
        for row in tok[:, 1:].tolist():
            s = []
            for t in row:
                if t in (0, 2):
                    break
                s.append(self.vocab.itos[t])
            out.append(''.join(s))
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['train'])
    ap.add_argument('--data', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--gpu', default='1')
    ap.add_argument('--d', type=int, default=512)
    ap.add_argument('--layers', type=int, default=6)
    ap.add_argument('--epochs', type=int, default=10)
    ap.add_argument('--lr', type=float, default=4e-4)
    ap.add_argument('--batch', type=int, default=384)
    ap.add_argument('--workers', type=int, default=8)
    a = ap.parse_args()
    train(a)


if __name__ == '__main__':
    main()
