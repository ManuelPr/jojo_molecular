"""Remove evaluation SIDs from a verified public CSR cache without changing its catalog."""
from pathlib import Path
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq


def exclude_sids(state, excluded_keys, output):
    if state['path'] is None:
        return state
    source=Path(state['path']); output=Path(output);output.mkdir(parents=True,exist_ok=True)
    structures=pq.read_table(source/'train_structs.parquet',columns=['inchikey14','sid']).to_pandas()
    blocked=structures.loc[structures.inchikey14.astype(str).isin(excluded_keys),'sid'].to_numpy()
    sids=pq.read_table(source/'spec_meta.parquet',columns=['sid']).column(0).to_numpy()
    keep=~np.isin(sids,blocked);removed=int((~keep).sum())
    if not removed:return dict(state,identity_filter_removed=0)
    if np.any(~keep[:state['base_rows']]):raise ValueError('Excluded SID leaked into prefiltered base references')
    offsets=np.load(source/'spec_off.npy',mmap_mode='r');counts=np.diff(offsets)[keep]
    newoff=np.r_[0,np.cumsum(counts,dtype=np.int64)];np.save(output/'spec_off.npy',newoff)
    for name in ['spec_mz.npy','spec_it.npy']:
        values=np.load(source/name,mmap_mode='r');dest=np.lib.format.open_memmap(output/name,mode='w+',dtype=values.dtype,shape=(int(newoff[-1]),))
        # Copy contiguous retained runs rather than allocating a dense peak mask.
        boundaries=np.r_[0,np.flatnonzero(keep[1:]!=keep[:-1])+1,len(keep)];pos=0
        for a,b in zip(boundaries[:-1],boundaries[1:]):
            if keep[a]:
                x,y=int(offsets[a]),int(offsets[b]);dest[pos:pos+y-x]=values[x:y];pos+=y-x
        dest.flush();del dest
    pf=pq.ParquetFile(source/'spec_meta.parquet');position=0
    with pq.ParquetWriter(output/'spec_meta.parquet',pf.schema_arrow) as writer:
        for batch in pf.iter_batches(batch_size=65536):
            table=pa.Table.from_batches([batch]);selection=keep[position:position+batch.num_rows];position+=batch.num_rows
            writer.write_table(table.filter(pa.array(selection)))
    if not (output/'train_structs.parquet').exists():(output/'train_structs.parquet').symlink_to((source/'train_structs.parquet').resolve())
    result=dict(state,path=str(output.resolve()),added=state['added']-removed,keys=int(np.unique(sids[state['base_rows']:][keep[state['base_rows']:]]).size),identity_filter_removed=removed)
    return result
