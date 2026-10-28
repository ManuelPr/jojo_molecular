"""Port pinned Gu V492 V1 to an isolated local filesystem for bounded diagnostics.

Never installs packages in the training environment; no Kaggle submission API.
"""
from __future__ import annotations
import argparse,hashlib,json,os,time
from pathlib import Path
from prepare_f0_source import SOURCE_SHA256

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--competition',type=Path,required=True);p.add_argument('--notebook',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--simulator-site',type=Path,required=True);a=p.parse_args()
 a.notebook=a.notebook.resolve();a.competition=a.competition.resolve();a.assets=a.assets.resolve();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=True);inp=a.output/'input';inp.mkdir(exist_ok=True)
 assert hashlib.sha256(a.notebook.read_bytes()).hexdigest()==SOURCE_SHA256
 sources={'casmi26-attributed-v4g-reproduction-assets':'casmi26-attributed-v4g-reproduction-assets-v6','casmi26-pubchem-popularity-prior':'casmi26-pubchem-popularity-prior-v10','casmi26-natural-product-knowledge-table':'casmi26-natural-product-knowledge-table-v9','casmi26-natural-product-panel-benchmark':'casmi26-natural-product-panel-benchmark-v10','casmi26-fold-safe-fpnet':'casmi26-fold-safe-fpnet-v5'}
 for slug,directory in sources.items():
  target=(a.assets/directory).resolve()
  if not target.is_dir():raise FileNotFoundError(target)
  link=inp/slug
  if not link.exists():link.symlink_to(target,target_is_directory=True)
 # V6 transports the original PubChem tier as flat files; restore names by links.
 tier=inp/'restored-pubchem-tier';tier.mkdir(exist_ok=True)
 for name in ('pc_smiles.npy','pc_mass.npy','pc_off.npy'):
  original=(a.assets/sources['casmi26-attributed-v4g-reproduction-assets'])/('pubchem_tier__'+name)
  if not original.is_file():raise FileNotFoundError(original)
  if not (tier/name).exists():(tier/name).symlink_to(original)
 comp=inp/'enveda-CASMI26-molecule-id-mass-spectra'
 if not comp.exists():comp.symlink_to(a.competition.resolve(),target_is_directory=True)
 # Reuse the separate simulator wheel site; main scorer remains RDKit 2026.03.3.
 site=a.output/'ice_site'
 if not site.exists():site.symlink_to(a.simulator_site.resolve(),target_is_directory=True)
 nb=json.loads(a.notebook.read_text());start=time.monotonic();os.chdir(a.output)
 env={'__name__':'__main__','__file__':str(a.notebook),'Path':Path,'os':os,'time':time,'hashlib':hashlib,'json':json,'display':lambda value: print('DISPLAY',getattr(value,'shape',type(value).__name__))}
 exec('import sys, glob, math, pickle, gc\nimport numpy as np\nimport pandas as pd\nimport pyarrow as pa\nimport pyarrow.parquet as pq\nimport rdkit\n',env)
 assert env['rdkit'].__version__=='2026.03.3'
 env.update(FOLD=inp/'casmi26-fold-safe-fpnet',POP=inp/'casmi26-pubchem-popularity-prior',TABLE=inp/'casmi26-natural-product-knowledge-table',PANEL=inp/'casmi26-natural-product-panel-benchmark',NOTEBOOK_STARTED=start)
 os.environ['CASMI_STRUCTURE_CATALOG']=str(a.competition/'candidate_only_structures.parquet')
 changes=['omit presentation EDA and Kaggle final observer; retain prediction cells25..52']
 for i,c in enumerate(nb['cells']):
  if c['cell_type']!='code' or i<25 or i>52:continue
  source=''.join(c['source'])
  if i==27:
   source="E004_PREFLIGHT = dict(input_ids=sorted(pd.read_parquet(str(Path(COMP)/'test.parquet')).molecule_id.astype(str).unique()),runtime_input_path=COMP)"
   # Cell25 defines COMP; this observer accepts H100 and local paths explicitly.
   changes.append('observer accepts local competition and H100')
  elif i==29:
   source="IS_RERUN=True\nSMOKE_N=len(pd.read_parquet(Path(COMP)/'test.parquet',columns=['molecule_id']).molecule_id.unique())\nICE_BUDGET=float(os.environ.get('CASMI_SIMULATOR_BUDGET',300))\nprint('F0 fixed validation cohort',SMOKE_N,'no placeholder selection')"
   changes.append('explicit fixed cohort; simulator budget seconds='+os.environ.get('CASMI_SIMULATOR_BUDGET','300'))
  elif i==49:
   source="""E004_REPORT=dict(experiment='E004', processed_ids=sorted(te.molecule_id.astype(str).unique()), hashes={'submission.csv':sha256('submission.csv')}, stages={})
Path('e004_verification.json').write_text(json.dumps(E004_REPORT,indent=2))
"""
   changes.append('replace Kaggle smoke observer with local lineage record')
  if i==25:
   begin=source.index("tag = f'cp")
   end=source.index('import rdkit;')
   source=source[:begin]+"# Main RDKit already verified; no pip bootstrap.\n"+source[end:]
   changes.append('skip in-place RDKit installation; assert verified version')
  if i==31:
   old='    tr = tr[~tr.ik.isin(set(co_keys))]'
   new='    tr = pd.concat([tr, pd.read_parquet(os.environ["CASMI_STRUCTURE_CATALOG"])],ignore_index=True).drop_duplicates("ik")\n'+old
   patch="ENG_FILES['casmi_engine.py']=ENG_FILES['casmi_engine.py'].replace("+repr(old)+","+repr(new)+")\n"
   source=source.replace('for _n, _src in ENG_FILES.items():',patch+'for _n, _src in ENG_FILES.items():')
   source=source.replace('workers=os.cpu_count()', 'workers=2')
   changes.append('Engine2 retains excluded query structures as candidate-only entries; workers=2')
  if i==33:
   source=source.replace(", '4'],",", '2'],")
   changes.append('PubChem retrieval uses two workers')
  if i==35:
   original="_EXTERNAL_REFERENCE_STATE = _build_external_reference_cache('work', TABLE, _EXTERNAL_REFERENCE_PINS)"
   filtered=original+"\nfrom filter_f0_reference_cache import exclude_sids\n_external_contract=json.loads(Path(os.environ['CASMI_STRUCTURE_CATALOG']).with_name('contract.json').read_text())\n_EXTERNAL_REFERENCE_STATE=exclude_sids(_EXTERNAL_REFERENCE_STATE,_external_contract['excluded_raw_identities'],Path('external_identity_filtered'))\nprint('EXTERNAL_REFERENCE_EXCLUSION',_EXTERNAL_REFERENCE_STATE,flush=True)"
   source=source.replace(original,filtered)
   old_call="build_spec_cache(os.path.join(COMP, 'train.parquet'), 'work')"
   cache_code="_cache_signature=dict(train_sha256=sha256(os.path.join(COMP,'train.parquet')),build_sha256=sha256(Path(V4CODE)/'casmi/build.py'))\n_cache_path=Path('work/cache-contract.json')\n_cache_ready=_cache_path.is_file() and json.loads(_cache_path.read_text())==_cache_signature\nif not _cache_ready:\n    "+old_call+"\n    _cache_path.write_text(json.dumps(_cache_signature))\nelse: print('verified reference cache reused',flush=True)"
   source=source.replace(old_call,cache_code)
   changes.append('reuse spectral cache only with identical reference bytes and build-code hash')
   changes.append('verify original external cache pins, then remove evaluation SIDs while preserving other external references and all candidate structures')
  if i==38:
   source="_RAW_EVIDENCE=[]\n"+source
   needle="                order = np.argsort(-score, kind='stable')"
   assert needle in source
   extra="                _feature_matrix=np.concatenate([X,F],1)\n                _feature_names=list(FEATURES)+list(names)\n                for _j in range(len(C.pid)):\n                    _RAW_EVIDENCE.append(dict(query_identity=str(mid),candidate_smiles=str(C.smiles[_j]),source_key=str(C.key[_j]),pool_row=int(C.pid[_j]),formula=str(C.formula[_j]),ranker_score=float(score[_j]),library_confidence=lib_max,features=json.dumps({str(_n):float(_v) if np.isfinite(_v) else None for _n,_v in zip(_feature_names,_feature_matrix[_j])})))\n"
   source=source.replace(needle,extra+needle)
  if i==40:
   source=source.replace("1.0, 4000","1.0, float(os.environ.get('CASMI_SIMULATOR_BUDGET',300))").replace("N1_BUDGET = 1200.0 if IS_RERUN else 600.0","N1_BUDGET = float(os.environ.get('CASMI_SIMULATOR_BUDGET',300))")
   source=source.replace("N1_ARM = 'N1A_D'","GL_REAL_SCORES = {k:dict(v) for k,v in GL_SCORES.items()}\nN1_ARM = 'N1A_D'")
  source=source.replace('/kaggle/input',str(inp)).replace('/kaggle/working',str(a.output))
  (a.output/f'cell-{i}.py').write_text(source)
  print('F0_CELL_START',i,round(time.monotonic()-start,2),flush=True)
  cached_engine2=a.output/'engine2-source.sha256'
  profile=a.output.parent/'engine2-profile/profile.json'
  reuse_engine2=(i==31 and cached_engine2.is_file() and profile.is_file() and json.loads(profile.read_text())['returncode']==0 and cached_engine2.read_text()==hashlib.sha256(source.encode()).hexdigest())
  if reuse_engine2:
   cache_signature=a.output/'engine2-input-signature.json'
   def file_digest(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as handle:
     for chunk in iter(lambda:handle.read(8<<20),b''):digest.update(chunk)
    return digest.hexdigest()
   expected_signature=dict(source_sha256=hashlib.sha256(source.encode()).hexdigest(),train_sha256=file_digest(a.competition/'train.parquet'),test_sha256=file_digest(a.competition/'test.parquet'),catalog_sha256=file_digest(a.competition/'candidate_only_structures.parquet'),assets_sha256=file_digest(a.output.parent/'complete-assets-manifest.json'),runtime_sha256=file_digest(a.output.parent/'runtime-versions.json'))
   reuse_engine2=cache_signature.is_file() and json.loads(cache_signature.read_text())==expected_signature
  if reuse_engine2:
   env['ENG']=json.loads((a.output/'eng_lists.json').read_text());env['ENG_DIR']=str(a.output/'eng')
   print('verified Engine2 source hash reused',flush=True)
   changes.append('reuse Engine2 only with identical source, reference/query/catalog bytes, assets and runtime manifest')
  else:
   exec(compile(source,f'cell-{i}.py','exec'),env)
  if i==38:
   payload={str(mid):dict(smiles=v[0],keys=v[1],library_confidence=v[2],scores=v[3],formulas=v[4]) for mid,v in env['BASE'].items()}
   (a.output/'base-candidates.json').write_text(json.dumps(payload,default=str))
   env['pd'].DataFrame(env['_RAW_EVIDENCE']).to_parquet(a.output/'raw_candidate_evidence.parquet',index=False)
  if i==40:
   for key in ['ICE_SCORES','GL_SCORES','GL_REAL_SCORES']:
    (a.output/(key.lower()+'.json')).write_text(json.dumps(env.get(key,{}),default=str))
   (a.output/'simulator-items.json').write_text(json.dumps(env['items'],default=str))
   (a.output/'post-forward-state.json').write_text(json.dumps({key:env[key] for key in ['BASE','PC','BASE_TAIL_CANDIDATES']},default=str))
  if i==44:
   (a.output/'fusion-inputs.json').write_text(json.dumps({key:env[key] for key in ['PREFUSION_LISTS','FUSION_OVERFLOW']},default=str))
  print('F0_CELL_DONE',i,round(time.monotonic()-start,2),flush=True)
 if env.get('n_err')!=0:raise RuntimeError('F0 main engine candidate failures')
 if set(map(str,env['ENG']))!=set(map(str,env['BASE'])):raise RuntimeError('F0 Engine2 incomplete')
 record=dict(source_sha256=SOURCE_SHA256,changes=changes,historical_mount_versions_certified=False,validation='reference-identity-disjoint diagnostic; Full1/A+B/forward pretrained exposure unverified',elapsed_seconds=time.monotonic()-start)
 (a.output/'port-manifest.json').write_text(json.dumps(record,indent=2)+'\n')
 from f0_g1_evidence import export
 export(env,a.competition/'contract.json',a.output)
 print('F0_FINISHED',record,flush=True)
if __name__=='__main__':main()
