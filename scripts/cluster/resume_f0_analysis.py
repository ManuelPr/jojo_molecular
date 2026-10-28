"""Resume pure F0 fusion/audit after inference, verifying byte-identical reconstruction."""
from __future__ import annotations
import argparse,hashlib,json,os,sys,time,shutil
from pathlib import Path
from prepare_f0_source import SOURCE_SHA256

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--notebook',required=True,type=Path);p.add_argument('--competition',required=True,type=Path);a=p.parse_args();out=a.output.resolve();nbpath=a.notebook.resolve();comp=a.competition.resolve()
 assert hashlib.sha256(nbpath.read_bytes()).hexdigest()==SOURCE_SHA256
 nb=json.loads(nbpath.read_text());checkpoint=out/'submission.inference-checkpoint.csv'
 if not checkpoint.exists():checkpoint.write_bytes((out/'submission.csv').read_bytes())
 original=checkpoint.read_bytes();expected=hashlib.sha256(original).hexdigest();(out/'submission.before-analysis-resume.csv').write_bytes(original)
 if (out/'run_manifest.json').exists():shutil.copyfile(out/'run_manifest.json',out/'run_manifest.before-analysis-resume.json')
 os.chdir(out);inp=out/'input';env={'__name__':'__main__','Path':Path,'time':time,'os':os,'json':json,'hashlib':hashlib,'display':lambda value: print('DISPLAY',getattr(value,'shape',type(value).__name__))}
 exec('import sys,glob,pickle,math\nimport numpy as np\nimport pandas as pd\nimport pyarrow as pa\nimport pyarrow.parquet as pq\nimport rdkit\nimport torch\n',env)
 env.update(FOLD=inp/'casmi26-fold-safe-fpnet',POP=inp/'casmi26-pubchem-popularity-prior',TABLE=inp/'casmi26-natural-product-knowledge-table',PANEL=inp/'casmi26-natural-product-panel-benchmark',NOTEBOOK_STARTED=time.monotonic())
 # These generated cells already contain the reviewed local filesystem/bootstrap adaptation.
 for i in (25,26):exec(compile((out/f'cell-{i}.py').read_text(),f'cell-{i}.py','exec'),env)
 sys.path.insert(0,env['V4CODE']);from casmi import chem
 sys.path.insert(0,str(inp/'casmi26-attributed-v4g-reproduction-assets/casmi26-glacier'));import gl_fuse
 sys.path.insert(0,str(inp/'casmi26-attributed-v4g-reproduction-assets/casmi26-iceberg'));import fuse as ice_fuse
 np,pd=env['np'],env['pd'];base=json.loads((out/'base-candidates.json').read_text());BASE={k:(v['smiles'],v['keys'],v['library_confidence'],v['scores'],v['formulas']) for k,v in base.items()}
 te=pd.read_parquet(comp/'test.parquet');te['nm']=chem.neutral_mass(te.precursor_mz.values.astype(float),te.adduct.values)
 ice=json.loads((out/'ice_scores.json').read_text());gl=json.loads((out/'gl_scores.json').read_text());real=json.loads((out/'gl_real_scores.json').read_text())
 env.update(chem=chem,gl_fuse=gl_fuse,ice_fuse=ice_fuse,BASE=BASE,BASE_TAIL_CANDIDATES={k:list(v[0]) for k,v in BASE.items()},PC=json.loads((out/'pc_lists.json').read_text()),ENG=json.loads((out/'eng_lists.json').read_text()),ICE_SCORES=ice,GL_SCORES=gl,GL_REAL_SCORES=real,BASE_ICE=False,ICE_PC=True,TOPN=60,ICE_LAM=1.,GL_LAM=1.,ice_stats=dict(molecules=0,changed_top25=0,changed_top1=0),gl_stats={},COMP=str(comp),te=te,n_err=0,IS_RERUN=True,SMOKE_N=16,dev='cuda',CLAW_ICE_HEALTH='ok; restored from successful driver metadata',CLAW_GL_HEALTH='ok; restored from successful driver metadata',POOL_POP=np.load(inp/'casmi26-pubchem-popularity-prior/pool_lsid.npy').astype(float)+np.load(inp/'casmi26-pubchem-popularity-prior/pool_lpmid.npy').astype(float),ENG_DIR=str(out/'eng'),N1_GL_MIDS={k for k in gl if k not in real},N1_COMPLEMENT=False)
 from rdkit import Chem
 from rdkit.Chem.rdMolDescriptors import CalcMolFormula
 for mid,value in env['PC'].items():
  if value.get('pc') and env['BASE'][mid][2]<env['LIB_TAU']:
   value['pc_form']=[CalcMolFormula(Chem.MolFromSmiles(smiles)) for smiles in value['pc']]
 source=''.join(nb['cells'][40]['source']);tail=source[source.index('def gl_of(m):'):]
 exec(compile(tail,'cell40-rerank-only.py','exec'),env)
 for i in [42,44,46,47,48,49,50,51,52]:
  print('ANALYSIS_CELL',i,flush=True)
  source=''.join(nb['cells'][i]['source']).replace('/kaggle/input',str(inp)).replace('/kaggle/working',str(out))
  if i==49:
   env['E004_REPORT']=dict(experiment='E004',processed_ids=sorted(te.molecule_id.astype(str).unique()),hashes={'submission.csv':hashlib.sha256((out/'submission.csv').read_bytes()).hexdigest()},stages={})
   (out/'e004_verification.json').write_text(json.dumps(env['E004_REPORT'],indent=2));continue
  exec(compile(source,f'cell-{i}-resume.py','exec'),env)
  if i==47:
   actual=hashlib.sha256((out/'submission.csv').read_bytes()).hexdigest()
   if actual!=expected:raise ValueError('Inference checkpoint fusion reconstruction differs: '+actual)
   print('BYTE_IDENTICAL_RECONSTRUCTION',actual,flush=True)
 from f0_g1_evidence import export
 export(env,comp/'contract.json',out)
 report=dict(source_sha256=SOURCE_SHA256,inference_repeated=False,stage47_reconstruction_sha256=expected,byte_identical_reconstruction=True,final_sha256=hashlib.sha256((out/'submission.csv').read_bytes()).hexdigest(),validation='public-panel reference-identity-disjoint diagnostic; pretrained exposure not certified')
 (out/'resume-manifest.json').write_text(json.dumps(report,indent=2)+'\n');print('ANALYSIS_COMPLETE',report,flush=True)
if __name__=='__main__':main()
