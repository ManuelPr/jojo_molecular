"""Take a bounded log snapshot when a long-lived SSE connection stops updating."""
import argparse
import json
from pathlib import Path
import time
import requests
from kaggle.api.kaggle_api_extended import KaggleApi


def read(kernel,output):
    api=KaggleApi();api.authenticate()
    owner,slug=kernel.split('/')
    chunks=[]
    with api.build_kaggle_client() as client:
        http=client._http_client;http._init_session()
        headers=dict(http._session.headers);headers['Accept']='text/event-stream, */*';headers.pop('Content-Type',None)
        response=http._session.get(http._endpoint+'/v1/kernels/logs/stream/'+owner+'/'+slug,
            stream=True,headers=headers,auth=http._session.auth,timeout=(10,5))
        response.raise_for_status()
        started=time.monotonic()
        try:
            if response.headers.get('Content-Type','').startswith('text/event-stream'):
                for line in response.iter_lines(chunk_size=1,decode_unicode=True):
                    if time.monotonic()-started>20:
                        break
                    if line and line.startswith('data:'):
                        payload=line[5:].strip()
                        if payload=='END_OF_LOG':
                            break
                        try:
                            chunks.append(json.loads(payload).get('data',''))
                        except json.JSONDecodeError:
                            chunks.append(payload)
            else:
                payload=response.json()
                chunks=[v.get('data','') for v in (payload if isinstance(payload,list) else [payload])]
        except requests.exceptions.ConnectionError:
            if not chunks:
                raise
        finally:
            response.close()
    text=''.join(chunks)
    target=Path(output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')
    return '\n'.join(text.splitlines()[-8:])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('kernel');parser.add_argument('output');args=parser.parse_args()
    print(read(args.kernel,args.output))
