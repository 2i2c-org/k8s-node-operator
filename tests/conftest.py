import logging
import json
import pytest
import subprocess
from pathlib import Path
from k8s_autoscaler_plugins.providers import create_provider

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).parent.parent
SRC_DIR = PROJECT_DIR.joinpath('src/k8s_autoscaler_plugins')
TEST_DIR = PROJECT_DIR.joinpath('tests')
CRD_FILE = PROJECT_DIR.joinpath('helm/k8s_autoscaler_plugins/crds/nodepool_allocation_target.yaml')


@pytest.fixture(scope='class')
def kind_cluster():
    """
    A [kind cluster](https://kind.sigs.k8s.io/) for running a local Kubernetes cluster.
    
    Note: If the cluster is not destroyed properly, e.g. an error while developing the test suite, then this raises a 'CalledProcessError' the next time you run the tests. Manually destroy the cluster with `kind delete cluster --name test-cluster` before running the test suite again.
    """
    subprocess.run(
        ["kind", "create", "cluster", "--name", "test-cluster"],
        check=True
    )
    # Install npat crd
    subprocess.run(
        ["kubectl", "apply", "-f", CRD_FILE],
        check=True
    )
    # Assert npat crd is installed
    output = subprocess.check_output(
      ["kubectl", "get", "crds"]
    )
    assert "nodepoolallocationtargets.jupyter.org" in output.decode('utf-8')
    # Yield and delete when done
    try:
        yield
    finally:
        subprocess.run(
          ["kind", "delete", "cluster", "--name", "test-cluster"],
          check=True
        )

@pytest.fixture(scope='session')
def provider():
    """
    Use no-op cloud provider for testing.
    
    Note: kopfRunner instantiates a provider within the handler routine, but we provide another instance as a fixture so that we can access its attributes for test assertions.
    """
    provider = create_provider(name="TEST", logger=logger)
    yield provider

@pytest.fixture(scope='session')
def fixture_node_index():
    """
    Fixture of in-memory Kubernetes nodes indexed by kopf.

    TODO: generalise for other cloud providers
    """
    with open(f'{TEST_DIR}/fixtures/node_index.json', 'r') as f:
        data = json.load(f)
    yield data

@pytest.fixture(scope='session')
def fixture_node():
    """
    Fixture of a Kubernetes node to be indexed.
    
    TODO: generalise for other cloud providers
    """
    with open(f'{TEST_DIR}/fixtures/node.json', 'r') as f:
        data = json.load(f)
    yield data