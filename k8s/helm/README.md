# NeMo Platform Helm Chart

![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square)

Documentation can be found at: https://docs.nvidia.com/nemo-platform.

## Platform Secrets Encryption Key

The platform secrets service reads `NMP_SECRETS_DEFAULT_ENCRYPTION_KEY` from the
API env Secret. The value must be base64-encoded and decode to at least 32 bytes.

Set `secrets.defaultEncryptionKey.value` to provide your own key. When that value
is empty and `envFromSecret` is not set, the chart runs a pre-install hook that
creates `<fullname>-api-env` with a per-install random key. The hook is
install-only and refuses to patch or rotate an existing Secret.

Set `envFromSecret` to use a fully user-managed API env Secret. In that mode the
chart does not create or generate the API env Secret.

On upgrade, the generated Secret must already exist and contain
`NMP_SECRETS_DEFAULT_ENCRYPTION_KEY`. If it is missing, restore the original
Secret instead of generating a replacement key; existing encrypted platform
secrets will not decrypt with a new key.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| additionalImagePullSecrets | object | `{}` | List of additional image pull secrets to use for pulling container images. Can be used when multiple image pull secrets are required in your environment. |
| api | object | This object has the following default values for the API configuration. | API configuration settings for the api deployment |
| api.affinity | object | `{}` | Affinity configuration for the API service. |
| api.annotations | object | `{}` | Annotations to add to the API service deployment. |
| api.autoscaling | object | `{"annotations":{},"enabled":false,"maxReplicas":10,"minReplicas":1,"targetCPUUtilizationPercentage":80}` | Specifies autoscaling configurations for the deployment. |
| api.autoscaling.annotations | object | `{}` | Annotations for the HorizontalPodAutoscaler. |
| api.autoscaling.enabled | bool | `false` | Whether to enable horizontal pod autoscaler. |
| api.autoscaling.maxReplicas | int | `10` | The maximum number of replicas for the deployment. |
| api.autoscaling.minReplicas | int | `1` | The minimum number of replicas for the deployment. |
| api.autoscaling.targetCPUUtilizationPercentage | int | `80` | The target CPU utilization percentage. |
| api.enabled | bool | `true` | Specifies whether to enable the api deployment. |
| api.extraArgs | list | `[]` | Additional arguments to pass to the Platform API service |
| api.image | object | This object has the following default values for the image configuration. | Container image configuration for the api deployment. |
| api.image.pullPolicy | string | `"IfNotPresent"` | The image pull policy determining when to pull new images. |
| api.image.repository | string | `"nvcr.io/nvidia/nemo-platform/nmp-api"` | The registry where the NeMo Platform image is located. |
| api.image.tag | string | `""` | The image tag to use. |
| api.livenessProbe | object | This object has the following default values for the liveness probe configuration. | Liveness probe configuration for the api service. |
| api.livenessProbe.failureThreshold | int | `3` | The failure threshold for the liveness probe. |
| api.livenessProbe.httpGet | object | `{"path":"/health/live","port":"http"}` | The HTTP GET request to use for the liveness probe. |
| api.livenessProbe.periodSeconds | int | `10` | The frequency in seconds to perform the liveness probe. |
| api.livenessProbe.timeoutSeconds | int | `5` | The timeout in seconds for the liveness probe. |
| api.nodeSelector | object | `{}` | Node selector configuration for the API service. |
| api.podAnnotations | object | `{}` | Annotations to add to the API service pod. |
| api.podDisruptionBudget | object | This object has the following default values for the pod disruption budget configuration. | PodDisruptionBudget configuration for the API service. |
| api.podDisruptionBudget.annotations | object | `{}` | Annotations for the PodDisruptionBudget. |
| api.podDisruptionBudget.enabled | bool | `false` | Whether to create a PodDisruptionBudget for the API pods. |
| api.podDisruptionBudget.minAvailable | int | `1` | Minimum number of API pods that must remain available during voluntary disruptions. Only one of minAvailable or maxUnavailable may be set. |
| api.podLabels | object | `{}` | Labels for the API service pod. |
| api.podSecurityContext | object | This object has the following default values for the pod security context. | Pod-level security context settings for the API service. |
| api.podSecurityContext.fsGroup | int | `1000` | The file system group ID to use for all containers. |
| api.readinessProbe | object | This object has the following default values for the readiness probe configuration. | Readiness probe configuration for the api service. |
| api.readinessProbe.failureThreshold | int | `3` | The failure threshold for the readiness probe. |
| api.readinessProbe.httpGet | object | `{"path":"/health/ready","port":"http"}` | The HTTP GET request to use for the readiness probe. |
| api.readinessProbe.periodSeconds | int | `10` | The frequency in seconds to perform the readiness probe. |
| api.readinessProbe.timeoutSeconds | int | `5` | The timeout in seconds for the readiness probe. |
| api.replicaCount | int | `1` | Number of replicas for the API service. |
| api.resources | object | `{}` | Kubernetes deployment resources configuration for the API service. |
| api.securityContext | object | `{}` | Container-level security context settings for the API service. |
| api.service | object | This object has the following default values for the service configuration. | Service configuration for the API service. |
| api.service.annotations | object | `{}` | Annotations for the API service. |
| api.service.port | int | `8080` | The port number to expose for the service. |
| api.service.type | string | `"ClusterIP"` | The Kubernetes service type to create. |
| api.serviceAccount | object | This object has the following default values for the service account configuration. | Service account configuration for the API service. |
| api.serviceAccount.annotations | object | `{}` | Annotations to add to the service account. |
| api.serviceAccount.automount | bool | `true` | Automatically mount a ServiceAccount's API credentials. |
| api.serviceAccount.create | bool | `true` | Specifies whether a service account should be created. |
| api.serviceAccount.name | string | `""` | The name of the service account to use. If not set and create is true, a name is generated using the fullname template. |
| api.serviceMonitor.annotations | object | `{}` | Additional annotations to add to the ServiceMonitor |
| api.serviceMonitor.enabled | bool | `false` | Enable ServiceMonitor resources for Prometheus Operator |
| api.serviceMonitor.interval | string | `"30s"` | Scrape interval for the ServiceMonitor |
| api.serviceMonitor.labels | object | `{}` | Additional labels to add to the ServiceMonitor |
| api.serviceMonitor.scheme | string | `"http"` | Scheme to use for scraping metrics (http or https) |
| api.startupProbe | object | This object has the following default values for the startup probe configuration. | Startup probe configuration for the api service. |
| api.startupProbe.failureThreshold | int | `24` | The failure threshold for the startup probe. |
| api.startupProbe.httpGet | object | `{"path":"/health/ready","port":"http"}` | The HTTP GET request to use for the startup probe. |
| api.startupProbe.initialDelaySeconds | int | `10` | Number of seconds to wait before the first startup probe. Allows time for DB connection retries (e.g. Postgres pod booting). |
| api.startupProbe.periodSeconds | int | `15` | The frequency in seconds to perform the startup probe. |
| api.startupProbe.timeoutSeconds | int | `5` | The timeout in seconds for the startup probe. |
| api.telemetry | object | `{}` | OpenTelemetry configuration overrides for the api deployment. |
| api.tolerations | list | `[]` | Tolerations configuration for the API service. |
| api.topologySpreadConstraints | list | `[]` | Topology spread constraints for the API service pods. See https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/ |
| basePlatformConfig | string | This object has the following default values for the base platform configuration. | Base platform configuration settings |
| core | object | This object has the following default values for the core deployment configuration. | Core deployment configuration settings |
| core.controller.affinity | object | `{}` | Affinity configuration for the controller service. |
| core.controller.annotations | object | `{}` | Annotations to add to the controller service deployment. |
| core.controller.env | object | `{}` | Additional environment variables to pass to containers. This is an object formatted like NAME: value or NAME: valueFrom: {object}. |
| core.controller.extraArgs | list | `[]` | Additional arguments to pass to the Core Controller service |
| core.controller.livenessProbe | object | This object has the following default values for the liveness probe configuration. | Liveness probe configuration for the controller service. |
| core.controller.livenessProbe.failureThreshold | int | `3` | The failure threshold for the readiness probe. |
| core.controller.livenessProbe.httpGet | object | `{"path":"/health/live","port":"http"}` | The HTTP GET request to use for the readiness probe. |
| core.controller.livenessProbe.periodSeconds | int | `10` | The frequency in seconds to perform the readiness probe. |
| core.controller.livenessProbe.timeoutSeconds | int | `5` | The timeout in seconds for the readiness probe. |
| core.controller.nodeSelector | object | `{}` | Node selector configuration for the controller service. |
| core.controller.podAnnotations | object | `{}` | Annotations to add to the controller service pod. |
| core.controller.podLabels | object | `{}` | Labels for the controller service pod. |
| core.controller.podSecurityContext | object | This object has the following default values for the pod security context. | Pod-level security context settings for the controller service. |
| core.controller.podSecurityContext.fsGroup | int | `1000` | The file system group ID to use for all containers. |
| core.controller.readinessProbe | object | This object has the following default values for the readiness probe configuration. | Readiness probe configuration for the controller service. |
| core.controller.readinessProbe.failureThreshold | int | `3` | The failure threshold for the readiness probe. |
| core.controller.readinessProbe.httpGet | object | `{"path":"/health/ready","port":"http"}` | The HTTP GET request to use for the readiness probe. |
| core.controller.readinessProbe.periodSeconds | int | `10` | The frequency in seconds to perform the readiness probe. |
| core.controller.readinessProbe.timeoutSeconds | int | `5` | The timeout in seconds for the readiness probe. |
| core.controller.resources | object | `{}` | Kubernetes deployment resources configuration for the controller service. |
| core.controller.securityContext | object | `{}` | Container-level security context settings for the controller service. |
| core.controller.service | object | This object has the following default values for the service configuration. | Service configuration for the controller service. This only configures a headless service for DNS resolution. |
| core.controller.service.annotations | object | `{}` | Annotations for the headless controller service. |
| core.controller.service.port | int | `8080` | The port for the service. |
| core.controller.serviceAccount | object | This object has the following default values for the service account configuration. | Service account configuration for the controller service. |
| core.controller.serviceAccount.annotations | object | `{}` | Annotations to add to the service account. |
| core.controller.serviceAccount.automount | bool | `true` | Automatically mount a ServiceAccount's API credentials. |
| core.controller.serviceAccount.create | bool | `true` | Specifies whether a service account should be created. |
| core.controller.serviceAccount.name | string | `""` | The name of the service account to use. If not set and create is true, a name is generated using the fullname template. |
| core.controller.startupProbe | object | This object has the following default values for the startup probe configuration. | Startup probe configuration for the core service. |
| core.controller.startupProbe.failureThreshold | int | `24` | The failure threshold for the startup probe. |
| core.controller.startupProbe.httpGet | object | `{"path":"/health/ready","port":"http"}` | The HTTP GET request to use for the startup probe. |
| core.controller.startupProbe.initialDelaySeconds | int | `10` | Number of seconds to wait before the first startup probe. Allows time for DB connection retries (e.g. Postgres pod booting). |
| core.controller.startupProbe.periodSeconds | int | `15` | The frequency in seconds to perform the startup probe. |
| core.controller.startupProbe.timeoutSeconds | int | `5` | The timeout in seconds for the startup probe. |
| core.controller.tolerations | list | `[]` | Tolerations configuration for the controller service. |
| core.controller.topologySpreadConstraints | list | `[]` | Topology spread constraints for the controller service pods. See https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/ |
| core.enabled | bool | `true` | Specifies whether to enable the core deployment. |
| core.image | object | This object has the following default values for the image configuration. | Container image configuration for the core deployment. |
| core.image.pullPolicy | string | `"IfNotPresent"` | The image pull policy determining when to pull new images. |
| core.image.repository | string | `"nvcr.io/nvidia/nemo-platform/nmp-api"` | The registry where the NeMo Platform image is located. |
| core.image.tag | string | `""` | The image tag to use. |
| core.jobs | object | This object has the following default values for the jobs service account configuration. | Service account configuration for pods created by the jobs controller (Kubernetes/Volcano job pods). |
| core.jobs.serviceAccount.annotations | object | `{}` | Annotations to add to the service account. |
| core.jobs.serviceAccount.automount | bool | `true` | Automatically mount a ServiceAccount's API credentials. |
| core.jobs.serviceAccount.create | bool | `true` | Specifies whether a service account should be created for job pods. |
| core.jobs.serviceAccount.name | string | `""` | The name of the service account to use. If not set and create is true, a name is generated with a '-jobs' suffix. |
| core.serviceMonitor.annotations | object | `{}` | Additional annotations to add to the ServiceMonitor |
| core.serviceMonitor.enabled | bool | `false` | Enable ServiceMonitor resources for Prometheus Operator |
| core.serviceMonitor.interval | string | `"30s"` | Scrape interval for the ServiceMonitor |
| core.serviceMonitor.labels | object | `{}` | Additional labels to add to the ServiceMonitor |
| core.serviceMonitor.scheme | string | `"http"` | Scheme to use for scraping metrics (http or https) |
| core.storage.accessModes | list | `["ReadWriteMany"]` | accessModes for the persistent volume claim. This should include `ReadWriteMany` to ensure multiple job pods can write to the volume concurrently. |
| core.storage.annotations | object | `{}` | Annotations to add to the persistent volume claim |
| core.storage.existingPersistentVolumeName | string | `""` | If set, pods will mount this persistent volume for job-scoped storage and we will not create a new persistent volume claim. |
| core.storage.size | string | `"200Gi"` | size of the persistent volume claim used for persistent storage |
| core.storage.storageClass | string | `""` | Which storageClass to use when creating a new persistent volume claim. Empty string uses the cluster's default StorageClass. |
| core.storage.volumePermissionsImage | string | `"busybox"` | volumePermissionsImage is the image used to set permissions on the volume |
| core.telemetry | object | `{}` | OpenTelemetry configuration overrides for the platform deployment. |
| env | object | `{}` | Environment variables that will be applied to every deployment pod. Uses a simple key value map structure like MY_ENV_VAR: the-key and works with valueFrom as well. |
| envFromSecret | string | `""` | Optional. Name of an existing Kubernetes Secret to load as env vars (envFrom) for the API pod. When set, the chart does not create or generate the default api-env Secret; use your own Secret (for example, from Vault or sealed-secrets). |
| envoyProxy | object | This object has the following default values for the envoy proxy configuration. | Envoy proxy configuration settings. Resources are created only when platform config has auth.enabled: true (see platformConfig.auth.enabled). |
| envoyProxy.adminPort | int | `9901` | Envoy Admin port |
| envoyProxy.affinity | object | `{}` | Affinity configuration for the Envoy pods. |
| envoyProxy.annotations | object | `{}` | Annotations to add to the Envoy service deployment. |
| envoyProxy.autoscaling | object | `{"annotations":{},"enabled":false,"maxReplicas":10,"minReplicas":1,"targetCPUUtilizationPercentage":80}` | Specifies autoscaling configurations for the deployment. |
| envoyProxy.autoscaling.annotations | object | `{}` | Annotations for the HorizontalPodAutoscaler. |
| envoyProxy.autoscaling.enabled | bool | `false` | Whether to enable horizontal pod autoscaler. |
| envoyProxy.autoscaling.maxReplicas | int | `10` | The maximum number of replicas for the deployment. |
| envoyProxy.autoscaling.minReplicas | int | `1` | The minimum number of replicas for the deployment. |
| envoyProxy.autoscaling.targetCPUUtilizationPercentage | int | `80` | The target CPU utilization percentage. |
| envoyProxy.enabled | bool | `true` | Specifies whether to enable the Envoy proxy deployment. Rendered only when platform config has auth.enabled: true. |
| envoyProxy.extraArgs | list | `[]` | Extra arguments to append to the envoy container command. Useful for passing server flags such as concurrency. Example: ["--concurrency", "4"] |
| envoyProxy.livenessProbe | object | `{"failureThreshold":3,"httpGet":{"path":"/ready","port":"admin"},"periodSeconds":10,"timeoutSeconds":5}` | Liveness probe for the Envoy container (admin interface /ready). |
| envoyProxy.nodeSelector | object | `{}` | Node selector configuration for the Envoy pods. |
| envoyProxy.podAnnotations | object | `{}` | Annotations to add to the Envoy service pod. |
| envoyProxy.podDisruptionBudget | object | This object has the following default values for the pod disruption budget configuration. | PodDisruptionBudget configuration for the Envoy service. |
| envoyProxy.podDisruptionBudget.annotations | object | `{}` | Annotations for the PodDisruptionBudget. |
| envoyProxy.podDisruptionBudget.enabled | bool | `false` | Whether to create a PodDisruptionBudget for the Envoy pods. |
| envoyProxy.podDisruptionBudget.minAvailable | int | `1` | Minimum number of Envoy pods that must remain available during voluntary disruptions. Only one of minAvailable or maxUnavailable may be set. |
| envoyProxy.podLabels | object | `{}` | Labels for the Envoy service pod. |
| envoyProxy.podSecurityContext | object | This object has the following default values for the pod security context. | Pod-level security context settings for the Envoy service. |
| envoyProxy.podSecurityContext.fsGroup | int | `1000` | The file system group ID to use for all containers. |
| envoyProxy.readinessProbe | object | `{"failureThreshold":3,"httpGet":{"path":"/ready","port":"admin"},"periodSeconds":10,"timeoutSeconds":5}` | Readiness probe for the Envoy container (admin interface /ready). |
| envoyProxy.resources | object | `{}` | Kubernetes deployment resources configuration for the Envoy service. |
| envoyProxy.securityContext | object | `{}` | Container-level security context settings for the Envoy service. |
| envoyProxy.service | object | This object has the following default values for the service configuration. | Service configuration for the Envoy service. |
| envoyProxy.service.annotations | object | `{}` | Annotations for the Envoy service. |
| envoyProxy.service.exposeAdminPort | bool | `false` | Expose the Envoy admin port through the Kubernetes Service. Enable only for controlled in-cluster scraping or debugging. |
| envoyProxy.service.port | int | `8080` | The port number to expose for the service. |
| envoyProxy.service.type | string | `"ClusterIP"` | The Kubernetes service type to create. |
| envoyProxy.serviceAccount | object | This object has the following default values for the service account configuration. | Service account configuration for the Envoy service. |
| envoyProxy.serviceAccount.annotations | object | `{}` | Annotations to add to the service account. |
| envoyProxy.serviceAccount.automount | bool | `true` | Automatically mount a ServiceAccount's API credentials. |
| envoyProxy.serviceAccount.create | bool | `true` | Specifies whether a service account should be created. |
| envoyProxy.serviceAccount.name | string | `""` | The name of the service account to use. If not set and create is true, a name is generated using the fullname template. |
| envoyProxy.serviceMonitor.annotations | object | `{}` | Additional annotations to add to the ServiceMonitor |
| envoyProxy.serviceMonitor.enabled | bool | `false` | Enable ServiceMonitor resources for Prometheus Operator |
| envoyProxy.serviceMonitor.interval | string | `"30s"` | Scrape interval for the ServiceMonitor |
| envoyProxy.serviceMonitor.labels | object | `{}` | Additional labels to add to the ServiceMonitor |
| envoyProxy.serviceMonitor.scheme | string | `"http"` | Scheme to use for scraping metrics (http or https) |
| envoyProxy.startupProbe | object | `{"failureThreshold":12,"httpGet":{"path":"/ready","port":"admin"},"periodSeconds":5,"timeoutSeconds":3}` | Startup probe for the Envoy container (admin interface /ready). |
| envoyProxy.timeouts | object | Tuned for streaming; increase or set to "0s" if requests are cut off. | Timeouts for proxying to long-lived streams (e.g. inference gateway). Use "0s" to disable a timeout. |
| envoyProxy.timeouts.connect | string | `"30s"` | Cluster connect timeout (time to establish connection to backend). |
| envoyProxy.timeouts.request | string | `"0s"` | Total request timeout. 0 = disabled (required for streaming; not compatible with streaming if set). |
| envoyProxy.timeouts.requestHeaders | string | `"60s"` | Time to receive full request headers. 0 = disabled. |
| envoyProxy.timeouts.route | string | `"0s"` | Per-route timeout for the passthrough to backend. 0 = disabled. |
| envoyProxy.timeouts.streamIdle | string | `"0s"` | Stream idle timeout. Time with no activity before stream is closed. 0 = disabled (required for long-lived streams). |
| envoyProxy.tolerations | list | `[]` | Tolerations configuration for the Envoy pods. |
| envoyProxy.topologySpreadConstraints | list | `[]` | Topology spread constraints for the Envoy pods. See https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/ |
| existingImagePullSecret | string | `"nvcrimagepullsecret"` | You can specify an existing Kubernetes image pull secret for pulling images from the NGC container registry. The chart uses the `ngcAPIKey` value to generate the secret if you set this to an empty string. |
| existingSecret | string | `"ngc-api"` | You can use an existing Kubernetes secret for communicating with the NGC API for downloading models. The chart uses the `ngcAPIKey` value to generate the secret if you set this to an empty string. |
| externalDatabase | object | This object has the following default values for the external PostgreSQL configuration. | External PostgreSQL configuration settings. These values are only used when postgresql.enabled is set to false. |
| externalDatabase.database | string | `"nemoplatform"` | Database name. |
| externalDatabase.existingSecret | string | `""` | Name of an existing secret resource containing the database credentials. |
| externalDatabase.existingSecretPasswordKey | string | `""` | Name of an existing secret key containing the database credentials. |
| externalDatabase.host | string | `"localhost"` | External database host address. |
| externalDatabase.port | int | `5432` | External database port number. |
| externalDatabase.uriSecret | object | This object has the following default values for the URI secret configuration. | URI secret configuration for external database. |
| externalDatabase.uriSecret.key | string | `""` | Key in the URI secret containing the database URI. |
| externalDatabase.uriSecret.name | string | `""` | Name of the URI secret. |
| externalDatabase.user | string | `"nemo"` | Database username |
| fullnameOverride | string | `""` |  |
| httpRoute.annotations | object | `{}` | Extra annotations for the HTTP Route object. |
| httpRoute.enabled | bool | `false` | Specifies whether to enable a Gateway API HTTP Route for the service. |
| httpRoute.filters | list | `[]` | This is a list of filters for the objects, such as CORS settings. |
| httpRoute.hostnames | list | `[]` | If this has a specific hostname, add the name or names here in an array. |
| httpRoute.labels | object | `{}` | Extra labels for the HTTP Route object. |
| httpRoute.parentRefs | list | `[]` | A list of Gateways to enable this route on. This is required if httpRoute.enabled is true. |
| httpRoute.pathRules | list | `[{"backends":[{"port":"{{ include \"nemo-platform.ingressBackendPort\" . }}","service":"{{ include \"nemo-platform.ingressBackendService\" . }}"}],"matches":[{"path":"/","type":"Exact"},{"path":"/apis","type":"PathPrefix"},{"path":"/studio","type":"PathPrefix"},{"path":"/cluster-info","type":"Exact"},{"path":"/status","type":"Exact"}]}]` | Path matches to route queries. |
| ingress.annotations | object | `{}` | Annotations for the ingress resource. |
| ingress.className | string | `""` | The ingress class to use if your cluster has more than one class. |
| ingress.defaultHost | string | `""` | Optional default hostname. When set, one rule is generated with this host and paths from the first entry in ingress.hosts. |
| ingress.enabled | bool | `false` | Specifies whether to enable the ingress. |
| ingress.hosts[0] | object | `{"name":"","paths":[{"path":"/","pathType":"Exact","port":"{{ include \"nemo-platform.ingressBackendPort\" . }}","service":"{{ include \"nemo-platform.ingressBackendService\" . }}"},{"path":"/apis","pathType":"Prefix","port":"{{ include \"nemo-platform.ingressBackendPort\" . }}","service":"{{ include \"nemo-platform.ingressBackendService\" . }}"},{"path":"/studio","pathType":"Prefix","port":"{{ include \"nemo-platform.ingressBackendPort\" . }}","service":"{{ include \"nemo-platform.ingressBackendService\" . }}"},{"path":"/cluster-info","pathType":"Exact","port":"{{ include \"nemo-platform.ingressBackendPort\" . }}","service":"{{ include \"nemo-platform.ingressBackendService\" . }}"},{"path":"/status","pathType":"Exact","port":"{{ include \"nemo-platform.ingressBackendPort\" . }}","service":"{{ include \"nemo-platform.ingressBackendService\" . }}"}]}` | Hostname used by ingress. If blank, use path-only routing. |
| ingress.tls | list | `[]` | TLS configurations. |
| k8s-nim-operator.enabled | bool | `true` | Specifies whether to enable the default NIM Operator installation. To learn more, see [Install NIM Operator](https://docs.nvidia.com/nim-operator/latest/install.html). If you are using an existing NIM Operator installation, set this to false. |
| k8s-nim-operator.nfd.nodeFeatureRules.deviceID | bool | `false` | Specifies whether to enable device ID feature rules. |
| multinodeNetworking | object | `{"aws":{"efaDevicesPerGPU":1,"enabled":false},"azure":{"enabled":false,"rdmaDeviceName":"hca_shared_devices_a","rdmaDevicesPerGPU":1},"gcp":{"enabled":false},"oci":{"enabled":false,"rdmaDevicesPerGPU":8}}` | Multi-node networking configuration for distributed GPU training. These settings control Kyverno policies that inject cloud-specific networking and NCCL configurations.  Requirements: - Kyverno policy engine must be installed in your cluster (required for multi-node networking) - Kyverno is NOT included as a subchart dependency and must be installed separately  To install Kyverno:   helm install kyverno kyverno/kyverno --namespace kyverno --create-namespace --version 3.2.0  Documentation: https://kyverno.io/docs/installation/ Helm chart: https://kyverno.github.io/kyverno/  Note: Only enable ONE cloud provider per cluster deployment. |
| multinodeNetworking.aws | object | `{"efaDevicesPerGPU":1,"enabled":false}` | AWS-specific configuration for EFA device injection |
| multinodeNetworking.aws.efaDevicesPerGPU | int | `1` | Number of EFA devices to request per GPU (typically 1 or 4) |
| multinodeNetworking.aws.enabled | bool | `false` | Enable AWS-specific Kyverno policy for EFA device injection |
| multinodeNetworking.azure | object | `{"enabled":false,"rdmaDeviceName":"hca_shared_devices_a","rdmaDevicesPerGPU":1}` | Azure-specific configuration for InfiniBand/RDMA |
| multinodeNetworking.azure.enabled | bool | `false` | Enable Azure-specific Kyverno policy for InfiniBand/RDMA configuration |
| multinodeNetworking.azure.rdmaDeviceName | string | `"hca_shared_devices_a"` | RDMA device plugin resource name |
| multinodeNetworking.azure.rdmaDevicesPerGPU | int | `1` | Number of RDMA devices to request per GPU |
| multinodeNetworking.gcp | object | `{"enabled":false}` | GCP-specific configuration for TCP-X/TCP-XO |
| multinodeNetworking.gcp.enabled | bool | `false` | Enable GCP-specific Kyverno policy for TCP-X/TCP-XO configuration |
| multinodeNetworking.oci | object | `{"enabled":false,"rdmaDevicesPerGPU":8}` | OCI-specific configuration for InfiniBand/SR-IOV |
| multinodeNetworking.oci.enabled | bool | `false` | Enable OCI-specific Kyverno policy for InfiniBand/SR-IOV configuration |
| multinodeNetworking.oci.rdmaDevicesPerGPU | int | `8` | Number of RDMA devices (mlnxnics) to request per GPU |
| nameOverride | string | `""` | Overrides for name and fullname templates |
| ncclTest | object | `{"configMapCleanupJob":{"image":{"repository":"docker.io/library/python","tag":"3.12-slim"}},"gpuNodeLabelKey":"nvidia.com/gpu.present","gpuNodeLabelValue":"true","gpuResourceKey":"nvidia.com/gpu","gpusPerNode":1,"iterations":3,"orchestrator":{"image":{"repository":"docker.io/library/python","tag":"3.12-slim"},"resources":{"limits":{"cpu":"1","memory":"512Mi"},"requests":{"cpu":"100m","memory":"256Mi"}}},"validation":{"minBandwidthMBpsAt1024MB":8000},"waitTimeoutSeconds":900,"worker":{"image":{"repository":"nvcr.io/nvidia/nemo-platform/nmp-automodel-training","tag":""},"resources":{"limits":{"cpu":"8","memory":"16Gi"},"requests":{"cpu":"4","memory":"8Gi"}}}}` | NCCL chart test (`helm test`): multi-node allreduce check. Templates use helm.sh/hook: test — they are not created on install/upgrade, only when you run helm test. Requires nodes labeled with gpuNodeLabelKey/gpuNodeLabelValue (default NFD / GPU operator style). See https://helm.sh/docs/topics/chart_tests/ |
| ncclTest.configMapCleanupJob | object | `{"image":{"repository":"docker.io/library/python","tag":"3.12-slim"}}` | Post-test hook Job (after orchestrator): deletes the scripts ConfigMap (helm.sh/hook-weight 5). |
| ncclTest.gpuNodeLabelKey | string | `"nvidia.com/gpu.present"` | Node label used to discover GPU workers (must match your cluster). |
| ncclTest.gpuResourceKey | string | `"nvidia.com/gpu"` | Resource name for GPU capacity on worker pods (e.g. nvidia.com/gpu or a MIG device). |
| ncclTest.gpusPerNode | int | `1` | GPUs per worker pod / per node (torch.distributed nproc_per_node). IMPORTANT: Set this value before testing |
| ncclTest.iterations | int | `3` | How many times to run the full multinode NCCL test (orchestrator loop; env NCCL_TEST_ITERATIONS). Increase the test timeout on helm test if increasing this variable |
| ncclTest.validation.minBandwidthMBpsAt1024MB | int | `8000` | Minimum allreduce bandwidth (MB/s) at 1024MB message size; 0 disables the floor check in nccl_test.py. |
| ncclTest.waitTimeoutSeconds | int | `900` | Max seconds to wait for each worker pod to complete. |
| ngcAPIKey | string | `"YOUR-NGC-API-KEY"` | Your NVIDIA GPU Cloud (NGC) API key authenticates and enables pulling images from the NGC container registry. The existing secret overrides this key if you provide one to the `existingSecret` key. |
| openshiftRoute | object | `{"annotations":{},"enabled":false,"host":"","labels":{},"service":"{{ include \"nemo-platform.ingressBackendService\" . }}","targetPort":"{{ include \"nemo-platform.ingressBackendPort\" . }}","tls":{}}` | OpenShift Route (route.openshift.io/v1). Use on OpenShift to expose the API via a Route instead of Ingress. |
| openshiftRoute.annotations | object | `{}` | Annotations for the route resource. |
| openshiftRoute.enabled | bool | `false` | Specifies whether to create an OpenShift Route for the API service. |
| openshiftRoute.host | string | `""` | Hostname for the route. If empty, the OpenShift router may assign a default hostname. |
| openshiftRoute.labels | object | `{}` | Labels for the route resource. |
| openshiftRoute.service | string | `"{{ include \"nemo-platform.ingressBackendService\" . }}"` | Service name to route to. Defaults to Envoy when auth+envoy enabled, otherwise API (tpl-evaluated). |
| openshiftRoute.targetPort | string | `"{{ include \"nemo-platform.ingressBackendPort\" . }}"` | Target port on the service. Defaults to Envoy or API port depending on auth (tpl-evaluated). |
| openshiftRoute.tls | object | `{}` | Optional TLS configuration (termination, certificate, key, etc.). See OpenShift Route spec. |
| platformConfig | object | `{}` | Platform-wide configuration settings Set configuration here to apply custom, structured configuration across all services. Applied after the base platform config is evaluated for templates. Enables adding / overriding YAML-based elements in the evaluated platform config. It is usually recommended to use this config section instead of `basePlatformConfig` unless you need to use templating features. For example, you can set the NIM default StorageClass via models.controller.backends.k8s-nim-operator.config.default_storage_class. For full configuration reference, see the NeMo Platform's config reference: https://docs.nvidia.com/nemo-platform |
| platformSeedJob | object | This object has the following default values for the platform seed Job configuration. | Platform seed Job (Helm hook: runs after install/upgrade) Runs the platform-seed task (guardrails configs, evaluator system entities, data designer filesets). Uses post-install,post-upgrade hooks so it runs on fresh installs and can be re-triggered on no-op upgrade. |
| platformSeedJob.activeDeadlineSeconds | int | `600` | Maximum time in seconds the Job can run. |
| platformSeedJob.affinity | object | `{}` | Affinity for the platform seeding Job pod. |
| platformSeedJob.backoffLimit | int | `6` | Number of retries before considering the Job failed. |
| platformSeedJob.enabled | bool | `true` | Specifies whether to enable the platform-seed Job. |
| platformSeedJob.extraEnv | list | `[]` | Extra environment variables for the platform-seed container (e.g. CONFIG_STORE_PATH, NMP_PLATFORM_SEED_*). |
| platformSeedJob.nodeSelector | object | `{}` | Node selector for the platform seeding Job pod. |
| platformSeedJob.podLabels | object | `{}` | Additional labels for the platform seeding Job pod. |
| platformSeedJob.podSecurityContext | object | `{}` | Pod-level security context for the platform seeding Job pod. |
| platformSeedJob.resources | object | `{}` | Resource requests/limits for the platform-seed container. |
| platformSeedJob.securityContext | object | `{}` | Container-level security context for the platform-seed container. |
| platformSeedJob.tolerations | list | `[]` | Tolerations for the platform seeding Job pod. |
| platformSeedJob.ttlSecondsAfterFinished | int | `86400` | Seconds after the Job finishes (success or failure) before it is eligible for automatic deletion. |
| podSecurityContext | object | This object has the following default values for the pod security context. | Pod security context settings applied to all services by default. These can be overridden in individual service configurations. |
| postgresql | object | This object has the following default values for the PostgreSQL configuration. | Local PostgreSQL configuration for the NeMo Platform. |
| postgresql.affinity | object | `{}` | Affinity for the PostgreSQL pod. |
| postgresql.auth | object | `{"database":"nemoplatform","existingSecret":"","password":"nemo","username":"nemo"}` | PostgreSQL authentication configuration. |
| postgresql.auth.existingSecret | string | `""` | Name of an existing secret containing a "password" key (or use existingSecretPasswordKey). If set, the chart does not create a secret. |
| postgresql.enabled | bool | `true` | Whether to deploy the embedded PostgreSQL. If enabled, the chart deploys a single-replica PostgreSQL instance using the official Postgres image. It is NOT recommended to use the built-in PostgreSQL for production deployments. It is enabled in the chart by default for ease of getting started with the platform. If you are using an existing PostgreSQL installation, set this to false and use the "externalDatabase" configuration section. |
| postgresql.nodeSelector | object | `{}` | Node selector for the PostgreSQL pod. |
| postgresql.persistence | object | `{"enabled":true,"size":"5Gi","storageClass":""}` | PostgreSQL persistence configuration. |
| postgresql.persistence.storageClass | string | `""` | Storage class for the PostgreSQL PVC. If unset, the cluster default is used. |
| postgresql.podSecurityContext | object | `{}` | Optional pod security context for the PostgreSQL pod (e.g. for OpenShift SCC). |
| postgresql.resources | object | `{}` | Optional resource limits/requests for the PostgreSQL container. |
| postgresql.securityContext | object | `{}` | Optional container security context for the PostgreSQL container. |
| postgresql.service | object | `{"port":5432}` | PostgreSQL service configuration. |
| postgresql.serviceAccount | object | This object has the following default values for the service account configuration. | Service account for the PostgreSQL pod. |
| postgresql.serviceAccount.annotations | object | `{}` | Annotations to add to the service account. |
| postgresql.serviceAccount.automount | bool | `true` | Automatically mount the ServiceAccount's API credentials. |
| postgresql.serviceAccount.create | bool | `true` | Specifies whether a service account should be created for the PostgreSQL pod. |
| postgresql.serviceAccount.name | string | `""` | The name of the service account to use. If not set and create is true, a name is generated from the release fullname. |
| postgresql.tolerations | list | `[]` | Tolerations for the PostgreSQL pod. |
| rbac | object | `{"k8sNimOperatorEnabled":true,"volcanoEnabled":true}` | RBAC configuration settings for optional dependencies |
| rbac.k8sNimOperatorEnabled | bool | `true` | Specifies whether to enable the core Controller to have RBAC permissions to k8s-nim-operator's NIMService for scheduling NIMs. |
| rbac.volcanoEnabled | bool | `true` | Specifies whether to enable the core Controller to have RBAC permissions to Volcano for scheduling distributed jobs. |
| secrets | object | `{"defaultEncryptionKey":{"generated":{"activeDeadlineSeconds":120,"affinity":{},"backoffLimit":3,"enabled":true,"image":{"pullPolicy":"IfNotPresent","repository":"docker.io/library/python","tag":"3.12-slim"},"nodeSelector":{},"podSecurityContext":{},"resources":{},"securityContext":{},"serviceAccount":{"annotations":{},"create":true,"name":""},"tolerations":[],"ttlSecondsAfterFinished":300},"value":""}}` | Secrets service configuration. |
| secrets.defaultEncryptionKey.generated | object | `{"activeDeadlineSeconds":120,"affinity":{},"backoffLimit":3,"enabled":true,"image":{"pullPolicy":"IfNotPresent","repository":"docker.io/library/python","tag":"3.12-slim"},"nodeSelector":{},"podSecurityContext":{},"resources":{},"securityContext":{},"serviceAccount":{"annotations":{},"create":true,"name":""},"tolerations":[],"ttlSecondsAfterFinished":300}` | Generated key configuration used only when value and envFromSecret are empty. The generated key is not rotated or recreated on upgrade. |
| secrets.defaultEncryptionKey.generated.activeDeadlineSeconds | int | `120` | Maximum seconds for the key generation hook to run. |
| secrets.defaultEncryptionKey.generated.affinity | object | `{}` | Affinity for the key generation hook. |
| secrets.defaultEncryptionKey.generated.backoffLimit | int | `3` | Number of retries before the key generation hook is marked failed. |
| secrets.defaultEncryptionKey.generated.image.pullPolicy | string | `"IfNotPresent"` | Image pull policy for the pre-install key generation hook. |
| secrets.defaultEncryptionKey.generated.image.repository | string | `"docker.io/library/python"` | Image repository for the pre-install key generation hook. |
| secrets.defaultEncryptionKey.generated.image.tag | string | `"3.12-slim"` | Image tag for the pre-install key generation hook. |
| secrets.defaultEncryptionKey.generated.nodeSelector | object | `{}` | Node selector for the key generation hook. |
| secrets.defaultEncryptionKey.generated.podSecurityContext | object | `{}` | Optional pod security context for the key generation hook. |
| secrets.defaultEncryptionKey.generated.resources | object | `{}` | Optional resource limits/requests for the key generation hook. |
| secrets.defaultEncryptionKey.generated.securityContext | object | `{}` | Optional container security context for the key generation hook. |
| secrets.defaultEncryptionKey.generated.serviceAccount.annotations | object | `{}` | Annotations to add to the key generation hook service account. |
| secrets.defaultEncryptionKey.generated.serviceAccount.create | bool | `true` | Specifies whether a service account should be created for the key generation hook. |
| secrets.defaultEncryptionKey.generated.serviceAccount.name | string | `""` | The name of the service account to use. Required when create is false. If not set and create is true, a name is generated using the fullname template. |
| secrets.defaultEncryptionKey.generated.tolerations | list | `[]` | Tolerations for the key generation hook. |
| secrets.defaultEncryptionKey.generated.ttlSecondsAfterFinished | int | `300` | Seconds to keep the key generation hook Job after it finishes, if the hook is not deleted first. |
| secrets.defaultEncryptionKey.value | string | `""` | Optional base64-encoded key for encrypting platform secrets. The decoded key must be at least 32 bytes. If empty and envFromSecret is not set, a pre-install hook generates a per-install key. |
| securityContext | object | This object has the following default values for the container security context. | Container security context settings applied to all services by default. These can be overridden in individual service configurations. |
| telemetry.OTEL_EXPORTER_OTLP_ENDPOINT | string | `""` | The OpenTelemetry grpc collector endpoint to export traces and metrics to. |
| telemetry.OTEL_EXPORTER_OTLP_INSECURE | bool | `true` | Whether to use an insecure connection (no TLS) to the OpenTelemetry collector endpoint. |
| telemetry.OTEL_EXPORTER_OTLP_METRICS_ENDPOINT | string | `nil` | The OpenTelemetry metrics exporter endpoint to use. Defaults to `OTEL_EXPORTER_OTLP_ENDPOINT` if not set. |
| telemetry.OTEL_EXPORTER_OTLP_METRICS_INSECURE | bool | `true` | Whether to use an insecure connection (HTTP) to the OpenTelemetry metrics exporter endpoint. Defaults to `OTEL_EXPORTER_OTLP_INSECURE` if not set. |
| telemetry.OTEL_EXPORTER_OTLP_TRACES_ENDPOINT | string | `nil` | The OpenTelemetry traces exporter endpoint to use. Defaults to `OTEL_EXPORTER_OTLP_ENDPOINT` if not set. |
| telemetry.OTEL_EXPORTER_OTLP_TRACES_INSECURE | bool | `true` | Whether to use an insecure connection (HTTP) to the OpenTelemetry traces exporter endpoint. Defaults to `OTEL_EXPORTER_OTLP_INSECURE` if not set. |
| telemetry.OTEL_METRICS_EXPORTER | string | `"none"` | The OpenTelemetry metrics exporter to use. Options are "otlp", "prometheus" or "none" to disable export. |
| telemetry.OTEL_SDK_DISABLED | bool | `false` | Disable OpenTelemetry instrumentation and exporting for all services. |
| telemetry.OTEL_TRACES_EXPORTER | string | `"none"` | The OpenTelemetry traces exporter to use. Options are "otlp" or "none" to disable export. |
