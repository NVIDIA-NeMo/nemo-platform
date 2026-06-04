<a id="install"></a>
# Install {{helm_chart_short_name}}

!!! tip "Note: This setup is the full enterprise platform, meant for advanced use. If you're just getting started, check out [setting up a local instance of the platform](../../get-started/setup.md) instead — it's faster and easier to explore the basics."

To deploy the {{platform_name}}, follow these steps after completing the [Prerequisites](./prerequisites.md).

1. Add the {{helm_chart_short_name}} to your local Helm repositories.

 ```sh
 helm repo add nmp https://helm.ngc.nvidia.com/nvidia/nemo-microservices \
 --username='$oauthtoken' \
 --password=$NGC_API_KEY
 ```
 ```sh
 helm repo update
 ```

2. Review the default values in the [{{helm_chart_short_name}} reference](../../helm/index.md). To override the default values, create a custom values file. Review the following while creating your custom values file.

 - To configure an external database, see [Database Setup](./database-setup.md).
 - To configure persistent volumes for jobs and files storage, see [Persistent Volumes](./persistent-volumes.md).
 - To configure file storage options, see [File Storage](./file-storage.md).
 - To configure ingress, see [Ingress](./ingress.md).
 - To configure multi-node networking, see [Multi-Node Networking](./multinode-networking.md).
 - To configure OpenShift-compatible security context overrides, see [OpenShift](./openshift.md).

3. Install the Volcano scheduler before installing the chart. This is required for customization jobs that leverage multiple nodes.

 ```sh
{% raw %}
 kubectl apply -f https://raw.githubusercontent.com/volcano-sh/volcano/v{{volcano_version}}/installer/volcano-development.yaml
{% endraw %}
 ```

 After applying, wait for the Volcano admission webhook to finish initializing before proceeding. The webhook registers immediately with `failurePolicy: Fail`, but TLS certificate generation runs asynchronously. If you proceed before the webhook is ready, all pod creation — including the {{platform_name}} Helm install — will fail with a certificate error.

 ```sh
 kubectl wait --for=condition=complete job/volcano-admission-init -n volcano-system --timeout=120s
 kubectl rollout status deployment/volcano-admission -n volcano-system
 ```

 
4. Install the chart using your `values.yaml` file:

 ```sh
 helm install nemo-platform nmp/nemo-platform -f values.yaml
 ```

 The installation process takes approximately 10 minutes for image downloads, container startup, and communication establishment. The time it takes might vary depending on the speed of your network connection.
 Pods might appear in pending or restarting states during the installation process.

5. Verify the pod status:

 ```sh
 kubectl get pods
 ```

For Red Hat OpenShift, use OpenShift-compatible security context overrides so pods satisfy the restricted SCC. See [OpenShift](./openshift.md).

<a id="upgrade-helm-chart"></a>
To upgrade the deployment with new configurations, use the following command:

```sh
helm upgrade nemo-platform nmp/nemo-platform -f values.yaml
```

<a id="uninstall-platform"></a>
To uninstall the deployment, use the following command:

```sh
helm uninstall nemo-platform
```

!!! note "`helm uninstall` intentionally does **not** remove all resources:"
    - **PVCs** are preserved to prevent accidental data loss. Delete them manually if no longer needed.
    - **CRDs** are not removed by Helm design ([upstream issue](https://github.com/helm/helm/issues/4840)) to avoid destroying custom resources across the cluster.
    - **Completed jobs, secrets, and the namespace** may also remain.
If you need a complete teardown (e.g., for CI/CD pipelines or reinstalling in the same namespace), run the following after `helm uninstall`:

```sh
# Delete the namespace — removes all namespace-scoped resources (pods, PVCs, jobs, secrets, etc.)
kubectl delete namespace <namespace>

# Then delete custom resources as needed, though generally this is not required
kubectl delete crd <crd_name>
```

!!! warning "Deleting CRDs removes all custom resources of those types cluster-wide. Only do this if no other workloads depend on them."

## Troubleshooting

### Volcano admission webhook blocks pod creation

**Symptom:** Pod creation fails cluster-wide with an error like:

```
Internal error occurred: failed calling webhook "mutatepod.volcano.sh":
failed to call webhook: Post "https://volcano-admission-service.volcano-system.svc:443/pods/mutate?timeout=10s":
tls: failed to verify certificate: x509: certificate signed by unknown authority
```

**Cause:** The Volcano `MutatingWebhookConfiguration` registers with `failurePolicy: Fail` before the `volcano-admission-init` job finishes generating TLS certificates. This affects all namespaces, not just Volcano workloads.

**Fix:** Wait for the webhook to become functional, then restart the admission deployment to force certificate regeneration:

```sh
kubectl rollout restart deployment/volcano-admission -n volcano-system
kubectl rollout status deployment/volcano-admission -n volcano-system
```

Verify the webhook is accepting requests before retrying your Helm install:

```sh
until kubectl run volcano-webhook-test --image=busybox --restart=Never --dry-run=server -o yaml 2>/dev/null; do
 echo "Volcano webhook not ready yet, waiting..."
 sleep 5
done
kubectl delete pod volcano-webhook-test --ignore-not-found=true
```
