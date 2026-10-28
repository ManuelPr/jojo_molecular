"""Export paired, fixed-pool simulator diagnostics from the portable F0 scope."""
from __future__ import annotations
import hashlib,json,math,time
from pathlib import Path
import numpy as np
import pandas as pd
from casmi26.chemistry import canonical_inchikey14

def export(scope, contract_path, output):
 output=Path(output); contract=json.loads(Path(contract_path).read_text());truth=contract['truth']
 groups={str(k):g for k,g in scope['te'].groupby('molecule_id',sort=False)}
 ice=scope['ICE_SCORES'];real=scope['GL_REAL_SCORES'];proxy=scope['GL_SCORES'];rows=[];query_rows=[];pair_rows=[]
 statuses={}
 for label,rel in [('iceberg','ice_work/ice_out.json.meta.json'),('glacier_real','gl_work/gl_out.json.meta.json'),('glacier_proxy','n1_work/n1_out.json.meta.json')]:
  path=output/rel; statuses[label]=json.loads(path.read_text()) if path.is_file() else {'status':'missing'}
 arms=['protonated_ice_fallback','n1a_complement','joint_ice_n1a']
 def lookup(d,s,k):
  value=d.get(s,d.get(k))
  try:return float(value) if value is not None and math.isfinite(float(value)) else None
  except (TypeError,ValueError):return None
 for mid,engine in scope['ENG'].items():
  mid=str(mid)
  if mid not in truth or mid not in scope['PREFUSION_LISTS']:continue
  first=[s for s in scope['PREFUSION_LISTS'][mid] if s and s!='CCO']
  cands,scores,_=scope['metric_fusion'](first,engine.get('smiles',[]),scope['metric_identity'],alpha=scope['ALPHA'],offset=scope['KRR'],limit=40)
  if not cands:raise ValueError('empty F0 candidate pool '+mid)
  keys=[scope['chem'].score_key(s) or s for s in cands];metric_keys=[canonical_inchikey14(s) for s in cands];forms=[scope['_form2'](s) for s in cands]
  if any(k is None for k in metric_keys) or len(set(metric_keys))!=len(metric_keys):raise ValueError('F0 metric-fusion pool has invalid or duplicate official identities')
  gd,rd,idict=proxy.get(mid,{}),real.get(mid,{}),ice.get(mid,{})
  has_h=any((r.adduct=='[M+H]+' and r.ionization_mode=='positive') for r in groups[mid].itertuples())
  eligible=not has_h and any((r.adduct in ('[M+NH4]+','[M-H2O+H]+') and r.ionization_mode=='positive') for r in groups[mid].itertuples())
  finite_ice=any(lookup(idict,s,s) is not None for s in idict);finite_real=any(lookup(rd,s,k) is not None for s,k in zip(cands,keys));finite_proxy=any(lookup(gd,s,k) is not None for s,k in zip(cands,keys))
  routed={}
  for arm in arms:
   use_proxy=eligible and any(lookup(gd,s,s) is not None for s in gd) and (arm=='joint_ice_n1a' or (arm=='n1a_complement' and not finite_ice))
   gl=gd if use_proxy else rd
   use_joint=use_proxy and arm=='joint_ice_n1a'
   if any(lookup(gl,s,s) is not None for s in gl):
    evidence=[idict if use_joint else {},gl];lams=[scope['ICE_LAM'],scope['GL_LAM']]
   elif not finite_ice and scope.get('FRAG_GAP',{}).get(mid):evidence=[scope['FRAG_GAP'][mid]];lams=[0.5]
   else:evidence=[idict];lams=[scope['ICE_LAM']]
   order=scope['gl_fuse'].rerank_multi(cands,keys,scores,forms,evidence,lams,top_n=len(cands))
   ranked=[metric_keys[i] for i in order]
   if scope.get('APPLY_E2R2',True):
    top=canonical_inchikey14(engine['smiles'][0]) if engine.get('smiles') else None
    if top is not None and top!=ranked[0]:
     if top not in ranked:raise ValueError('Engine2 top candidate outside frozen pool')
     rest=[k for k in ranked if k!=top];ranked=rest[:1]+[top]+rest[1:]
   order=[metric_keys.index(k) for k in ranked]
   unique=list(dict.fromkeys(k for k in ranked if k))
   rank=unique.index(truth[mid])+1 if truth[mid] in unique else None
   rr=1/rank if rank is not None and rank<=25 else 0.
   routed[arm]=dict(order=list(map(int,order)),rr=rr,rank=rank)
   query_rows.append(dict(query_identity=mid,arm=arm,eligible=eligible,proxy_applied=use_proxy,has_real_h=has_h,candidate_count=len(cands),truth_in_pool=truth[mid] in metric_keys,rank=rank,rr_at25=rr,ice_covered=finite_ice,real_gl_covered=finite_real,proxy_gl_covered=eligible and finite_proxy,ice_candidate_coverage=sum(lookup(idict,s,k) is not None for s,k in zip(cands,keys)),real_gl_candidate_coverage=sum(lookup(rd,s,k) is not None for s,k in zip(cands,keys)),proxy_gl_candidate_coverage=sum(lookup(gd,s,k) is not None for s,k in zip(cands,keys)) if eligible else 0))
  if has_h and len({tuple(v['order']) for v in routed.values()})!=1:raise AssertionError('real protonated route changed')
  for i,(s,k,mk) in enumerate(zip(cands,keys,metric_keys)):
   vals=dict(iceberg_score=lookup(idict,s,k),glacier_real_score=lookup(rd,s,k),glacier_proxy_score=lookup(gd,s,k) if eligible else None)
   row=dict(query_identity=mid,candidate_smiles=s,candidate_scorer_identity=mk,candidate_source_key=k,rank=i+1,fusion_score=float(scores[i]),formula=forms[i],provenance='fixed F0 metric-fusion union',inclusion_stage='final_fusion_window40',true_candidate=mk==truth[mid],split='public_panel_reference_disjoint_diagnostic',eligible_proxy=eligible,**vals)
   row.update({name+'_missing':value is None for name,value in vals.items()});row.update({name+'_failed':statuses[name.removesuffix('_score')].get('status') in ('error','bad_input') for name in vals})
   row.update({'rank_'+arm:routed[arm]['order'].index(i)+1 for arm in arms})
   rows.append(row)
   for r in groups[mid].itertuples():
    pair_rows.append(dict(query_identity=mid,candidate_scorer_identity=mk,spectrum_id=r.spectrum_id,real_adduct=r.adduct,proxy_adduct='[M+H]+' if eligible and r.adduct in ('[M+NH4]+','[M-H2O+H]+') else None,collision_energy=json.dumps(np.asarray(r.collision_energy_ev).tolist()),score_granularity='molecule-aggregate; raw per-spectrum proxy scores retained in n1_work/n1_out.json'))
 candidates=pd.DataFrame(rows)
 raw=pd.read_parquet(output/'raw_candidate_evidence.parquet');raw['candidate_scorer_identity']=raw.candidate_smiles.map(canonical_inchikey14);raw['true_candidate']=[k==truth[mid] for k,mid in zip(raw.candidate_scorer_identity,raw.query_identity)];raw['inclusion_stage']='main_engine_before_top60';raw.to_parquet(output/'raw_candidate_evidence.parquet',index=False)
 for name,key in [('fingerprint_single_score','fz_single'),('fingerprint_merged_score','fz_merged'),('fingerprint_cosine','fp_cos')]:raw[name]=raw.features.map(lambda value:json.loads(value).get(key))
 raw['prior']=[float(scope['POOL_POP'][pid]) if 0<=pid<len(scope['POOL_POP']) else None for pid in raw.pool_row]
 raw.to_parquet(output/'raw_candidate_evidence.parquet',index=False)
 candidates=candidates.merge(raw[['query_identity','candidate_scorer_identity','ranker_score','library_confidence','pool_row','features','fingerprint_single_score','fingerprint_merged_score','fingerprint_cosine','prior']].drop_duplicates(['query_identity','candidate_scorer_identity']),on=['query_identity','candidate_scorer_identity'],how='left',validate='many_to_one')
 queries=pd.DataFrame(query_rows);pairs=pd.DataFrame(pair_rows)
 candidates.to_parquet(output/'candidate_evidence.parquet',index=False);queries.to_parquet(output/'paired_queries.parquet',index=False);pairs.to_parquet(output/'candidate_spectrum_pairs.parquet',index=False)
 provenance=[]
 for row in candidates.itertuples(index=False):
  sources=[]
  if pd.notna(row.ranker_score):sources.append('main_engine')
  if row.candidate_source_key in scope['ENG'][row.query_identity].get('keys',[]):sources.append('engine2')
  if row.candidate_source_key in scope.get('PC',{}).get(row.query_identity,{}).get('pc_keys',[]):sources.append('pubchem')
  if pd.notna(row.pool_row) and row.pool_row<0:sources.append('inherited_generator')
  provenance.append(';'.join(sources) or 'metric_fusion_representative')
 candidates['provenance']=provenance
 asset_manifest=output.parent/'complete-assets-manifest.json'
 if not asset_manifest.exists():asset_manifest=output.parent/'full-assets-manifest.json'
 candidates['asset_manifest_sha256']=hashlib.sha256(asset_manifest.read_bytes()).hexdigest() if asset_manifest.exists() else None
 candidates['data_contract_sha256']=hashlib.sha256(Path(contract_path).read_bytes()).hexdigest()
 candidates['source_sha256']=scope.get('F0_SOURCE_SHA256','3b05fe5620f0bfe3acb319c782761acb61c61d283d8835b415a4d671cd841aa4')
 candidates.to_parquet(output/'candidate_evidence.parquet',index=False)
 if set(queries.query_identity)!=set(truth):raise ValueError('Incomplete evaluation denominator')
 summary={}
 base=queries[queries.arm.eq(arms[0])].set_index('query_identity')
 for arm in arms:
  q=queries[queries.arm.eq(arm)].set_index('query_identity');delta=q.rr_at25-base.rr_at25
  rng=np.random.default_rng(20261022);boot=np.mean(rng.choice(delta.to_numpy(),size=(2000,len(delta)),replace=True),axis=1)
  summary[arm]=dict(queries=len(q),mrr_at25=float(q.rr_at25.mean()),eligible_queries=int(q.eligible.sum()),proxy_applied_queries=int(q.proxy_applied.sum()),eligible_mrr_at25=float(q.loc[q.eligible,'rr_at25'].mean()) if q.eligible.any() else None,paired_delta=float(delta.mean()),paired_bootstrap95=list(map(float,np.quantile(boot,[.025,.975]))),regressions=int((delta<0).sum()))
 raw_ranked=raw.sort_values('ranker_score',ascending=False,kind='stable').drop_duplicates(['query_identity','candidate_scorer_identity']).copy()
 raw_ranked['rank_after_ranker']=raw_ranked.groupby('query_identity').cumcount()+1
 raw_ranked.to_parquet(output/'raw_candidate_evidence.parquet',index=False)
 stage_coverage={}
 for label,mask in [('main_before_top60',raw_ranked.true_candidate),('main_ranker_recall_at100',raw_ranked.true_candidate & raw_ranked.rank_after_ranker.le(100)),('main_ranker_recall_at1000',raw_ranked.true_candidate & raw_ranked.rank_after_ranker.le(1000))]:
  stage_coverage[label]=raw_ranked.loc[mask,'query_identity'].nunique()/len(truth)
 report=dict(stage_coverage=stage_coverage,n1_arm='N1A_D from pinned V1 source; CE policy preserved',stage_reports=statuses,arms=summary,candidate_coverage=float(base.truth_in_pool.mean()),candidate_count=len(candidates),candidate_spectrum_pairs=len(pairs),validation=contract['validation'],limitations=['fixed F0 pool; upstream pre-fusion ranking held fixed across arms; original fragment fallback and E2R2 retained','Full1, A+B and simulator pretrained exposure not certified; not strict unseen-structure MRR',f'{len(truth)}-query public diagnostic; not sealed evaluation','missing scores retained as missing; failed status must be read with driver stage reports'])
 (output/'g1_results.json').write_text(json.dumps(report,indent=2)+'\n');print('G1_RESULTS',json.dumps(report),flush=True)
