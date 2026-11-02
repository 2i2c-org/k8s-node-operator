import kopf
from k8s_autoscaler_plugins.base import Nodepool
from k8s_autoscaler_plugins.hooks import hookimpl

@hookimpl
def evaluate_nodepool(nodepool: Nodepool, spec: kopf.Spec, logger: kopf.Logger) -> Nodepool:
    target_min_node_count = spec.get('plugins', {}).get('always_on', {}).get('minimum', 0)
    if nodepool.target_min_node_count <= target_min_node_count:
        nodepool.target_min_node_count = target_min_node_count
    logger.debug(f'[plugin] {__package__} succeeded')
    return nodepool
