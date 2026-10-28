"""Bound a local cluster process group and record cgroup/GPU resource samples."""
from __future__ import annotations
import argparse,json,os,signal,subprocess,time
from pathlib import Path

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=float,default=1800);p.add_argument('--ram-gib',type=float,default=26);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args();cmd=a.command[1:] if a.command[:1]==['--'] else a.command
 a.output.mkdir(parents=True,exist_ok=True)
 rel=Path('/proc/self/cgroup').read_text().strip().split('::')[-1];cg=Path('/sys/fs/cgroup')/rel.lstrip('/')
 while not (cg/'memory.current').exists() and cg!=Path('/sys/fs/cgroup'):cg=cg.parent
 start=time.monotonic();samples=[];reason=None
 with (a.output/'run.log').open('w') as log:
  proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  while proc.poll() is None:
   elapsed=time.monotonic()-start
   mem=int((cg/'memory.current').read_text()) if (cg/'memory.current').exists() else None
   gpu=subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True,capture_output=True,timeout=10)
   row=dict(seconds=elapsed,cgroup_bytes=mem,gpu=gpu.stdout.strip());samples.append(row)
   with (a.output/'resources.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
   if elapsed>a.timeout or (mem is not None and mem>a.ram_gib*1024**3):
    reason='time_budget' if elapsed>a.timeout else 'ram_guard';os.killpg(proc.pid,signal.SIGTERM)
    try:proc.wait(timeout=20)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL)
    break
   time.sleep(2)
  proc.wait()
 summary=dict(returncode=proc.returncode,stop_reason=reason,wall_seconds=time.monotonic()-start,cgroup=str(cg),peak_cgroup_sample_bytes=max((s['cgroup_bytes'] or 0 for s in samples),default=0),peak_gpu_sample_mib=max((int(s['gpu'].split(',')[0]) for s in samples if s['gpu']),default=0),memory_events=(cg/'memory.events').read_text() if (cg/'memory.events').exists() else None,notes='cgroup and nvidia-smi include other job processes; sampling is not exact per-process peak')
 (a.output/'profile.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary));raise SystemExit(proc.returncode if proc.returncode>=0 else 1)
if __name__=='__main__':main()
