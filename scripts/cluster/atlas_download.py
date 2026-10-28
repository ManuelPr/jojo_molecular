"""Download ICEBERG PubChem-atlas predicted [M+H]+ spectra per formula (public endpoint), gzip on disk.

Host ruling (Kaggle topic 745134, 2026-10-28): atlas predictions may be used and shipped in a private
dataset together with this retrieval code. Retrieval date is recorded per file in the manifest.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

URL = 'https://iceberg-ms.mit.edu/download_mgf?formula='


def validate_gzip(path):
    """Validate complete MGF blocks and gzip CRC before publishing a download."""
    active, blocks, raw_bytes = False, 0, 0
    with gzip.open(path, 'rb') as handle:
        for raw in handle:
            raw_bytes += len(raw)
            line = raw.strip()
            if line == b'BEGIN IONS':
                if active:
                    raise ValueError('Nested MGF block')
                active = True
            elif line == b'END IONS':
                if not active:
                    raise ValueError('Unmatched MGF end')
                active, blocks = False, blocks + 1
            elif line and not active and not line.startswith((b'#', b';', b'!')):
                raise ValueError('Response is not MGF')
    if active or not blocks:
        raise ValueError('Incomplete or empty MGF')
    return raw_bytes, blocks


def receipt(formula, path, status, raw_bytes, blocks):
    with path.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    return dict(formula=formula, status=status, raw_bytes=raw_bytes,
                compressed_bytes=path.stat().st_size, sha256=digest, spectra=blocks,
                url=URL+urllib.parse.quote(formula),
                utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))


def fetch(formula, out, max_bytes, retries=4):
    if not re.fullmatch(r'(?:[A-Z][a-z]?\d*)+', formula):
        raise ValueError('Invalid formula: '+formula)
    path = out/f'{formula}.mgf.gz'
    if path.exists():
        raw_bytes, blocks = validate_gzip(path)
        return receipt(formula, path, 'cached', raw_bytes, blocks)
    for attempt in range(retries):
        tmp = None
        try:
            with urllib.request.urlopen(URL+urllib.parse.quote(formula), timeout=300) as r:
                size = int(r.headers.get('Content-Length') or 0)
                if max_bytes and size > max_bytes:
                    return dict(formula=formula, status='too_large', advertised_raw_bytes=size)
                # Bound actual bytes even when HEAD/Content-Length is missing or inaccurate.
                with tempfile.NamedTemporaryFile(dir=out, prefix=formula+'.', suffix='.tmp', delete=False) as handle:
                    tmp = Path(handle.name)
                    with gzip.GzipFile(filename='', fileobj=handle, mode='wb', compresslevel=6, mtime=0) as compressed:
                        received = 0
                        while chunk := r.read(1024*1024):
                            received += len(chunk)
                            if max_bytes and received > max_bytes:
                                return dict(formula=formula, status='too_large', observed_raw_bytes=received)
                            compressed.write(chunk)
                        if size and received != size:
                            raise EOFError(f'Expected {size} response bytes, received {received}')
            raw_bytes, blocks = validate_gzip(tmp)
            tmp.replace(path)
            return receipt(formula, path, 'ok', raw_bytes, blocks)
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404):
                return dict(formula=formula, status=f'http{e.code}')
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        except (ValueError, EOFError, gzip.BadGzipFile) as e:
            return dict(formula=formula, status='invalid_mgf', error=str(e))
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)
        if attempt + 1 < retries:
            time.sleep(10*(attempt+1))
    return dict(formula=formula, status='failed')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('formulas', help='text file, one formula per line, in priority order')
    p.add_argument('--out', default='data/fastweb/iceberg_atlas/h_plus')
    p.add_argument('--workers', type=int, default=3)
    p.add_argument('--max-mb', type=float, default=60., help='skip formulas whose raw MGF exceeds this (0 = no cap)')
    a = p.parse_args()
    if a.workers < 1 or a.max_mb < 0:
        p.error('workers must be positive and max-mb nonnegative')
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    formulas = list(dict.fromkeys(Path(a.formulas).read_text().split()))
    log = (out/'manifest.jsonl').open('a')
    started, total = time.monotonic(), 0
    with ThreadPoolExecutor(a.workers) as pool:
        for n, result in enumerate(pool.map(lambda f: fetch(f, out, int(a.max_mb*1e6)), formulas), 1):
            total += result.get('raw_bytes', 0) if result['status'] == 'ok' else 0
            result.setdefault('utc', time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
            result.setdefault('url', URL+urllib.parse.quote(result['formula']))
            log.write(json.dumps(result)+'\n')
            log.flush()
            if n % 200 == 0:
                print(n, len(formulas), round(total/1e9, 2), 'GB raw', round(time.monotonic()-started), 's', flush=True)
    print('done', len(formulas), round(total/1e9, 2), 'GB raw', flush=True)


if __name__ == '__main__':
    main()
