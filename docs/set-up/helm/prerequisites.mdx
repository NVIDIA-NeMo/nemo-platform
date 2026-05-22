<a id="install-prerequisites"></a>
# Prerequisites

Before installing the {{helm_chart_short_name}}, review requirements and create necessary secrets using your NGC API key.

---

## Review Requirements

To check the hardware and software specifications required for installing the {{helm_chart_short_name}}, review [](../../requirements.md).

For storage and persistent volume configuration (including ReadWriteMany and StorageClass configuration), see [](persistent-volumes.md).

---

<a id="nemo-ms-ngc-catalog-secrets"></a>
## Create NGC API Key and Secrets

You need to have an NGC account, create an NGC API key, and create secrets using the key to access and download the {{helm_chart_short_name}} and Docker images.

To learn more about using Helm charts in the NGC Catalog console in general, refer to the [Helm Charts](https://docs.nvidia.com/ngc/gpu-cloud/ngc-catalog-user-guide/index.html#helm-charts) section in the _NGC Catalog User Guide_.

1. Create an NGC API key following the instructions at [Generating NGC API Keys](https://docs.nvidia.com/ngc/latest/ngc-private-registry-user-guide.html#generating-ngc-api-keys).

 !!! tip

 While creating the key, make sure that you include the following permissions at a minimum:

 - NGC Catalog
 - Public API Endpoints

 For more information about the service permissions you can include, refer to [Supported NGC Applications and API Key Types](https://docs.nvidia.com/ngc/gpu-cloud/ngc-private-registry-user-guide/index.html#supported-ngc-applications-and-api-key-types) in the NVIDIA NGC Catalog documentation.

2. Store the key into your shell environment.

 ```sh
 export NGC_API_KEY=<your-ngc-api-key>
 ```

 The rest of the installation guide assumes that you have set up the environment variable `NGC_API_KEY`.

3. Set up the following secrets in a namespace where you want to install the charts.

 * Docker registry image pull secret:
 This secret allows pods to pull container images from the NGC Catalog.

 ```sh
 kubectl create secret \
 docker-registry nvcrimagepullsecret \
 --docker-server=nvcr.io \
 --docker-username='$oauthtoken' \
 --docker-password=$NGC_API_KEY \
 --namespace <namespace-to-install-nemo-microservices>
 ```

 * Generic secret:
 This secret is for authenticating to download models from the NGC Catalog.

 ```sh
 kubectl create secret generic ngc-api \
 --from-literal=NGC_API_KEY=$NGC_API_KEY \
 --namespace <namespace-to-install-nemo-microservices>
 ```

For more information about various secrets you might need to create and set up through the {{helm_chart_short_name}} depending on your use case, refer to [](../../get-started/concepts/manage-secrets.md).
