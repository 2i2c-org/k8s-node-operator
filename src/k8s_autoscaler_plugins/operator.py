import kopf
from typing import Any
from k8s_autoscaler_plugins.base import Node, Nodepool, NodepoolState
from k8s_autoscaler_plugins.const import RETRY_LIMIT, ERROR_DELAY
from k8s_autoscaler_plugins.utils import calculate_target_min_node_count_from_plugins

# Nodepool allocation target (npat) custom resource

@kopf.on.create('nodepoolallocationtarget') # type: ignore[arg-type]
@kopf.on.update('nodepoolallocationtarget') # type: ignore[arg-type]
async def nodepool_allocation(spec: kopf.Spec, logger: kopf.Logger, k8s_nodes: kopf.Index, **kwargs: Any) -> dict:
    """
    Set minimum node count of selected nodepools. 
    """
    # List nodepools that match the node label selector
    label_selector = spec.get('nodepoolSelector', {})
    node_list = await Node.list_node(label_selector=label_selector, index=k8s_nodes)
    nodepool_list = await Nodepool.list_nodepool(node_list)
    npat_status = Nodepool.get_status_list(nodepool_list, NodepoolState.UPDATING.name)
    return npat_status

@kopf.on.delete('nodepoolallocationtarget') # type: ignore[arg-type]
async def delete_nodepool_allocation(spec: kopf.Spec, k8s_nodes: kopf.Index, logger: kopf.Logger, retries = RETRY_LIMIT, **kwargs: Any) -> dict | None:
    """
    Set minimum node count to 0 on delete.
    """
    label_selector = spec.get('nodepoolSelector', {})
    target_min_node_count = 0
    # List k8s nodepools with node label selector
    node_list = await Node.list_node(label_selector=label_selector, index = k8s_nodes)
    nodepool_list = await Nodepool.list_nodepool(node_list)
    for nodepool in nodepool_list:
        if nodepool.min_node_count != nodepool.target_min_node_count:
            await nodepool.set_min_node_count(target_min_node_count)
            raise kopf.TemporaryError(f'[{nodepool.name}] Cloud provider minimum node count target state of {nodepool.min_node_count} not reached', delay=ERROR_DELAY)
        else:
            logger.info(f'[{nodepool.name}] Cloud provider minimum node count target state of {nodepool.min_node_count} reached')
            npat_status = Nodepool.get_status_list(nodepool_list, NodepoolState.READY.name)
            return npat_status
    return None


@kopf.index('nodes')
def k8s_nodes(body: kopf.Body, labels: kopf.Labels, logger: kopf.Logger, **kwargs: Any) -> dict | None:
    """
    Keep in-memory index of ready k8s nodes to avoid multiple k8s API calls.
    """
    conditions = body['status']['conditions']
    for c in conditions:
        if c['type'] == 'Ready':
            if c['status'] == 'True':
                return {label: value for label, value in labels.items()}
            else:
                pass
        else:
            pass
    return None

@kopf.timer('nodepoolallocationtarget', interval=10) # type: ignore[arg-type]
async def reconcile_provider(spec: kopf.Spec, status: kopf.Status, name: str, k8s_nodes: kopf.Index, patch: kopf.Patch, logger: kopf.Logger, retry: int, **kwargs: Any) -> None:
    """
    Regularly reconcile target minimum node count is equal to cloud provider config.
    """
    if status.get('nodepool_allocation', {}).get('status', '') == NodepoolState.ERROR.name:
        raise kopf.PermanentError(f'Nodepool allocation target [{name}] in {NodepoolState.ERROR.name} status')
    label_selector = spec.get('nodepoolSelector', {})
    node_list = await Node.list_node(label_selector=label_selector, index=k8s_nodes)
    nodepool_list = await Nodepool.list_nodepool(node_list)
    for nodepool in nodepool_list:
        # Invoke plugin handlers to get nodepool target minimum node count
        nodepool = calculate_target_min_node_count_from_plugins(nodepool, spec, logger)
        if nodepool.min_node_count == nodepool.target_min_node_count:
            logger.info(f'[{nodepool.name}] Cloud provider minimum node count target state of {nodepool.min_node_count} reached')
            state = NodepoolState.READY.name
            npat_status = Nodepool.get_status_list(nodepool_list, state)
            patch.status['nodepool_allocation'] = npat_status
        else:
            if retry < RETRY_LIMIT:
                logger.error(f'Attempt {retry}: reconcile_provider handler')
                await nodepool.set_min_node_count(nodepool.target_min_node_count)
                state = NodepoolState.UPDATING.name
                npat_status = Nodepool.get_status_list(nodepool_list, state)
                patch.status['nodepool_allocation'] = npat_status
                raise kopf.TemporaryError(f'[{nodepool.name}] Cloud provider minimum node count target state of {nodepool.min_node_count} not reached', delay=ERROR_DELAY)
            else:
                state = NodepoolState.ERROR.name
                npat_status = Nodepool.get_status_list(nodepool_list, state)
                patch.status['nodepool_allocation'] = npat_status
                raise kopf.PermanentError(f'[{nodepool.name}] Reconciliation of target_min_node_count ({nodepool.target_min_node_count}) == cloud provider minimum node count ({nodepool.min_node_count}) timed out after {RETRY_LIMIT} tries.')

@kopf.timer('nodepoolallocationtarget', interval=10, initial_delay=10, idle=10) # type: ignore[arg-type]
async def reconcile_kubernetes(spec: kopf.Spec, status: kopf.Status, name: str, k8s_nodes: kopf.Index, patch: kopf.Patch, logger: kopf.Logger, retry: int, **kwargs: Any) -> None:
    """
    Regularly reconcile target minimum node count is less than or equal to current Kubernetes node count.
    """
    if status.get('nodepool_allocation', {}).get('status', '') == NodepoolState.ERROR.name:
        raise kopf.PermanentError(f'Nodepool allocation target [{name}] in {NodepoolState.ERROR.name} status')
    label_selector = spec.get('nodepoolSelector', {})
    node_list = await Node.list_node(label_selector=label_selector, index=k8s_nodes)
    nodepool_list = await Nodepool.list_nodepool(node_list)
    for nodepool in nodepool_list:
        # Calculate nodepool target minimum node count from plugins
        nodepool = calculate_target_min_node_count_from_plugins(nodepool, spec, logger)
        if nodepool.target_min_node_count <= nodepool.current_node_count:
            logger.info(f'[{nodepool.name}] Target minimum node count ({nodepool.target_min_node_count}) <= Kubernetes nodes online ({nodepool.current_node_count}) reached')
            npat_status = Nodepool.get_status_list(nodepool_list, NodepoolState.READY.name)
            patch.status['nodepool_allocation'] = npat_status
        else:
            if retry < RETRY_LIMIT:
                npat_status = Nodepool.get_status_list(nodepool_list, NodepoolState.UPDATING.name)
                patch.status['nodepool_allocation'] = npat_status
                logger.info(f'Attempt {retry}: reconcile_kubernetes handler')
                raise kopf.TemporaryError(f'[{nodepool.name}] Target minimum node count ({nodepool.target_min_node_count}) <= Kubernetes nodes online ({nodepool.current_node_count}) not reached', delay=ERROR_DELAY)
            else:
                npat_status = Nodepool.get_status_list(nodepool_list, NodepoolState.ERROR.name)
                patch.status['nodepool_allocation'] = npat_status
                raise kopf.PermanentError(f'[{nodepool.name}] Reconciliation of target_min_node_count ({nodepool.target_min_node_count}) <= Kubernetes current node count ({nodepool.current_node_count}) timed out after {RETRY_LIMIT} tries.')
