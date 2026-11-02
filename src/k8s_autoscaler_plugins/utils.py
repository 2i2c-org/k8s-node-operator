import kopf
import pluggy
from k8s_autoscaler_plugins.base import Nodepool
import k8s_autoscaler_plugins.hooks as hookspec

def get_plugin_manager():
    """
    Get the plugin manager instance.
    """
    # Set up plugin infrastructure
    pm = pluggy.PluginManager("k8s-autoscaler-plugins")
    pm.add_hookspecs(hookspec)
    # Automatically register installed plugins with plugin entrypoint
    pm.load_setuptools_entrypoints('k8s-autoscaler-plugins')
    return pm

def calculate_target_min_node_count_from_plugins(nodepool: Nodepool, spec: kopf.Spec, logger: kopf.Logger):
    """
    Calculate nodepool target minimum node count by calling plugin hook implementation functions in reverse priority order, i.e. highest priority functions override the final results and are called last.
    """
    pm = get_plugin_manager()
    plugins = pm.get_plugins()
    if not plugins:
        raise kopf.PermanentError('No k8s autoscaler plugins registered.')
    else:
        logger.info(f'Registered plugin packages: {[p.__package__ for p in plugins]}')
    names = [pm.get_name(plugin) for plugin in plugins]
    specs = [{name: spec.get('plugins', {}).get(name, {})} for name in names] # NOTE: npat spec plugin name must match registered plugin name
    priorities = {}
    for s in specs:
        for k, v in s.items():
            priorities.update({k: v.get('priority', None)})
    caller = pm.hook.evaluate_nodepool # TODO: make hook function name flexible
    implementations = sorted(
        caller.get_hookimpls(),
        key = lambda impl: priorities[impl.plugin_name],  # TODO: validate spec to ensure unique ordering
        reverse=True  
    )
    results = []
    for impl in implementations:
        result = impl.function(nodepool=nodepool, spec=spec, logger = logger) # TODO: assumes every plugin handler has the same call signature
        results.append(result)
        logger.info(f'[plugin] [{impl.plugin_name}] {result.target_min_node_count=}')
    return results.pop()
