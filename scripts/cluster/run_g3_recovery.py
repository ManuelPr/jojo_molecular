"""Complete interrupted G3 evidence and then train, after the authorized F0 submit."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    os.chdir(ROOT)
    out = ROOT/'artifacts/cluster/g3-dev200-2545'
    assert os.environ.get('SLURM_JOB_ID') == '2545'
    receipt = json.loads((ROOT/'artifacts/kaggle/f0-gu-v1/finalizer-state.json').read_text())
    assert receipt['status'] == 'submitted'
    os.environ.update(PYTHONUNBUFFERED='1', OMP_NUM_THREADS='2', MKL_NUM_THREADS='2', OPENBLAS_NUM_THREADS='2',
                      CASMI_SIMULATOR_BUDGET='1800',
                      PYTHONPATH=os.pathsep.join(map(str, [ROOT/'artifacts/cluster/f0-g1-2545/runtime', ROOT/'src', ROOT/'scripts/cluster'])))
    state = dict(status='recovering_forward', pid=os.getpid(), job=2545, submission_ref=receipt['submission_ref'],
                 source_sha256={name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                                ['scripts/cluster/recover_g3_forward.py', 'scripts/cluster/train_g3_fusion.py']})
    path = out/'recovery-state.json'
    def save():
        path.write_text(json.dumps(state, indent=2)+'\n')
    save()
    rc = subprocess.call([sys.executable, 'scripts/cluster/profile_command.py', '--output', str(out/'recovery-profile'),
                          '--timeout', '3600', '--ram-gib', '26', '--', sys.executable, 'scripts/cluster/recover_g3_forward.py'])
    state.update(recovery_returncode=rc, status='recovery_failed' if rc else 'training_fusion')
    save()
    if rc:
        return
    rc = subprocess.call([sys.executable, 'scripts/cluster/profile_command.py', '--output', str(out/'fusion-profile'),
                          '--timeout', '600', '--ram-gib', '26', '--', sys.executable, 'scripts/cluster/train_g3_fusion.py',
                          '--control', str(out/'control'), '--contract', str(out/'competition/contract.json'),
                          '--output', str(out/'fusion')])
    state.update(training_returncode=rc, status='training_failed' if rc else 'complete')
    save()


if __name__ == '__main__':
    main()
