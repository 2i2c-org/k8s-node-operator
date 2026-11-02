# k8s-autoscaler-plugins

Scale nodes for your Kubernetes cluster ahead of time with flexible plugins.

## Features

This is a custom python-based k8s `kopf` operator that provides a way for you to bring nodes online in advance of user demand. We create a framework composed of two parts:

- A mechanism by which minimum nodepool sizes are scaled up or down with support for multiple cloud providers
- A plug-in system that initiates node scaling based on different types of triggers, e.g. event-based triggers such as crossing a utilisation threshold, or time-based triggers such as a calendar integration.

## Prerequisites

A Kubernetes cluster (`k3s`, `minikube`, `Docker`, etc.).

> [!note]
> If you are using macOS, then instead of `minikube` you may need to run a kubernetes cluster with a docker daemon inside a virtual machine manager such as [colima](https://colima.run/), e.g. `colima start --kubernetes --network-address`.

## Installation

### Local development

For local development, install the package with

```bash
pip install -e '.[dev]'
```

Install the `NodepoolAllocationTarget` [custom resource definition](https://kubernetes.io/docs/tasks/extend-kubernetes/custom-resources/custom-resource-definitions/) (CRD) with

```bash
kubectl apply -f helm/k8s_node_operator/crds/nodepool_allocation_target.yaml
```

> [!note]
> CRDs fundamentally alter the Kubernetes API. If `nodepool_allocation_target.yaml` is updated, then remember to delete and re-register the CRD.
>
> See the [Helm docs](https://helm.sh/docs/chart_best_practices/custom_resource_definitions/) for working with CRDs in Helm.  # TODO: write more docs for how to install in a prod environment.

Run the `kopf` operator with

```bash
kopf run -A src/k8s_node_operator/operator.py
```

> [!note]
> If you see
>
> ```bash
> kopf._cogs.structs.credentials.LoginError: Ran out of valid credentials. Consider installing an API client library or adding a login handler. See more: https://docs.kopf.dev/en/stable/authentication/
> ```
>
> check that your k8s context is set to the correct cluster with
>
> ```bash
> kubectl config use-context <context-name>
> ```

## Usage

### Local development

The following example usage is based on scaling nodes in a GCP GKE cluster nodepool.

1. [Generate a service account](https://docs.cloud.google.com/iam/docs/service-accounts-create) for the `kopf` operator with the [Kubernetes Engine Cluster Admin](https://docs.cloud.google.com/iam/docs/roles-permissions/container#container.clusterAdmin) role permissions.

1. Add a service account key and save the key, e.g. `sa_key.secret.json` file securely.

1. Configure the operator by setting and sourcing environment variables with a `.env` file

   ```bash
   # .env
   export K8S_AUTOSCALER_PLUGINS_CLOUD_PROVIDER="GCP"
   export GOOGLE_APPLICATION_CREDENTIALS="sa_key.secret.json"
   ```

1. Update the Nodepool Allocation Target (`npat`) resource definition with the following `spec`

   ```bash
   spec:
       minimumNodeCount: 1
       project: <gcp-project-id>
       cluster: <gcp-cluster-name>
       zone: <gcp-zone>
       nodepool: <gcp-nodepool>
       nodepoolLabel: <kubernetes-nodepool-label>
   ```

   You can also set `spec` values, except the `minimumNodeCount`, as environment variables in your `.env` file.

> [!note]
> For example, the `kubernetes-nodepool-label` could be `kubernetes.io/hostname=colima` for a local development environment running k3s in a Colima VM.

1. Run the `kopf` operator

   ```bash
   kopf run -A src/k8s_node_operator/operator.py
   ```

1. In another terminal window, scale the GCP nodepool by creating an `npat` object with

   ```bash
   kubectl apply -f examples/npat.yaml
   ```

1. Display the `npat` resource with

   ```bash
   $ kubectl get npat
   NAME           NODEPOOL       STATE   NODE COUNT   TARGET MIN NODE COUNT   MIN NODE COUNT   MAX NODE COUNT   AGE
   example-npat   default-pool   UPDATING   1            1                       0                0                10s
   ```

1. Check that the nodepool minimum node count has updated, e.g. with Google Cloud Console > Kubernetes Engine > Clusters, or running

   ```bash
   gcloud container node-pools describe $GCP_NODEPOOL --cluster $GCP_CLUSTER \
    --location=$GCP_ZONE
   ```

1. Patch the `npat` resource to update the minimum node count value with `kubectl edit` or `kubectl patch`

1. Delete the `npat` resource to set the minimum nodepool size back down to 0 again.

   ```bash
   kubectl delete npat example-npat
   ```

> [!note]
> Sometimes the [deletion gets 'stuck'](https://docs.kopf.dev/en/stable/troubleshooting/#kubectl-freezes-on-object-deletion) when the object's finaliser cannot run to completion, e.g. the `npat` object is deleted when the `kopf` operator is down. You can re-run the `kopf` operator to clean up, or force the deletion with
>
> ```bash
> kubectl patch npat example-npat -p '{"metadata": {"finalizers": []}}' --type merge
> ```

## Documentation

TBD

## Contributing

See the guidance in [CONTRIBUTING](CONTRIBUTING.md)

## License

This project is licensed under the [BSD 3-Clause License](LICENSE.md).
