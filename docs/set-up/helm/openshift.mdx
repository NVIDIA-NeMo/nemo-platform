<a id="nemo-ms-install-openshift"></a>
# OpenShift

The {{platform_name}} chart works on Red Hat OpenShift when security context overrides are applied. OpenShift’s **restricted** or **restricted-v2** Security Context Constraint (SCC) requires pods to run as non-root with explicit `runAsUser` and `runAsNonRoot`.

## Values

You can override the default values for the {{platform_name}} chart to make it compatible with OpenShift.

1. **Create the OpenShift values file.** Save the following as `openshift-values.yaml`:

 ```yaml
 # openshift-values.yaml

 podSecurityContext:
 runAsNonRoot: true
 fsGroup: 1000
 seccompProfile:
 type: RuntimeDefault

 securityContext:
 allowPrivilegeEscalation: false
 capabilities:
 drop:
 - ALL

 # If using the embedded PostgreSQL, otherwise skip this section
 postgresql:
 securityContext:
 runAsUser: 999
 runAsNonRoot: true
 podSecurityContext:
 runAsNonRoot: true
 fsGroup: 999
 ```

2. **Install** with your custom values and the OpenShift overrides (order matters; later files override earlier). Complete the [Prerequisites](./prerequisites.md) and follow [Install](./install.md), using the provided OpenShift values file.

 ```sh
 helm upgrade --install --namespace <namespace-to-install-nemo-microservices> \
 nemo-platform nmp/nemo-platform \
 -f values.yaml \
 -f openshift-values.yaml
 ```

## Ingress

You can expose the API using the following methods:

- **Kubernetes Ingress** — supported by OpenShift’s default IngressController; set `ingress.enabled: true` and `ingress.defaultHost` as in [Ingress](./ingress.md).
- **Gateway API HTTPRoute** — optional; configure `httpRoute` in values. See [Gateway API HTTPRoute](./ingress.md#gateway-api-httproute).
- **OpenShift Route** — enable the chart’s Route and set an optional hostname. See [OpenShift Route](./ingress.md#openshift-route) for steps.

## Troubleshooting

### Security Context Constraints

If you see "unable to validate against any security context constraint" or "container has runAsNonRoot and image will run as root", ensure you pass the necessary pod security context overrides. See [Values](#values) for steps.
If you want to validate your values are being applied correctly, you can use the `helm template` command to see the rendered templates.

```sh
helm template nemo-platform nmp/nemo-platform -f values.yaml -f openshift-values.yaml
```
