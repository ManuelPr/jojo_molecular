"""Create a bounded public-panel reference-disjoint smoke; never alter frozen splits."""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from casmi26.chemistry import canonical_inchikey14

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--queries',type=int,default=16);p.add_argument('--exclude-contract',type=Path);p.add_argument('--query-audit',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 panelroot=a.root/'casmi26-natural-product-panel-benchmark-v10';panel=pd.read_parquet(panelroot/'panel.parquet').sort_values('molecule')
 if a.exclude_contract:
  prior=set(json.loads(a.exclude_contract.read_text())['truth'])
  panel=panel.loc[~panel.molecule.astype(str).isin(prior)]
 structures=pd.read_parquet(panelroot/'casmi26-identity-disjoint-validation-folds/structures.parquet')
 audit=json.loads(a.query_audit.read_text()) if a.query_audit else None
 if audit:
  if audit['mismatches']:raise ValueError('Resolve scorer crosswalk discrepancies before selecting a cohort')
  panel=panel.loc[panel.molecule.astype(str).isin(audit['truth'])]
 unavailable=panel.loc[~panel.molecule.astype(str).isin(structures.inchikey14.astype(str)),'molecule'].astype(str).tolist()
 (a.output/'eligibility.json').write_text(json.dumps(dict(excluded_without_training_identity_crosswalk=unavailable,excluded_without_np_query=audit['no_queries'] if audit else [],reason='Only audited training/scorer identities with available enveda-np-examples query spectra are eligible'),indent=2)+'\n')
 if unavailable:print('Explicitly excluded panel identities without training crosswalk',unavailable,flush=True)
 panel=panel.loc[panel.molecule.astype(str).isin(structures.inchikey14.astype(str))]
 if a.queries<1 or a.queries>len(panel):raise ValueError('Requested cohort exceeds available panel queries')
 def stratum(ad):
  ads=set(str(ad).split(';'))
  if '[M+H]+' in ads:return 'real_H'
  if '[M+NH4]+' in ads:return 'NH4_blind'
  if '[M-H2O+H]+' in ads:return 'waterloss_blind'
  return 'other'
 panel['stratum']=panel.adducts.map(stratum);chosen=[]
 groups=[g for _,g in panel.groupby('stratum',sort=True)]
 for i in range(len(panel)):
  for g in groups:
   if i<len(g) and len(chosen)<a.queries: chosen.append(g.iloc[i])
 selected=pd.DataFrame(chosen); rawkeys=set(selected.molecule.astype(str))
 raw_to_scorer=dict(zip(structures.inchikey14.astype(str),structures.scorer_key.astype(str)))
 truth={k:raw_to_scorer.get(k) for k in rawkeys}
 if any(v is None for v in truth.values()):raise ValueError('Panel query missing scorer crosswalk')
 excluded={str(k) for k,v in raw_to_scorer.items() if v in set(truth.values())}
 structures.loc[structures.inchikey14.astype(str).isin(excluded),['inchikey14','smiles']].rename(columns={'inchikey14':'ik','smiles':'smi'}).to_parquet(a.output/'candidate_only_structures.parquet',index=False)
 queries=[];removed=kept=0;writer=None
 pf=pq.ParquetFile(a.root/'competition/train.parquet')
 try:
  for batch in pf.iter_batches(batch_size=16384):
   table=pa.Table.from_batches([batch]); keys=table['inchikey14'].cast(pa.string())
   q=table.filter(pc.is_in(keys,value_set=pa.array(sorted(rawkeys))))
   if q.num_rows:queries.append(q)
   ref=table.filter(pc.invert(pc.is_in(keys,value_set=pa.array(sorted(excluded)))))
   removed+=table.num_rows-ref.num_rows;kept+=ref.num_rows
   if writer is None:writer=pq.ParquetWriter(a.output/'train.parquet',ref.schema,compression='zstd')
   writer.write_table(ref)
 finally:
  if writer:writer.close()
 frame=pa.concat_tables(queries).to_pandas();frame=frame.loc[frame.ingest_lib.eq('enveda-np-examples')].copy();frame['molecule_id']=frame.inchikey14.astype(str);frame['spectrum_id']=['f0:'+str(i) for i in range(len(frame))]
 observed=frame.groupby('molecule_id').normalized_smiles.first().map(canonical_inchikey14)
 if observed.to_dict()!=truth:raise ValueError('Official scorer query identity disagrees with public crosswalk')
 frame.to_parquet(a.output/'test.parquet',index=False)
 pd.DataFrame({'molecule_id':sorted(rawkeys),'smiles':['']*len(rawkeys)}).to_csv(a.output/'sample_submission.csv',index=False)
 selected['truth_scorer_key']=selected.molecule.map(truth);selected.to_parquet(a.output/'query_contract.parquet',index=False)
 (a.output/'contract.json').write_text(json.dumps(dict(query_count=len(rawkeys),spectrum_count=len(frame),strata=selected.stratum.value_counts().to_dict(),excluded_raw_identities=sorted(excluded),truth=truth,reference_rows=kept,removed_reference_rows=removed,validation='public-panel reference-identity-disjoint diagnostic; pretrained exposure not certified'),indent=2)+'\n')
 print('queries',len(rawkeys),'spectra',len(frame),'references',kept,'removed',removed,flush=True)
if __name__=='__main__':main()
