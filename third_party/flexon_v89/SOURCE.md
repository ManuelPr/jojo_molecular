# Flexon v89 reproduction source

Exact downloaded notebook: `upstream.ipynb`, SHA256
`c43e870c92bd67b2f0c0245c1b4064cfb1c49a1cbc81ffac349bee4708ad55a1`.

Source: https://www.kaggle.com/code/flexonafft/casmi26-public-baseline-adaptation-experiments?scriptVersionId=357683876

The upstream notebook declares Apache-2.0. All original authors, citations and
component licence notices are preserved in its cells. Dataset/component licences
remain separate; exact dataset versions and declared licence labels are recorded
in `configs/flexon_v89_assets.json`. This is derivative code, not our model design.

The recorded page score was 0.440 on 2026-10-14. The notebook itself identifies
0.440 as the inherited E006 result and does not claim a measured benefit for its
dual-polarity overlay. This score is not our independently reproduced result.

The builder preserves all source cells except one assignment selecting the full
visible workload instead of the original 12-query smoke. It appends a read-only
acceptance observer and strips previous execution outputs. No ranking coefficient,
candidate route, model or simulator policy is modified. The original source file
remains byte-for-byte unchanged.
