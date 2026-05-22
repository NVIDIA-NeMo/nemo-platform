# Credential Propagation

How credentials flow through the system when {{platform_name}} runs jobs or serves inference.

## Job Credential Propagation

When a user submits a job (customization, evaluation, data generation), the job runs in a Kubernetes pod that needs to call {{platform_name}} APIs — to download datasets, upload results, and read secrets. The platform propagates the submitting user's identity into the job container so it operates with the user's permissions, not elevated service credentials.

The flow:

1. The user submits a job via the API. The platform records the user's principal identity.
2. The platform creates a Kubernetes job with the `NMP_PRINCIPAL` environment variable set to the submitting user's identity.
3. Secrets needed by the job are fetched on behalf of the user (the platform checks that the user has access before injecting them).
4. The job container uses the propagated principal to authenticate API calls back to {{platform_name}}.

Job containers need to run inside the trust boundary so that their `X-NMP-Principal-*` headers are accepted by downstream services. Network policies and gateway configuration enforce this boundary. For the full architecture, see [Security Model](../security-model.md#job-credential-propagation).

## Inference Auth Context

When a model is deployed as an inference endpoint, incoming requests are authenticated at the gateway or service level before reaching the model. The user's auth context is evaluated before the request reaches the model container.

## Trust Implications

The `NMP_PRINCIPAL` environment variable is trusted by {{platform_name}} services. If a user can exec into a job pod and read this variable, they have the submitting user's identity for the duration of the job.

!!! warning
    Ensure Kubernetes RBAC prevents unauthorized access to job pods. Network policies should restrict which pods can reach {{platform_name}} internal endpoints.

## Related

- [Security Model](../security-model.md) — Trust boundaries and job credential propagation.
- [Auth Configuration](configuration.md) — Platform auth configuration.
