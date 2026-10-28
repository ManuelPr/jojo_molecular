"""Download version-pinned F0 datasets with complete pagination and SHA256 inventory.

Run with Kaggle available in an isolated tool environment. Never logs credentials
or exception URLs. Raw DreaMS assets not consumed by F0 are explicitly inventoried
as omitted; the separately listed PubChemLite asset is already inside V6.
"""
from __future__ import annotations
import argparse,hashlib,json,time,os
from urllib.parse import quote
from pathlib import Path,PurePosixPath


def sha256(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for block in iter(lambda:f.read(8<<20),b''):h.update(block)
 return h.hexdigest()


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--root',required=True,type=Path)
 parser.add_argument('--only-source',help='Optional source slug; keep its configured version')
 parser.add_argument('--output',required=True,type=Path)
 parser.add_argument('--manifest',type=Path,default=Path(__file__).resolve().parents[2]/'configs/fastweb_research_assets_2026-10-22.json')
 args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
 from kaggle.api.kaggle_api_extended import KaggleApi
 api=KaggleApi();api.authenticate();inventory=[]
 for item in json.loads(args.manifest.read_text())['assets']:
  if args.only_source and item.get('source')!=args.only_source:continue
  if item['group']!='full' or item['source'].startswith('franciscoangulo/'):continue
  if not isinstance(item['version'],int) or item['version']<1:raise ValueError('Version pin required')
  source=f"{item['source']}/{item['version']}";dest=args.root/item['directory'];dest.mkdir(parents=True,exist_ok=True)
  rows=[];token=None;seen=set()
  while True:
   page=api.dataset_list_files(source,page_token=token,page_size=200)
   if page.error_message:raise RuntimeError('Dataset file listing failed')
   rows.extend(dict(name=f.name,bytes=f.total_bytes) for f in page.files)
   token=page.next_page_token
   if not token:break
   if token in seen:raise RuntimeError('Repeated pagination token')
   seen.add(token)
  (args.output/(item['directory']+'-files.json')).write_text(json.dumps(rows,indent=2)+'\n')
  omitted=[r for r in rows if r['name'].startswith('hengck23-dreams-enveda-casmi26/')]
  (args.output/(item['directory']+'-omitted-unused.json')).write_text(json.dumps(omitted,indent=2)+'\n')
  for row in rows:
   if row in omitted:continue
   name=PurePosixPath(row['name'])
   if name.is_absolute() or '..' in name.parts:raise ValueError('Unsafe asset path')
   path=dest/row['name'];path.parent.mkdir(parents=True,exist_ok=True)
   if not path.is_file() or path.stat().st_size!=row['bytes']:
    try:api.dataset_download_file(source,row['name'],path=str(path.parent),quiet=True)
    except Exception as exc:
     if isinstance(exc,TypeError) and row['name'].endswith('.json'):
      # SDK mistakes a public JSON file's list-valued `code` field for an RPC error.
      import requests
      token=os.environ.get('KAGGLE_API_TOKEN')
      token_path=Path(os.environ.get('KAGGLE_CONFIG_DIR',str(Path.home()/'.kaggle')))/'access_token'
      if token is None and token_path.is_file():token=token_path.read_text().strip()
      if token:
       url='https://www.kaggle.com/api/v1/datasets/download/'+item['source']+'/'+quote(row['name'],safe='')+'?datasetVersionNumber='+str(item['version'])
       response=requests.get(url,headers={'Authorization':'Bearer '+token},timeout=60)
       if response.status_code==200 and len(response.content)==row['bytes']:
        path.write_bytes(response.content)
        print('same-version raw JSON recovery',row['name'],flush=True)
        exc=None
     if exc is not None:
      status=getattr(getattr(exc,'response',None),'status_code',None)
      (args.output/'download-error.json').write_text(json.dumps(dict(source=source,file=row['name'],error_class=type(exc).__name__,http_status=status)))
      raise SystemExit('Download failed; see sanitized download-error.json') from None
    time.sleep(1)
   if not path.is_file() or path.stat().st_size!=row['bytes']:raise ValueError('Asset size mismatch: '+row['name'])
   inventory.append(dict(source=source,file=row['name'],bytes=row['bytes'],sha256=sha256(path)))
   (args.output/'full-assets-manifest.json').write_text(json.dumps(inventory,indent=2)+'\n')
  print(source,'complete',flush=True)
if __name__=='__main__':main()
