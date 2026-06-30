# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Configuration model for k8s-nim-operator backend."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class K8sNimOperatorConfig(BaseModel):
    """
    Configuration for the Kubernetes NIM Operator backend.

    These settings control how NIMService CRDs are generated and deployed.
    """

    # Storage configuration
    default_storage_class: Optional[str] = Field(
        default=None,
        description="Default storage class for PVCs. If not set, the cluster's default StorageClass is used.",
    )
    default_pvc_size: str = Field(
        default="200Gi",
        description="Default PVC size for model storage (used if not specified in deployment config)",
    )

    # PEFT/LoRA configuration
    peft_source: str = Field(
        default="http://nemo-entity-store:8000",
        description="LoRA/PEFT source endpoint (only used when lora_enabled is true)",
    )
    peft_refresh_interval: int = Field(
        default=30,
        ge=1,
        description="PEFT refresh interval in seconds (only used when lora_enabled is true)",
    )
    lora_sidecar_image_name: str = Field(
        default="nmp-api",
        description=(
            "Image name (without registry/tag) for the LoRA adapters sidecar container. "
            "Registry and tag are taken from the platform config (NMP_IMAGE_REGISTRY / NMP_IMAGE_TAG). "
            "Override to 'nmp-automodel-tasks' for local dev when that image is already available "
            "but nmp-api is not."
        ),
    )
    lora_sidecar_command: list[str] = Field(
        default=["nemo", "services", "run", "--sidecars", "adapters"],
        description=(
            "Kubernetes container command (entrypoint) for the LoRA sidecar. "
            "Default uses the nmp-platform-runner entrypoint present in nmp-api. "
            "When using nmp-automodel-tasks set to ['python'] and set lora_sidecar_args to "
            "['-m', 'nmp.core.models.sidecars.adapters.main']."
        ),
    )
    lora_sidecar_args: list[str] = Field(
        default=[],
        description=(
            "Kubernetes container args for the LoRA sidecar (appended after lora_sidecar_command). "
            "Leave empty for nmp-api. "
            "Set to ['-m', 'nmp.core.models.sidecars.adapters.main'] when using nmp-automodel-tasks."
        ),
    )

    # Security context for the NIM (operator) path: applied to the NIMService /
    # NIMCache CRs. NOTE: securityContext uid/gid is engine-specific -- NIM images
    # expect different values (operator default 1000/2000) than the vLLM image
    # (2000/0, see default_vllm_*). When NIM is migrated onto the raw-object
    # compilers (vllm_k8s_compiler), keep passing THESE fields for the NIM path --
    # do not reuse default_vllm_user_id/_group_id. See the FUTURE note in
    # vllm_k8s_compiler.py.
    default_user_id: Optional[int] = Field(
        default=None,
        description="Default user ID for NIM containers (security context)",
    )
    default_group_id: Optional[int] = Field(
        default=None,
        description="Default group ID for NIM containers (security context)",
    )

    # Security context for the directly-emitted vLLM path (puller Job + server
    # Deployment). Defaults match the user the upstream vllm/vllm-openai image
    # ships ("vllm", uid 2000, gid 0): a non-root uid that HAS an /etc/passwd
    # entry, so torch/inductor's getpass.getuser() (pwd.getpwuid) does not crash.
    # gid 0 (root group) is the image's group and is the standard
    # arbitrary-uid-friendly group. The puller writes weights under this uid/gid
    # so the server can read them.
    default_vllm_user_id: Optional[int] = Field(
        default=2000,
        description="Default user ID for vLLM puller + server pods (security context). "
        "Defaults to 2000 to match the upstream vLLM image's 'vllm' user, which has an "
        "/etc/passwd entry (avoids torch getpwuid crashes from an unknown uid).",
    )
    default_vllm_group_id: Optional[int] = Field(
        default=0,
        description="Default group ID / fsGroup for vLLM puller + server pods. Defaults to 0 "
        "(root group) to match the upstream vLLM image and keep weights readable across the "
        "puller and server pods.",
    )

    # Files service configuration
    files_auth_secret: str = Field(
        default="nemo-models-files-token",
        description="Kubernetes secret name for Files service authentication (HF_TOKEN)",
    )
    huggingface_model_puller_image_pull_secret: str = Field(
        default="nvcrimagepullsecret",
        description="The name of the image pull secret for the modelPuller image",
    )

    busybox_image: str = Field(
        default="docker.io/library/busybox",
        description="BusyBox image repository used by plugin init containers. "
        "Fully qualified (docker.io/library/...) so it resolves on container runtimes "
        "that enforce fully-qualified image names (short names like 'busybox' fail there).",
    )

    busybox_image_tag: str = Field(
        default="latest",
        description="BusyBox image tag used by plugin init containers.",
    )

    # Auth configuration
    auth_secret: str = Field(
        default="ngc-api",
        description="NGC API key secret name for pulling NIM images",
    )

    # NIMService image configuration
    default_nimservice_image: str = Field(
        default="nvcr.io/nim/nvidia/llm-nim",
        description="Default NIMService image repository (used if not specified in deployment config)",
    )
    default_nimservice_image_tag: str = Field(
        default="1.13.1",
        description="Default NIMService image tag (used if not specified in deployment config)",
    )

    # vLLM image configuration (vLLM engine on k8s; raw-object emission path)
    default_vllm_image: str = Field(
        default="vllm/vllm-openai",
        description="Default vLLM server image repository (used if not specified in deployment config)",
    )
    default_vllm_image_tag: str = Field(
        default="v0.22.1",
        description="Default vLLM server image tag (used if not specified in deployment config)",
    )

    # NIM runtime configuration
    nim_guided_decoding_backend: str = Field(
        default="outlines",
        description="Default guided decoding backend for NIM (e.g., 'outlines', 'auto', 'lm-format-enforcer')",
    )

    # Kubernetes namespace (optional override)
    namespace: Optional[str] = Field(
        default=None,
        description="Kubernetes namespace for NIM deployments (defaults to controller's namespace if not set)",
    )

    # ServiceAccount for directly-emitted workloads (vLLM Deployment pods + weight
    # puller Job). A single shared models ServiceAccount is used; the platform Helm
    # chart is responsible for creating it and granting any required RBAC/SCC.
    # If not set, pods run under the namespace's default ServiceAccount.
    service_account_name: Optional[str] = Field(
        default=None,
        description="ServiceAccount name for directly-emitted vLLM Deployment pods and the weight-puller Job. "
        "If not set, the namespace default ServiceAccount is used.",
    )

    # Shared memory (/dev/shm) for directly-emitted vLLM Deployment pods. vLLM uses
    # /dev/shm for tensor-parallel NCCL communication. If not set, the dshm emptyDir
    # is mounted with no explicit size limit (uses the node default).
    default_shared_memory_size_limit: Optional[str] = Field(
        default=None,
        description="Shared memory (/dev/shm) size limit for vLLM Deployment pods (e.g. '8Gi'). "
        "If not set, the emptyDir uses the node default size.",
    )

    # Default Kubernetes configuration for all NIM deployments
    default_resources: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Default Kubernetes resource requirements for all NIM deployments. "
        "Can be overridden per-deployment via k8s_nim_operator_config. "
        "Example: {'requests': {'cpu': '2', 'memory': '8Gi'}, 'limits': {'memory': '16Gi'}}",
        examples=[{"requests": {"cpu": "2", "memory": "8Gi"}, "limits": {"memory": "16Gi"}}],
    )
    default_tolerations: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Default Kubernetes tolerations for all NIM deployments. "
        "Can be overridden per-deployment via k8s_nim_operator_config. "
        "Example: [{'key': 'nvidia.com/gpu', 'operator': 'Exists', 'effect': 'NoSchedule'}]",
        examples=[[{"key": "nvidia.com/gpu", "operator": "Exists", "effect": "NoSchedule"}]],
    )
    default_node_selector: Optional[Dict[str, str]] = Field(
        default=None,
        description="Default Kubernetes node selector for all NIM deployments. "
        "Can be overridden per-deployment via k8s_nim_operator_config. "
        "Example: {'node-type': 'gpu-node', 'zone': 'us-west1-a'}",
        examples=[{"node-type": "gpu-node", "zone": "us-west1-a"}],
    )
    default_labels: Optional[Dict[str, str]] = Field(
        default=None,
        description="Default Kubernetes labels applied to NIMService and NIMCache resources and their child resources (e.g. pods). "
        "Merged with controller-managed labels; controller labels take precedence on conflict. "
        "Example: {'team': 'ml-platform', 'environment': 'prod'}",
        examples=[{"team": "ml-platform", "environment": "prod"}],
    )
    default_annotations: Optional[Dict[str, str]] = Field(
        default=None,
        description="Default Kubernetes annotations applied to NIMService and NIMCache resources and their child resources (e.g. pods, PVCs). "
        "Merged with controller-managed annotations; controller annotations take precedence on conflict. "
        "Example: {'prometheus.io/scrape': 'true'}",
        examples=[{"prometheus.io/scrape": "true"}],
    )
    default_startup_probe_grace_period_seconds: Optional[int] = Field(
        default=None,
        description="Default grace period in seconds for NIM startup. "
        "Can be overridden per-deployment via k8s_nim_operator_config. "
        "Determines how long Kubernetes will wait for the NIM to become ready before restarting it. "
        "If not set, defaults to 600 seconds (10 minutes). "
        "Example: 600 (10 minutes)",
        examples=[600],
        gt=0,
    )

    # PENDING timeout and crash loop detection
    pending_timeout_seconds: int = Field(
        default=7200,
        ge=60,
        description="Maximum time in seconds a deployment may stay in PENDING before being "
        "transitioned to ERROR. Default: 7200 (2 hours).",
    )

    max_restart_count: int = Field(
        default=5,
        ge=1,
        description="Maximum number of pod container restarts before a PENDING deployment is "
        "transitioned to ERROR (crash loop detection). Default: 5.",
    )
