from __future__ import annotations
import google.auth
import google.api_core
import kopf
import logging
import os
from abc import ABC
from google.cloud import container_v1
from types import TracebackType
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from k8s_autoscaler_plugins.base import Nodepool
from k8s_autoscaler_plugins.const import ERROR_DELAY

class CloudProvider(ABC):
    """
    Abstract base class with Kubernetes API methods and standardizes the construction of all cloud providers (see https://peps.python.org/pep-3119/).
    """
    def __init__(self, logger: kopf.Logger | None = None, timeout: int = 300, interval: int = 10):
        if logger:
            self.log = logger
        else:
            self.log = logging.getLogger(__name__)

    async def __aenter__(self):
        ... # Note that `...` is a Python placeholder object

    async def __aexit__(self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None):
        ...

    async def get_nodepool(self, name: str, zone: str | None = None, region: str | None = None):
        ...

    async def set_min_node_count(self, nodepool: Nodepool):
        ...
        
class GCPProvider(CloudProvider):
    """
    Methods for Google Cloud Platform (GCP).
    """
    def __init__(self, logger: kopf.Logger | None = None):
        super().__init__(logger=logger)
        self.project_name = os.environ.get('GCP_PROJECT_ID', '')
        self.cluster_location = os.environ.get('GCP_LOCATION', '')
        self.cluster_name = os.environ.get('GCP_CLUSTER', '')
        self.credentials_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        self.credentials, self.project = google.auth.default()
        self.log.debug(self.credentials.get_cred_info())

    async def __aenter__(self):
        self.client = container_v1.ClusterManagerAsyncClient(
            credentials=self.credentials
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.client.transport.close()

    def _get_prefix_project(self) -> str:
        return f"projects/{self.project_name}"

    def _get_prefix_location(self, location: bool = False, zone: str | None = None, region: str | None = None) -> str:
        if location:
            return '/'.join([self._get_prefix_project(), f'locations/{self.cluster_location}'])
        else:
            return '/'.join([self._get_prefix_project(), f'zones/{zone}']) if zone else '/'.join([self._get_prefix_project(), f'region/{region}'])

    def _get_prefix_cluster(self, location: bool = False, zone: str | None = None, region: str | None = None):
        prefix = self._get_prefix_location(location, zone, region)
        request_name = '/'.join([prefix, f"clusters/{self.cluster_name}"]) # TODO: use YARL
        return request_name

    def _get_request_nodepool(self, name: str, zone: str | None = None, region: str | None = None):
        prefix = self._get_prefix_cluster(zone=zone, region=region)
        request_name = '/'.join([prefix, f"nodePools/{name}"]) # TODO: use YARL
        return request_name

    def _list_request_nodepool(self, location: bool = True, zone: str | None = None, region: str | None = None):
        request_name = self._get_prefix_cluster(location, zone, region)
        return request_name

    def _get_gcp_nodepool_limits(self, gcp_nodepool: container_v1.NodePool) -> dict:
        """
        Helper method to determine whether nodepool autoscaler limits are total (returns True) or zonal (returns False), and returns values. Total and zonal limits are mutually exclusive.
        """
        if gcp_nodepool.autoscaling.min_node_count == 0 and gcp_nodepool.autoscaling.max_node_count == 0:
            return {
                'min': gcp_nodepool.autoscaling.total_min_node_count,
                'max': gcp_nodepool.autoscaling.total_max_node_count
            }
        elif gcp_nodepool.autoscaling.total_min_node_count == 0 and gcp_nodepool.autoscaling.total_max_node_count == 0:
            return {
                'min': gcp_nodepool.autoscaling.min_node_count,
                'max': gcp_nodepool.autoscaling.max_node_count
            }
        else:
            raise kopf.TemporaryError('Unable to determine whether nodepool limits are total or zonal.', delay=ERROR_DELAY)

    async def _get_gcp_nodepool(self, name: str, zone: str | None = None, region: str | None = None) -> container_v1.NodePool:
        """
        Request a vendor-specific GCP nodepool.
        """
        request_name = self._get_request_nodepool(name, zone, region)
        request = container_v1.GetNodePoolRequest(
           name=request_name
        )
        nodepool = await self.client.get_node_pool(request=request)
        return nodepool

    async def get_nodepool(self, name: str, zone: str | None = None, region: str | None = None) -> dict:
        """
        Get non-vendor-specific nodepool config.
        """
        gcp_nodepool = await self._get_gcp_nodepool(name, zone, region)
        nodepool_limit = self._get_gcp_nodepool_limits(gcp_nodepool)
        return {
            'name': name,
            'min_node_count': nodepool_limit['min'],
            'max_node_count': nodepool_limit['max']
        } 
    
    async def list_nodepool(self, label_selector: str = '', zone: str | None = None, region: str | None = None) -> list[dict]:
        """
        Convert vendor-specific nodepool list to vendor-agnostic nodepool list.
        """
        request_parent = self._list_request_nodepool(zone = zone, region = region)
        request = container_v1.ListNodePoolsRequest(parent=request_parent)
        response = await self.client.list_node_pools(request)
        nodepool_list = []
        for nodepool in list(response.node_pools):
            if label_selector:
                label_selector_split = label_selector.split('=')
                label_selector_name = label_selector_split[0]
                label_selector_value = label_selector_split[1]
                label_dict = dict(nodepool.config.labels)
                if {label_selector_name: label_selector_value} == label_dict:
                    nodepool_dict = {
                            'name': nodepool.name,
                            'zone': zone if zone else self.cluster_location,
                            'region': region if region else self.cluster_location,
                            'label_selector': label_selector
                            }
            else:
                # Split location into region and zone
                if self.cluster_location:
                    cluster_location_split = self.cluster_location.split('-')
                    region = ''.join(cluster_location_split[0:2])
                    zone = self.cluster_location if len(cluster_location_split) == 3 else ''
                nodepool_dict = {
                        'name': nodepool.name,
                        'zone': zone,
                        'region': region,
                        'label_selector': ''
                        }
            nodepool_list.append(nodepool_dict)
        return nodepool_list

    async def wait_gcp_operation(self, operation_name: str, zone: str | None = None, region: str | None = None) -> container_v1.Operation:
        """
        Blocking call to wait until operation is completed.
        """
        name = '/'.join([self._get_prefix_location(zone=zone, region=region), "operations", operation_name])
        request = container_v1.GetOperationRequest(name=name)
        while True:
            response = await self.client.get_operation(request=request)
            if response.status != container_v1.Operation.Status.DONE:
                self.log.debug(f'Operation is {container_v1.Operation.Status(response.status).name}')
            # TODO: backoff on error
            else:
                return response

    async def set_min_node_count(self, nodepool: Nodepool) -> None:
        """
        Set the autoscaling minimum node count of a GCP nodepool.
        """
        target_min_node_count = nodepool.target_min_node_count
        gcp_nodepool = await self._get_gcp_nodepool(name=nodepool.name, zone=nodepool.zone, region=nodepool.region)
        nodepool_limit = self._get_gcp_nodepool_limits(gcp_nodepool)
        # Decide whether to scale
        if target_min_node_count >= nodepool_limit['max']:
            raise kopf.TemporaryError(f'Target minimum node count {target_min_node_count} exceeds maximum node count of {nodepool_limit['max']}.', delay=ERROR_DELAY)
        elif target_min_node_count != nodepool_limit['min']:
            gcp_nodepool_autoscaling = container_v1.NodePoolAutoscaling(
                enabled = gcp_nodepool.autoscaling.enabled,
                min_node_count = target_min_node_count,
                max_node_count = nodepool_limit['max'],
                location_policy = gcp_nodepool.autoscaling.location_policy
            )
            request_name = self._get_request_nodepool(nodepool.name, nodepool.zone, nodepool.region)
            request = container_v1.SetNodePoolAutoscalingRequest(
                name=request_name,
                autoscaling=gcp_nodepool_autoscaling
            )
            try:
                operation = await self.client.set_node_pool_autoscaling(request=request)
                self.log.debug(f'{operation.name=}')
            except google.api_core.exceptions.FailedPrecondition as e:
                # This can happen e.g. if nodepool state is already busy running another operation. Kopf will retry the handler again on TemporaryError
                raise kopf.TemporaryError(f"{e}", delay=ERROR_DELAY)
            # Block until current scaling operation is completed
            if operation:
                await self.wait_gcp_operation(operation_name = operation.name, zone = nodepool.zone, region = nodepool.region)
            self.log.debug(f'Minimum node count {target_min_node_count} request sent to cloud provider.')
        else:
            self.log.debug(f'Minimum node count is already set to {target_min_node_count}.')                

class TestProvider(CloudProvider):
    """
    No-op cloud provider for testing and mocking.
    """
    def __init__(self, logger: kopf.Logger | None = None):
        super().__init__(logger=logger)
        self._entered = False
        self._exited = False

    async def __aenter__(self):
        self._entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._exited = True

    async def get_nodepool(self, name: str, zone: str | None = None, region: str | None = None) -> dict:
        data = {
            'name': name,
            'min_node_count': 0,
            'max_node_count': 2
        }
        return data

    async def set_min_node_count(self, nodepool: Nodepool) -> None:
        ...
        


def create_provider(name: str, logger: kopf.Logger | None = None) -> CloudProvider:
    if name == "GCP":
        return GCPProvider(logger = logger)
    elif name == "TEST":
        return TestProvider(logger = logger)
    else:
        raise ValueError(f"Provider name '{name}' not recognized.")
