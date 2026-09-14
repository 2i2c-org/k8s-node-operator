import subprocess
import time
from kopf.testing import KopfRunner
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
SRC_DIR = PROJECT_DIR.joinpath('src/k8s_node_operator')

def test_npat_create_and_delete():
    with KopfRunner(['run', '-A', '--verbose', SRC_DIR.joinpath('operator.py').as_posix()]) as runner:
        subprocess.run('kubectl apply -f' + SRC_DIR.joinpath('npat.yaml').as_posix(), shell=True, check=True)
        time.sleep(1)
        subprocess.run('kubectl delete -f' + SRC_DIR.joinpath('npat.yaml').as_posix(), shell=True, check=True)
        time.sleep(1)

    assert runner.exit_code == 0
    assert runner.exception is None
    assert 'NodepoolAllocationTarget' in runner.output
    assert '"spec":{"minimumNodeCount":0}}' in runner.output
    assert 'Deleted, really deleted' in runner.output
