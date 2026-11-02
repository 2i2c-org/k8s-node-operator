import pytest
import subprocess
from k8s_autoscaler_plugins.base import Node, Nodepool, KubernetesClient
from .utils import generate_test_npat_file

# TODO:
# - request different fixture_node_index fixtures for different cloud providers in future

@pytest.mark.asyncio
class TestNode:

    label_selector = 'topology.kubernetes.io/zone=us-central1-b'
    zone = 'us-central1-b'

    async def test_list_node(self, fixture_node_index):
        node_list = await Node.list_node(index=fixture_node_index)
        assert len(node_list) == 2

    async def test_list_node_label_selector(self, fixture_node_index):
        node_list = await Node.list_node(index=fixture_node_index, label_selector=self.label_selector)
        assert len(node_list) == 1
        node = node_list[0]
        assert node.zone == self.zone

@pytest.mark.asyncio
class TestNodepool:

    label_selector = 'topology.kubernetes.io/zone=us-central1-b'
    name = 'test-pool-1'
    zone = 'us-central1-b'
    current_node_count = 1

    async def test_list_nodepool(self, fixture_node_index):
        node_list = await Node.list_node(index=fixture_node_index)
        nodepool_list = await Nodepool.list_nodepool(node_list=node_list)
        assert len(nodepool_list) == 2
        nodepool = nodepool_list[0]
        assert nodepool.current_node_count == self.current_node_count

    async def test_list_nodepool_label_selector(self, fixture_node_index):
        node_list = await Node.list_node(index=fixture_node_index, label_selector=self.label_selector)
        nodepool_list = await Nodepool.list_nodepool(node_list=node_list)
        assert len(nodepool_list) == 1
        nodepool = nodepool_list[0]
        assert nodepool.name == self.name
        assert nodepool.zone == self.zone
        assert nodepool.current_node_count == self.current_node_count
    

@pytest.mark.asyncio
class TestKubernetesClient:

    npat_name = 'test-npat'
    target_min_node_count = 1

    async def test_get_custom_resource_object(self, kind_cluster):
        npat_file = generate_test_npat_file(name=self.npat_name, target_min_node_count=self.target_min_node_count)
        subprocess.run('kubectl apply -f' + npat_file, shell=True, check=True)
        async with KubernetesClient() as client:
            obj = await client.get_custom_resource_object(name=self.npat_name)
        assert obj['metadata']['name'] == self.npat_name
        assert int(obj['spec']['plugins']['always_on']['minimum']) == self.target_min_node_count  # TODO: spec.plugins is subject to change