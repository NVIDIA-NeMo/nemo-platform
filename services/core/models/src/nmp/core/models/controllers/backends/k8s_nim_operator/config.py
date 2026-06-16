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

    # Security context
    default_user_id: Optional[int] = Field(
        default=None,
        description="Default user ID for NIM containers (security context)",
    )
    default_group_id: Optional[int] = Field(
        default=None,
        description="Default group ID for NIM containers (security context)",
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
        default="busybox",
        description="BusyBox image repository used by plugin init containers.",
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
