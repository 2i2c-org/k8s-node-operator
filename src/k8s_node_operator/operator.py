import kopf
import logging
import os
import yaml
import google.auth
import google.api_core
from google.cloud import container_v1
from typing import Any

logger = logging.getLogger(__name__)

class GCPClient:
    def __init__(self):
        self.cluster_name = os.environ.get("GCP_CLUSTER")
        self.machine_type = os.environ.get("GCP_MACHINE_TYPE")
        self.nodepool = os.environ.get("GCP_NODEPOOL")
        self.project_name = os.environ.get("GCP_PROJECT_ID")
        self.zone = os.environ.get("GCP_ZONE") # TODO: add support for regional clusters
        self.prefix =  f"projects/{self.project_name}/zones/{self.zone}" if self.zone else f"projects/{self.project_name}/region/{self.region}"
        self.nodepool_name = self.prefix + f"/clusters/{self.cluster_name}/nodePools/{self.nodepool}"
        self.credentials_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        self.credentials, self.project = google.auth.default()
        self.client = container_v1.ClusterManagerAsyncClient(
            credentials=self.credentials
        )
        logger.debug(self.credentials.get_cred_info())

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.client.transport.close()

    async def get_nodepool(self):
        request = container_v1.GetNodePoolRequest(
           name=self.nodepool_name
        )
        return await self.client.get_node_pool(request=request)

    async def update_autoscaling_min_node_count(self, min_node_count: int):
        nodepool = await self.get_nodepool()
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
        return await self.client.set_node_pool_autoscaling(request=request)

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
            else:
                return response


@kopf.on.create('nodepoolallocationtarget')
async def create_fn(spec: kopf.Spec, name: str, namespace: str | None, logger: kopf.Logger, **_: Any) -> None:
    # Parse spec
    min_node_count = spec.get('minimumNodeCount')
    if not min_node_count:
        min_node_count = 0
    # Populate npat template with spec
    path = os.path.join(os.path.dirname(__file__), 'npat_template.yaml')
    tmpl = open(path, 'rt').read()
    text = tmpl.format(name=name, minimumNodeCount=min_node_count)
    data = yaml.safe_load(text)
    # Send nodepool scaling request according to npat spec
    async with GCPClient() as client:
        operation = await client.update_autoscaling_min_node_count(int(data["spec"]["minimumNodeCount"]))
        logger.info(f'npat requested')
        # Determine if scaling operation is completed
        response = await client.wait_gcp_operation(operation.name)
        logger.info(f'{response.progress=}')
