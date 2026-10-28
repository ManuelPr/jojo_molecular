"""SpectrumCandidateModel with optional width/depth knobs; sanpier v1 configs build the identical network."""
import torch
from torch import nn
from torch.nn import functional as F


class SpectrumCandidateModel(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        if cfg.get('members'):
            # Ensemble: concatenated member embeddings scaled by 1/sqrt(n) make Z@M the mean member cosine,
            # and the mean fingerprint logits make the fingerprint term the mean member term.
            shared = {k: v for k, v in cfg.items() if k != 'members'}
            self.members = nn.ModuleList(SpectrumCandidateModel({**shared, **m}) for m in cfg['members'])
            return
        d = cfg['width']
        self.register_buffer('freq', 2.**torch.arange(10).float())
        self.peak = nn.Linear(44, d)
        self.meta = nn.Sequential(nn.Linear(4, d), nn.GELU(), nn.Linear(d, d))
        self.adduct = nn.Embedding(11, d)
        self.cls = nn.Parameter(torch.zeros(1, 1, d))
        layer = nn.TransformerEncoderLayer(d, cfg['heads'], d*4, cfg['dropout'], batch_first=True, norm_first=True)
        self.transformer = nn.TransformerEncoder(layer, cfg['layers'], enable_nested_tensor=False)
        self.norm = nn.LayerNorm(d)
        self.spec_projection = nn.Linear(d, cfg['embedding'])
        self.fp_head = nn.Linear(d, cfg['fp_bits'])
        hidden = cfg.get('mol_hidden', 512)
        blocks = [nn.Linear(cfg['fp_bits'], hidden), nn.GELU(), nn.Dropout(cfg['dropout'])]
        for _ in range(cfg.get('mol_layers', 1)-1):
            blocks += [nn.Linear(hidden, hidden), nn.GELU(), nn.Dropout(cfg['dropout'])]
        self.molecule = nn.Sequential(*blocks, nn.Linear(hidden, cfg['embedding']))

    def encode_spectra(self, x, lengths, meta, adduct):
        if self.cfg.get('members'):
            out = [m.encode_spectra(x, lengths, meta, adduct) for m in self.members]
            scale = len(out)**-0.5
            return torch.cat([z for z, _ in out], -1)*scale, torch.stack([p for _, p in out]).mean(0)
        a = x[:, :, [0, 3]].unsqueeze(-1)*self.freq*torch.pi
        p = torch.cat([x, a.sin().flatten(2), a.cos().flatten(2)], -1)
        tokens = self.peak(p)
        cls = self.cls.expand(len(x), -1, -1)+self.meta(meta)[:, None]+self.adduct(adduct)[:, None]
        tokens = torch.cat([cls, tokens], 1)
        mask = torch.arange(x.shape[1]+1, device=x.device)[None] > lengths[:, None]
        h = self.norm(self.transformer(tokens, src_key_padding_mask=mask)[:, 0])
        return F.normalize(self.spec_projection(h), dim=-1), self.fp_head(h)

    def encode_molecules(self, fp):
        if self.cfg.get('members'):
            return torch.cat([m.encode_molecules(fp) for m in self.members], -1)*len(self.members)**-0.5
        return F.normalize(self.molecule(fp), dim=-1)
