import kopf
from k8s_autoscaler_plugins.base import Nodepool
from k8s_autoscaler_plugins.hooks import hookimpl

@hookimpl
def evaluate_nodepool(nodepool: Nodepool, spec: kopf.Spec, logger: kopf.Logger) -> Nodepool:
    # TODO: incomplete
    target_min_node_count = spec.get('plugins', {}).get('cron', {}).get('minimum', 0)
    schedule_list =  spec.get('plugins', {}).get('cron', {}).get('schedule', [])
    for schedule in schedule_list:
        logger.debug(f'{schedule=}')
    if nodepool.target_min_node_count <= target_min_node_count:
        nodepool.target_min_node_count = target_min_node_count
    logger.debug(f'[plugin] {__package__} succeeded')
    return nodepool
