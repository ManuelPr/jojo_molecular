"""Resolve exact source datasetVersion IDs without downloading dataset payloads.

Run with the Python interpreter that owns the Kaggle CLI installation.
Only the path of a download redirect is inspected; signed URLs are never saved.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

from kaggle.api.kaggle_api_extended import KaggleApi
from kagglesdk.datasets.types.dataset_api_service import (
    ApiDownloadDatasetRequest, ApiGetDatasetRequest,
)


def main():
    source = Path('artifacts/public_notebook_audit/flexon_v89/casmi26-public-baseline-adaptation-experiments-v89.ipynb')
    nb = json.loads(source.read_text(encoding='utf-8'))
    expected = {x['sourceId'] for x in nb['metadata']['kaggle']['dataSources']
                if x['sourceType'] == 'datasetVersion'}
    meta = json.loads(Path('artifacts/public_notebook_audit/flexon_current_metadata/kernel-metadata.json').read_text())

    def resolve(slug):
        api = KaggleApi(); api.authenticate()
        owner, name = slug.split('/')
        with api.build_kaggle_client() as client:
            req = ApiGetDatasetRequest(); req.owner_slug = owner; req.dataset_slug = name
            info = client.datasets.dataset_api_client.get_dataset(req)
            for version in sorted(info.versions, key=lambda v: v.version_number, reverse=True):
                req = ApiDownloadDatasetRequest()
                req.owner_slug = owner; req.dataset_slug = name
                req.dataset_version_number = version.version_number
                redirect = client.datasets.dataset_api_client.download_dataset(req)
                parts = urlsplit(redirect.url).path.strip('/').split('/')
                if len(parts) < 3 or parts[0] != 'kaggle-data-sets':
                    raise ValueError('Unexpected download redirect layout for ' + slug)
                version_id = int(parts[2])
                if version_id in expected:
                    result = dict(source=slug, version_number=version.version_number,
                                  dataset_version_id=version_id, dataset_id=info.id,
                                  license=info.license_name,
                                  pinned_source=f'{slug}/{version.version_number}')
                    print(json.dumps(result), flush=True)
                    return result
            raise ValueError('No exact historical version found for ' + slug)

    with ThreadPoolExecutor(max_workers=4) as pool:
        assets = list(pool.map(resolve, meta['dataset_sources']))
    assert {x['dataset_version_id'] for x in assets} == expected
    out = Path('configs/flexon_v89_assets.json')
    out.write_text(json.dumps({'source_notebook_sha256': 'c43e870c92bd67b2f0c0245c1b4064cfb1c49a1cbc81ffac349bee4708ad55a1',
                              'datasets': assets}, indent=2) + '\n', encoding='utf-8')
    print('All 16 exact historical dataset versions resolved.')


if __name__ == '__main__':
    main()
