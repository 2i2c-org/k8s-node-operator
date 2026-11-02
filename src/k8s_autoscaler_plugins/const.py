import os

ERROR_DELAY = int(os.environ.get('K8S_AUTOSCALER_PLUGINS_ERROR_DELAY', 20))
RETRY_LIMIT = int(os.environ.get('K8S_AUTOSCALER_PLUGINS_RETRY_LIMIT', 5))
PROVIDER_NAME = os.environ.get('K8S_AUTOSCALER_PLUGINS_CLOUD_PROVIDER', '')
NODEPOOL_LABELS = {
    'GCP': 'cloud.google.com/gke-nodepool',
    'TEST': 'cloud.google.com/gke-nodepool'
}