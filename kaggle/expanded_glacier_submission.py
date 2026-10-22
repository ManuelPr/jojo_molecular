"""Actual competition inference, recomputed on every hidden rerun."""
import gc
import importlib.metadata

torch.set_num_threads(4)
if _MODEL is None or len(_MODEL[0])!=1 or len(_MODEL[1])!=1 or _MODEL[2]!='cpu' or len(RANKERS)!=8 or NFEAT!=31:
    raise RuntimeError('Frozen evidence channels missing')
if len(L['ik'])!=2_539_608 or len(pool.mass)!=712_199:
    raise RuntimeError('Frozen candidate/reference universe drift')
reference_count=len(L['ik'])
pool_count=len(pool.mass)
te=pq.read_table(TEST).to_pandas()
te['molecule_id']=te.molecule_id.astype(str)
te['nm']=neutral_mass(te.precursor_mz.values.astype(np.float64),te.adduct.values)
if not np.isfinite(te.nm).all():
    raise RuntimeError('Invalid query neutral mass')
sample=pd.read_csv(SAMPLE,dtype={'molecule_id':str})
if sample.molecule_id.duplicated().any() or set(te.molecule_id)!=set(sample.molecule_id):
    raise RuntimeError('Test/sample identity mismatch')
records,items=[],[]
for number,(mid,sub) in enumerate(te.groupby('molecule_id')):
    ev=evidence(sub)
    indices=pool.window(ev[0],CFG.PPM_WIN)
    if not len(indices):
        indices=pool.window(ev[0],CFG.PPM_FALLBACK)
    variant=score_variant(indices,[],sub,ev,{})
    for name in ['features','external_flags','mass_error_ppm']:
        variant.pop(name,None)
    # Preserve the previous baseline's explicitly reported empty-window fallback.
    fallback=not bool(variant['smiles'])
    selected=ranked_unique(variant['smiles'],variant['probabilities'],scorer_key,top_k=SUBMISSION_CONFIG['forward_top_k'])
    eligible=[variant['smiles'][i] for i in selected if forward_eligible(variant['smiles'][i])]
    measured=forward_spectra(sub)
    records.append({'molecule_id':mid,'variant':variant,'empty_window_fallback':fallback,
                    'candidate_count':len(indices),'spectra_count':len(sub),
                    'covered_spectra':len(measured),'eligible_forward_candidates':len(eligible)})
    # Protected library matches cannot change, so no forward compute is needed.
    if measured and eligible and variant['library_max']<SUBMISSION_CONFIG['library_gate']:
        items.append({'id':mid,'candidates':eligible,'spectra':measured})
    if number%10==0 or number==sample.shape[0]-1:
        save_json('inference_progress.json',{'phase':'features','completed':number+1,'expected':len(sample),'seconds':time.time()-T0})
        print('[SUBMISSION] Features',number+1,'/',len(sample),'seconds',round(time.time()-T0,1),flush=True)
save_json('inference_candidates.json',records)
save_json('forward_input.json',items)
save_json('inference_feature_manifest.json',{'configuration':SUBMISSION_CONFIG,'query_count':len(records),
    'candidates_sha256':file_hash('inference_candidates.json'),'forward_input_sha256':file_hash('forward_input.json'),
    'test_spectrum_count':len(te),'test_sha256':file_hash(TEST),'sample_sha256':file_hash(SAMPLE),
    'reference_spectra':reference_count,'candidate_pool_count':pool_count,'features_seconds':time.time()-T0})
del te,L,pool,rep,rep_key,rep_nm,RANKERS,_MODEL,ev,variant,sub
gc.collect()
torch.cuda.empty_cache()
forward={}
meta={'status':'not_needed','items_total':0,'items_done':0,'errors':[]}
if items:
    pkg=Path(find_file('PROVENANCE.json')).parent
    aux=Path(find_file('auxiliary_manifest.json')).parent
    python,child_env=prepare_forward_environment(pkg,aux,'/kaggle/tmp/submission_forward_site',
        provenance_hash=STACK_PROVENANCE_SHA256,auxiliary_hash=AUXILIARY_SHA256,device='cuda')
    command=[python,str(pkg/'runner/fwd_runner.py'),str(pkg),'batch','forward_input.json','forward_scores.json',
        '--models','glacier','--stack','none','--device','cuda','--bs',str(SUBMISSION_CONFIG['forward_batch_size']),'--budget','7200']
    print('[SUBMISSION] GLACIER starting',len(items),'molecules',flush=True)
    run=subprocess.run(command,capture_output=True,text=True,env=child_env,timeout=7500)
    Path('forward_run.log').write_text(run.stdout+'\n'+run.stderr)
    status=Path('forward_scores.json.meta.json')
    if not status.exists():
        raise RuntimeError('GLACIER produced no status')
    meta=json.loads(status.read_text())
    if run.returncode!=0 or meta['status']!='ok' or meta['errors'] or meta['items_done']!=len(items) or meta['device']!='cuda':
        raise RuntimeError('GLACIER failure: '+json.dumps(meta))
    raw=json.loads(Path('forward_scores.json').read_text())
    for item in items:
        values=raw[item['id']]['glacier']
        if len(values)!=len(item['candidates']) or not np.isfinite(np.asarray(values,float)).all():
            raise RuntimeError('Missing or invalid forward scores')
        forward[item['id']]=dict(zip(item['candidates'],values))
rows=[]
for record in records:
    mid=record['molecule_id']
    guesses=submission_smiles(record['variant'],forward.get(mid,{}),weight=SUBMISSION_CONFIG['forward_weight'],
        forward_top_k=SUBMISSION_CONFIG['forward_top_k'],library_gate=SUBMISSION_CONFIG['library_gate'])
    if record['empty_window_fallback']:
        guesses=['CCO']
    keys=[scorer_key(s) for s in guesses]
    if not 1<=len(guesses)<=25 or len(keys)!=len(set(keys)):
        raise RuntimeError('Invalid output guesses')
    rows.append({'molecule_id':mid,'smiles':';'.join(guesses)})
predictions=pd.DataFrame(rows)
submission=sample[['molecule_id']].merge(predictions,on='molecule_id',how='left',validate='one_to_one')
if submission.smiles.isna().any():
    raise RuntimeError('Missing output predictions')
submission.to_csv('submission.csv',index=False)
save_json('submission_complete.json',{'complete':True,'configuration':SUBMISSION_CONFIG,'query_count':len(submission),
    'submission_sha256':file_hash('submission.csv'),'kernel_sha256':file_hash(__file__),
    'feature_manifest_sha256':file_hash('inference_feature_manifest.json'),'forward_meta':meta,
    'empty_window_fallbacks':sum(r['empty_window_fallback'] for r in records),'reference_spectra':reference_count,
    'candidate_pool_count':pool_count,'elapsed_seconds':time.time()-T0,
    'versions':{n:importlib.metadata.version(n) for n in ['numpy','pandas','pyarrow','rdkit','scikit-learn','torch']}})
print('[SUBMISSION] COMPLETE',len(submission),'rows, runtime',round(time.time()-T0,1),'seconds',flush=True)
