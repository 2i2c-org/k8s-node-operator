import google.auth
import google.api_core
from google.cloud import container_v1
import kopf
from kubernetes.aio import client, config
from kubernetes.aio.client.api_client import ApiClient
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

class GCPClient:
    def __init__(self):
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
        logger.debug(self.credentials.get_cred_info())

    async def __aenter__(self):
        self.client = container_v1.ClusterManagerAsyncClient(
            credentials=self.credentials
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.client:
            await self.client.transport.close()

    async def get_nodepool(self):
        request = container_v1.GetNodePoolRequest(
           name=self.nodepool_name
        )
        return await self.client.get_node_pool(request=request)

    async def update_autoscaling_min_node_count(self, min_node_count: int, nodepool):
        if min_node_count >= nodepool.autoscaling.max_node_count:
            logger.error(f'Minimum node count {min_node_count} exceeds maximum node count.')
            return # TODO: update Status
        elif min_node_count != nodepool.autoscaling.min_node_count:
            nodepool_autoscaling = container_v1.NodePoolAutoscaling(
                enabled = nodepool.autoscaling.enabled,
                min_node_count = min_node_count,
                max_node_count = nodepool.autoscaling.max_node_count,
                location_policy = nodepool.autoscaling.location_policy
            )
            request = container_v1.SetNodePoolAutoscalingRequest(
                name=self.nodepool_name,
                autoscaling=nodepool_autoscaling
            )
            logger.info(f'Nodepool Allocation Target requested.')
            return await self.client.set_node_pool_autoscaling(request=request)
        else:
            logger.info(f'Minimum node count is already set to {min_node_count}.')
            return # TODO: update status

    async def wait_gcp_operation(self, operation_name: str):
        """
        Blocking call to wait until operation is completed.
        """
        name = '/'.join([self.prefix, "operations", operation_name])
        logger.debug(f'{name=}')
        request = container_v1.GetOperationRequest(name=name)
        while True:
            response = await self.client.get_operation(request=request)
            if response.status != container_v1.Operation.Status.DONE:
                logger.info(f'Operation is {container_v1.Operation.Status(response.status).name}')
            # TODO: backoff on error
            else:
                return response

@kopf.on.create('nodepoolallocationtarget')
async def create_npat(spec: kopf.Spec, name: str, namespace: str | None, logger: kopf.Logger, **_: Any) -> None:
    # Parse npat spec
    min_node_count = spec.get('minimumNodeCount')
    if not min_node_count:
        min_node_count = 0
    # Send nodepool scaling request to cloud provider
    async with GCPClient() as gke:
        nodepool = await gke.get_nodepool()
        operation = await gke.update_autoscaling_min_node_count(min_node_count, nodepool)
        # Block until scaling operation is completed
        if operation:
            response = await gke.wait_gcp_operation(operation.name)
            logger.debug(f'{response.progress=}')
        # Get updated nodepool
        nodepool = await gke.get_nodepool()
    # Block on current node count with k8s api until minimum nodepool count is achieved
    await config.load_kube_config()
    node_count = 0
    while node_count < min_node_count:
        async with ApiClient() as api:
            v1 = client.CoreV1Api(api)
            node_list = await v1.list_node()
        node_count = len(node_list.items)
        logger.info(f'Node count = {node_count}.')
    return {'status': 'SUCCESS', 'node_count': node_count, 'min_node_count': nodepool.autoscaling.min_node_count, 'max_node_count': nodepool.autoscaling.max_node_count}

# TODO: we want to update/patch the npat, so change create_fn to first instantiation, and convert current fn to an update_fn to respond to a kubectl patch/update