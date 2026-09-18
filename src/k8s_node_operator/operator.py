import kopf
import os
from typing import Any
from k8s_node_operator.providers import create_provider

@kopf.on.create('nodepoolallocationtarget')
@kopf.on.update('nodepoolallocationtarget')
async def create_npat(spec: kopf.Spec, name: str, namespace: str | None, logger: kopf.Logger, **_: Any) -> None:
    # Parse npat spec
    target_min_node_count = spec.get('minimumNodeCount')
    if not target_min_node_count:
        target_min_node_count = 0
    # Send nodepool scaling request to cloud provider
    provider_name = os.environ.get("K8S_NODE_OPERATOR_CLOUD_PROVIDER")
    async with create_provider(name=provider_name, logger=logger) as provider:
        nodepool = await provider.set_min_node_count(target_min_node_count=target_min_node_count)
    # Store returned output into npat object
    return {'status': 'SUCCESS', 'nodepool_name': nodepool.name, 'node_count': nodepool.current_node_count, 'min_node_count': nodepool.min_node_count, 'max_node_count': nodepool.max_node_count, 'target_min_node_count': nodepool.target_min_node_count} # type: ignore
