from dataclasses import dataclass
import google.auth
import google.api_core
from google.cloud import container_v1
import kopf
from kubernetes.aio import client, config
from kubernetes.aio.client.api_client import ApiClient
import os
from typing import Any, Protocol

@dataclass
class Nodepool:
    name: str
    min_node_count: int
    max_node_count: int
    current_node_count: int
class CloudProvider(Protocol):
    """
    Abstract class that allows structural subtyping/duck typing of all cloud providers (see https://typing.python.org/en/latest/reference/protocols.html).
    """
    async def get_nodepool(self):
        ... # Note that `...` is a Python placeholder object

    async def set_min_node_count(self, min_node_count: int, nodepool: Nodepool):
        ...

    async def get_k8s_current_node_count(self):
        """
        Get current node count with Kubernetes API. We use this as the source of truth for the number of nodes online, rather than cloud provider specific APIs.
        """
        await config.load_kube_config()
        async with ApiClient() as api:
            v1 = client.CoreV1Api(api)
            node_list = await v1.list_node()
        node_count = len(node_list.items)
        return node_count
        
class GCPProvider(CloudProvider):
    """
    Methods for Google Cloud Platform (GCP).
    """
    def __init__(self, logger: kopf.Logger):
        self.cluster_name = os.environ.get("GCP_CLUSTER", "")
        self.machine_type = os.environ.get("GCP_MACHINE_TYPE", "")
        self.nodepool = os.environ.get("GCP_NODEPOOL", "")
        self.project_name = os.environ.get("GCP_PROJECT_ID", "")
        self.zone = os.environ.get("GCP_ZONE", "") # TODO: add support for regional clusters
        self.region = os.environ.get("GCP_REGION", "")
        self.prefix =  f"projects/{self.project_name}/zones/{self.zone}" if self.zone else f"projects/{self.project_name}/region/{self.region}"
        self.nodepool_name = self.prefix + f"/clusters/{self.cluster_name}/nodePools/{self.nodepool}"
        self.credentials_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        self.credentials, self.project = google.auth.default()
        self.client = None
        self.log = logger
        self.log.debug(self.credentials.get_cred_info())

    async def __aenter__(self):
        self.client = container_v1.ClusterManagerAsyncClient(
            credentials=self.credentials
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.client:
            await self.client.transport.close()

    async def _get_gcp_nodepool(self):
        request = container_v1.GetNodePoolRequest(
           name=self.nodepool_name
        )
        response = await self.client.get_node_pool(request=request)
        return response

    async def get_nodepool(self, gcp_nodepool, current_node_count: int | None):
        if not gcp_nodepool:
            gcp_nodepool = await self._get_gcp_nodepool()
        current_node_count = await self.get_k8s_current_node_count()
        nodepool = Nodepool(name=self.nodepool_name, min_node_count=gcp_nodepool.autoscaling.min_node_count, max_node_count=gcp_nodepool.autoscaling.max_node_count, current_node_count=current_node_count)
        return nodepool

    async def wait_gcp_operation(self, operation_name: str):
        """
        Blocking call to wait until operation is completed.
        """
        name = '/'.join([self.prefix, "operations", operation_name])
        self.log.debug(f'Operation name: {name}')
        request = container_v1.GetOperationRequest(name=name)
        while True:
            response = await self.client.get_operation(request=request)
            if response.status != container_v1.Operation.Status.DONE:
                self.log.debug(f'Operation is {container_v1.Operation.Status(response.status).name}')
            # TODO: backoff on error
            else:
                return response

    async def set_min_node_count(self, min_node_count: int):
        gcp_nodepool = await self._get_gcp_nodepool()
        if min_node_count >= gcp_nodepool.autoscaling.max_node_count:
            self.log.warning(f'Minimum node count {min_node_count} exceeds maximum node count.')
        elif min_node_count != gcp_nodepool.autoscaling.min_node_count:
            gcp_nodepool_autoscaling = container_v1.NodePoolAutoscaling(
                enabled = gcp_nodepool.autoscaling.enabled,
                min_node_count = min_node_count,
                max_node_count = gcp_nodepool.autoscaling.max_node_count,
                location_policy = gcp_nodepool.autoscaling.location_policy
            )
            request = container_v1.SetNodePoolAutoscalingRequest(
                name=self.nodepool_name,
                autoscaling=gcp_nodepool_autoscaling
            )
            operation = await self.client.set_node_pool_autoscaling(request=request)
            # Block until scaling operation is completed
            if operation:
                await self.wait_gcp_operation(operation_name = operation.name)
            # Update with new nodepool config
            gcp_nodepool = await self._get_gcp_nodepool()
            self.log.info(f'Minimum node count set to {gcp_nodepool.autoscaling.min_node_count}.')
        else:
            self.log.warning(f'Minimum node count is already set to {min_node_count}.')
        current_node_count = await self.get_k8s_current_node_count()
        nodepool = await self.get_nodepool(gcp_nodepool=gcp_nodepool, current_node_count=current_node_count)
        self.log.debug(f'{nodepool=}')
        return nodepool


def create_provider(logger: kopf.Logger):
    name = os.environ.get("K8S_NODE_OPERATOR_CLOUD_PROVIDER")
    if name == "GCP":
        return GCPProvider(logger=logger)

@kopf.on.create('nodepoolallocationtarget')
async def create_npat(spec: kopf.Spec, name: str, namespace: str | None, logger: kopf.Logger, **_: Any) -> None:
    # Parse npat spec
    min_node_count = spec.get('minimumNodeCount')
    if not min_node_count:
        min_node_count = 0
    # Send nodepool scaling request to cloud provider
    async with create_provider(logger=logger) as provider:
        nodepool = await provider.set_min_node_count(min_node_count=min_node_count)
    return {'status': 'SUCCESS', 'node_count': nodepool.current_node_count, 'min_node_count': nodepool.min_node_count, 'max_node_count': nodepool.max_node_count} # type: ignore

@kopf.on.update('nodepoolallocationtarget')
async def update_npat(spec: kopf.Spec, status: kopf.Status, logger: kopf.Logger, **_: Any):
    # Parse npat spec
    min_node_count = spec.get('minimumNodeCount')
    if not min_node_count:
        min_node_count = 0
    # Send nodepool scaling request to cloud provider
    async with create_provider(logger=logger) as provider:
        nodepool = await provider.set_min_node_count(min_node_count=min_node_count)
    return {'status': 'SUCCESS', 'node_count': nodepool.current_node_count, 'min_node_count': nodepool.min_node_count, 'max_node_count': nodepool.max_node_count} # type: ignore