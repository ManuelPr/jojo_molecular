"""Run one bounded F0 evidence collection followed by fixed G3 diagnostics.

Uses only the existing allocation and environment. No Kaggle API or scheduler
submission. Launch from the repository's existing Python with a detached log.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    os.chdir(ROOT)
    out = ROOT / 'artifacts/cluster/g3-dev200-2545'
    previous = ROOT / 'artifacts/cluster/f0-g1-2545'
    assert os.environ.get('SLURM_JOB_ID') == '2545', 'Run only in the existing allocation'
    contract = json.loads((out / 'competition/contract.json').read_text())
    assert contract['query_count'] == 200
    pilot_truth = json.loads((previous/'competition/contract.json').read_text())['truth']
    assert not set(contract['truth']) & set(pilot_truth)
    assert not set(contract['truth'].values()) & set(pilot_truth.values())
    for name in ['complete-assets-manifest.json', 'runtime-versions.json']:
        target = out / name
        if not target.exists():
            target.symlink_to(previous / name)
    os.environ.update(PYTHONUNBUFFERED='1', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2',
                      OPENBLAS_NUM_THREADS='2', CASMI_SIMULATOR_BUDGET='1800',
                      PYTHONPATH=os.pathsep.join(map(str, [previous/'runtime', ROOT/'src', ROOT/'scripts/cluster'])))
    record = dict(started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                  pid=os.getpid(), job='2545', query_count=200, status='collecting_evidence',
                  control='F0 fixed public recipe; reference-identity exclusion',
                  excluded_pilot_queries=16, simulator_budget_seconds_each=1800,
                  pipeline_cap_seconds=10800, ram_guard_gib=26,
                  g2_started=False, g4_started=False,
                  scientific_limit='Public-panel diagnostic; pretrained exclusion unverified',
                  hypothesis='Learn conditional weighting and missing-evidence handling from a larger fixed-pool replay.',
                  comparison='Five identity-grouped OOF folds: existing heuristics, fixed LambdaRank, fixed neural listwise scorer.',
                  promotion='No automatic promotion; frozen splits and Kaggle F0 unchanged.',
                  scripts_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in [Path(__file__), ROOT/'scripts/cluster/run_f0_control.py',
                                            ROOT/'scripts/cluster/train_g3_fusion.py', ROOT/'scripts/cluster/f0_g1_evidence.py']})
    manifest = out / 'run-manifest.json'
    def save():
        manifest.write_text(json.dumps(record, indent=2) + '\n')
    save()
    command = [sys.executable, 'scripts/cluster/profile_command.py', '--output', str(out/'control-profile'),
               '--timeout', '10800', '--ram-gib', '26', '--', sys.executable,
               'scripts/cluster/run_f0_control.py', '--assets', str(ROOT/'data/fastweb'),
               '--competition', str(out/'competition'), '--notebook',
               str(ROOT/'artifacts/cluster/f0-gu-v492-latest-audit/casmi26-v492-dg-v19.ipynb'),
               '--output', str(out/'control'), '--simulator-site',
               str(ROOT/'artifacts/cluster/simulator-load-2545-20261022/site')]
    try:
        result = subprocess.run(command, check=False)
        record['f0_returncode'] = result.returncode
        record['status'] = 'f0_failed' if result.returncode else 'training_fusion'
        save()
        if result.returncode:
            return
        result = subprocess.run([sys.executable, 'scripts/cluster/profile_command.py',
                                 '--output', str(out/'fusion-profile'), '--timeout', '600', '--ram-gib', '26',
                                 '--', sys.executable, 'scripts/cluster/train_g3_fusion.py',
                                 '--control', str(out/'control'), '--contract', str(out/'competition/contract.json'),
                                 '--output', str(out/'fusion')], check=False)
        record.update(fusion_returncode=result.returncode,
                      status='fusion_failed' if result.returncode else 'complete')
    except Exception as exc:
        record.update(status='orchestration_failed', error_type=type(exc).__name__)
        raise
    finally:
        record['updated_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        save()


if __name__ == '__main__':
    main()
