"""Private verbatim copy of a public notebook directory (ipynb + kernel-metadata.json) as a submittable kernel.

Usage: build_verbatim_bundle.py SRC_DIR OUT_DIR SLUG
"""
import json
import sys
from pathlib import Path


def main():
    src, out, slug = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    nbs = sorted(src.glob('*.ipynb'))
    assert len(nbs) == 1, nbs
    nb = json.loads(nbs[0].read_text())
    for c in nb['cells']:
        if c['cell_type'] == 'code':
            c['outputs'], c['execution_count'] = [], None
    meta = json.loads((src/'kernel-metadata.json').read_text())
    meta.update(id=f'mperni/{slug}', title=slug.replace('-', ' '), code_file=f'{slug}.ipynb', is_private=True)
    meta.pop('id_no', None)
    out.mkdir(parents=True, exist_ok=True)
    (out/f'{slug}.ipynb').write_text(json.dumps(nb, indent=1))
    (out/'kernel-metadata.json').write_text(json.dumps(meta, indent=2)+'\n')
    print('wrote', out, 'kernel sources', meta.get('kernel_sources'), 'datasets', len(meta.get('dataset_sources', [])))


if __name__ == '__main__':
    main()
