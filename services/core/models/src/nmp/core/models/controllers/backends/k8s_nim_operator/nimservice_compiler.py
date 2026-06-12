# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NIMService compiler for transforming ModelDeploymentConfig into NIMService CRD."""

from logging import getLogger
from typing import Any, Optional
from urllib.parse import urljoin

from nemo_platform.types.inference.model_deployment import ModelDeployment
from nemo_platform.types.inference.model_deployment_config import ModelDeploymentConfig
from nemo_platform.types.models.model_entity import ModelEntity
from nmp.common.config import get_platform_config
from nmp.core.models.app import is_multi_llm_image, parse_model_name_revision
from nmp.core.models.app.constants import MODEL_MANAGED_BY_LABEL, MODEL_MANAGED_BY_MODELS_CONTROLLER
from nmp.core.models.app.utils import _get_k8s_safe_name
from nmp.core.models.controllers.backends.common import DeploymentConfigView, deployment_config_view
from nmp.core.models.controllers.backends.k8s_nim_operator.config import K8sNimOperatorConfig
from nmp.core.models.controllers.backends.k8s_nim_operator.types.nimcache import (
    Hf,
    NIMCache,
    Pvc,
    Source,
)
from nmp.core.models.controllers.backends.k8s_nim_operator.types.nimcache import (
    Resources as NIMCacheResources,
)
from nmp.core.models.controllers.backends.k8s_nim_operator.types.nimcache import (
    Spec as NIMCacheSpec,
)
from nmp.core.models.controllers.backends.k8s_nim_operator.types.nimcache import (
    Storage as NIMCacheStorage,
)
from nmp.core.models.controllers.backends.k8s_nim_operator.types.nimcache import (
    Toleration as NIMCacheToleration,
)
from nmp.core.models.controllers.backends.k8s_nim_operator.types.nimservice import (
    ContainerSpec,
    EnvItem,
    Expose,
    HttpGet2,
    Image,
    Limits1,
    NIMService,
    Probe2,
    Requests1,
    Resources,
    SecretKeyRef,
    Spec,
    StartupProbe,
    Storage,
    ValueFrom,
)

logger = getLogger(__name__)
TOOL_CALL_PLUGIN_PATH = "/model-store/plugin/plugin.py"
TOOL_CALL_PLUGIN_SCRATCH_DIR = "/scratch/plugin"
TOOL_CALL_PLUGIN_FINALIZE_SCRIPT_TEMPLATE = """set -euo pipefail
py_files="$(find "{scratch_dir}" -type f -name '*.py' || true)"
count="$(printf '%s\n' "$py_files" | sed '/^$/d' | wc -l | tr -d ' ')"
if [ "$count" -eq 0 ]; then
  echo "tool_call_plugin fileset contains no .py files"
  exit 1
fi
if [ "$count" -ne 1 ]; then
  echo "tool_call_plugin fileset must contain exactly one .py file, found $count"
  printf '%s\n' "$py_files"
  exit 1
fi
plugin_file="$(printf '%s\n' "$py_files" | sed '/^$/d' | sed -n '1p')"
mv "$plugin_file" "{plugin_path}"
"""


def _get_files_hf_url() -> str:
    """Get Files service HF-compatible API URL."""
    return urljoin(get_platform_config().get_service_url("files"), "apis/files/v2/hf")


def _nimcache_default_resources(backend_config: K8sNimOperatorConfig) -> Optional[NIMCacheResources]:
    """Map backend default_resources (K8s requests/limits) to NIMCache Resources (cpu, memory)."""
    raw = backend_config.default_resources
    if not raw or not isinstance(raw, dict):
        return None
    requests = raw.get("requests") or {}
    limits = raw.get("limits") or {}
    if not isinstance(requests, dict):
        requests = {}
    if not isinstance(limits, dict):
        limits = {}
    cpu = requests.get("cpu") or limits.get("cpu")
    memory = requests.get("memory") or limits.get("memory")
    if cpu is None and memory is None:
        return None
    return NIMCacheResources(cpu=cpu, memory=memory)


def _nimcache_default_tolerations(backend_config: K8sNimOperatorConfig) -> Optional[list[NIMCacheToleration]]:
    """Convert backend default_tolerations to NIMCache Toleration list."""
    raw = backend_config.default_tolerations
    if not raw or not isinstance(raw, list):
        return None
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(NIMCacheToleration(**{k: v for k, v in item.items() if v is not None}))
    return out if out else None


def compile_nimcache(
    backend_config: K8sNimOperatorConfig,
    k8s_namespace: str,
    resource_name: str,
    model_namespace: str,
    model_name: str,
    pvc_size: str,
    huggingface_model_puller: str,
    model_revision: Optional[str] = None,
) -> NIMCache:
    """Generate a NIMCache CR for models whose weights are served via the Files service HF-compatible API.

    Used for Files service weights (e.g. fileset-backed or SFT full weights in Files).
    models, e.g. multi-LLM pulling through Files). The NIMCache job pulls from the Files endpoint
    and populates the cache so the NIM pod uses pre-filled storage.

    Args:
        backend_config: Backend configuration
        k8s_namespace: Kubernetes namespace
        resource_name: Name for the NIMCache resource (already K8s-safe)
        model_namespace: Model namespace in Entity Store
        model_name: Model name in Entity Store
        pvc_size: PVC size for storage
        model_revision: Optional model revision

    Returns:
        NIMCache CR object
    """
    logger.info(f"Generating NIMCache for Files service model: {model_namespace}/{model_name}")

    files_full_url = _get_files_hf_url()

    cr_labels = _merge_default_labels(
        backend_config.default_labels,
        {
            "app.kubernetes.io/name": resource_name,
            MODEL_MANAGED_BY_LABEL: MODEL_MANAGED_BY_MODELS_CONTROLLER,
        },
    )
    cr_annotations = _merge_default_annotations(backend_config.default_annotations)
    nimcache_metadata: dict[str, Any] = {
        "name": resource_name,
        "namespace": k8s_namespace,
        "labels": cr_labels,
    }
    if cr_annotations:
        nimcache_metadata["annotations"] = cr_annotations

    nimcache = NIMCache(
        apiVersion="apps.nvidia.com/v1alpha1",
        kind="NIMCache",
        metadata=nimcache_metadata,
        spec=NIMCacheSpec(
            storage=NIMCacheStorage(
                pvc=Pvc(
                    create=True,
                    name=resource_name,
                    size=pvc_size,
                    storageClass=backend_config.default_storage_class or None,
                    volumeAccessMode="ReadWriteOnce",
                    annotations=cr_annotations,
                )
            ),
            source=Source(
                # Using Hf (HuggingFace) source type for Files service HF-compatible API
                hf=Hf(
                    endpoint=files_full_url,
                    namespace=model_namespace,
                    authSecret=backend_config.files_auth_secret,
                    modelPuller=huggingface_model_puller,
                    pullSecret=backend_config.huggingface_model_puller_image_pull_secret,
                    modelName=model_name,
                    revision=model_revision,
                )
            ),
            userID=backend_config.default_user_id,
            groupID=backend_config.default_group_id,
            resources=_nimcache_default_resources(backend_config),
            tolerations=_nimcache_default_tolerations(backend_config),
            nodeSelector=backend_config.default_node_selector,
        ),
    )

    logger.info(f"Generated NIMCache {k8s_namespace}/{resource_name} for model {model_namespace}/{model_name}")
    return nimcache


def _generate_tool_plugin_container(
    deployment: ModelDeployment,
    config: ModelDeploymentConfig,
    model_entity: ModelEntity | None,
    backend_config: K8sNimOperatorConfig,
    huggingface_model_puller: str | None,
) -> list[ContainerSpec] | None:
    nim_config = deployment_config_view(config)
    plugin_fileset: str | None = None
    if nim_config.tool_call_config and nim_config.tool_call_config.tool_call_plugin:
        plugin_fileset = nim_config.tool_call_config.tool_call_plugin
    elif (
        model_entity
        and model_entity.spec
        and model_entity.spec.tool_call_config
        and model_entity.spec.tool_call_config.tool_call_plugin
    ):
        plugin_fileset = model_entity.spec.tool_call_config.tool_call_plugin

    if plugin_fileset:
        logger.info(f"Pulling tool_call_plugin fileset '{plugin_fileset}' for {deployment.workspace}/{deployment.name}")
        container_name = f"md-plugin-{deployment.workspace}-{deployment.name}"
        container_name = _get_k8s_safe_name(container_name, max_length=63, name_type="label")
        if not huggingface_model_puller:
            logger.warning(
                "tool_call_plugin is configured but huggingface_model_puller image is unavailable; "
                "skipping plugin init containers"
            )
            return None

        files_url = _get_files_hf_url()

        # Require explicit tag. The tag separator ':' must be after the last '/'
        # so registry ports like registry:5000/... are not treated as a tag.
        hmp = huggingface_model_puller
        last_slash_idx = hmp.rfind("/")
        last_colon_idx = hmp.rfind(":")
        if last_colon_idx <= last_slash_idx:
            logger.warning(f"huggingface_model_puller image {huggingface_model_puller} does not have a tag")
            return None

        puller_repo = hmp[:last_colon_idx]
        puller_tag = hmp[last_colon_idx + 1 :]

        return [
            ContainerSpec(
                name=_get_k8s_safe_name(container_name, max_length=63, suffix="-prepare", name_type="label"),
                image=Image(
                    repository=backend_config.busybox_image,
                    tag=backend_config.busybox_image_tag,
                    pullPolicy="IfNotPresent",
                ),
                command=[
                    "sh",
                    "-c",
                    "set -e; mkdir -p /model-store/plugin /scratch/plugin; "
                    f"rm -f {TOOL_CALL_PLUGIN_PATH}; rm -rf /scratch/plugin/*",
                ],
            ),
            ContainerSpec(
                name=_get_k8s_safe_name(container_name, max_length=63, suffix="-pull", name_type="label"),
                image=Image(
                    repository=puller_repo,
                    tag=puller_tag,
                    pullPolicy="IfNotPresent",
                    pullSecrets=(
                        [backend_config.huggingface_model_puller_image_pull_secret]
                        if backend_config.huggingface_model_puller_image_pull_secret
                        else None
                    ),
                ),
                command=["download", plugin_fileset, "--local-dir", TOOL_CALL_PLUGIN_SCRATCH_DIR],
                env=[
                    EnvItem(name="HF_ENDPOINT", value=files_url),
                    EnvItem(name="HF_TOKEN", value="service:models"),
                ],
            ),
            ContainerSpec(
                name=_get_k8s_safe_name(container_name, max_length=63, suffix="-finalize", name_type="label"),
                image=Image(
                    repository=backend_config.busybox_image,
                    tag=backend_config.busybox_image_tag,
                    pullPolicy="IfNotPresent",
                ),
                command=[
                    "sh",
                    "-c",
                    TOOL_CALL_PLUGIN_FINALIZE_SCRIPT_TEMPLATE.format(
                        scratch_dir=TOOL_CALL_PLUGIN_SCRATCH_DIR,
                        plugin_path=TOOL_CALL_PLUGIN_PATH,
                    ),
                ],
            ),
        ]

    return None


def compile_nimservice(
    deployment: ModelDeployment,
    config: ModelDeploymentConfig,
    backend_config: K8sNimOperatorConfig,
    k8s_namespace: str,
    resource_name: str,
    nimcache_name: str | None = None,
    model_entity: ModelEntity | None = None,
    huggingface_model_puller: str | None = None,
) -> NIMService:
    """Compile a NIMService CRD from a ModelDeployment and its configuration.

    Args:
        deployment: The ModelDeployment object
        config: The ModelDeploymentConfig
        backend_config: Backend configuration
        k8s_namespace: Kubernetes namespace
        resource_name: Name for the NIMService resource
        nimcache_name: Optional NIMCache name when pulling weights from Files service (weights in /model-store).
        model_entity: Optional ModelEntity for propagating entity-level settings (e.g. trust_remote_code).

    Returns:
        NIMService CR object
    """
    logger.info(
        f"Compiling NIMService for deployment {deployment.workspace}/{deployment.name} "
        f"with config {config.workspace}/{config.name}@{config.entity_version}"
    )

    nim_config = deployment_config_view(config)
    platform_config = get_platform_config()
    image_pull_secrets = [secret.name for secret in platform_config.image_pull_secrets]
    pvc_size = nim_config.disk_size if nim_config.disk_size else backend_config.default_pvc_size

    # Determine startup_probe_grace_seconds with precedence: backend default < per-deployment config
    startup_grace_seconds = backend_config.default_startup_probe_grace_period_seconds
    if nim_config.k8s_nim_operator_config:
        if hasattr(nim_config.k8s_nim_operator_config, "model_dump"):
            config_dict = nim_config.k8s_nim_operator_config.model_dump(exclude_none=True)
            if "startup_probe_grace_seconds" in config_dict:
                startup_grace_seconds = config_dict.get("startup_probe_grace_seconds")
        elif isinstance(nim_config.k8s_nim_operator_config, dict):
            if "startup_probe_grace_seconds" in nim_config.k8s_nim_operator_config:
                startup_grace_seconds = nim_config.k8s_nim_operator_config.get("startup_probe_grace_seconds")

    plugin_containers = _generate_tool_plugin_container(
        deployment=deployment,
        config=config,
        model_entity=model_entity,
        backend_config=backend_config,
        huggingface_model_puller=huggingface_model_puller,
    )
    plugin_path = TOOL_CALL_PLUGIN_PATH if plugin_containers is not None else None

    env_vars = _compile_env_vars(
        backend_config, nim_config, nimcache_name, model_entity, tool_call_plugin_path=plugin_path
    )
    sidecar_env_vars = env_vars + [EnvItem(name=k, value=v) for k, v in platform_config.to_shared_envvars().items()]
    # Operator uses authSecret for NGC_API_KEY by default; when NIMCache is HF (or NIMService has hf:// model name)
    # it injects HF_TOKEN from authSecret instead. We use Files placeholder secret when we have NIMCache (always HF);
    # otherwise use NGC secret so the NIM can pull weights from NGC at runtime.
    auth_secret = backend_config.files_auth_secret if nimcache_name else backend_config.auth_secret

    sidecar_containers = []
    if nim_config.lora_enabled:
        sidecar_containers = [
            ContainerSpec(
                name=_get_k8s_safe_name(resource_name, max_length=63, suffix="-lora-sidecar", name_type="label"),
                image=Image(
                    repository=f"{platform_config.image_registry}/nmp-api",
                    tag=platform_config.image_tag,
                    pullPolicy="IfNotPresent",
                    pullSecrets=image_pull_secrets if image_pull_secrets else None,
                ),
                command=[
                    "nemo",
                    "services",
                    "run",
                    "--sidecars",
                    "adapters",
                ],
                env=sidecar_env_vars,
            )
        ]
    spec_labels = _merge_default_labels(
        backend_config.default_labels,
        {
            "app.kubernetes.io/name": resource_name,
            MODEL_MANAGED_BY_LABEL: MODEL_MANAGED_BY_MODELS_CONTROLLER,
            "nmp.nvidia.com/deployment-workspace": deployment.workspace,
            "nmp.nvidia.com/deployment-name": deployment.name,
        },
    )
    spec_annotations = _merge_default_annotations(backend_config.default_annotations)

    spec = Spec(
        authSecret=auth_secret,
        image=Image(
            repository=nim_config.image_name or backend_config.default_nimservice_image,
            tag=nim_config.image_tag or backend_config.default_nimservice_image_tag,
            pullPolicy="IfNotPresent",
            pullSecrets=image_pull_secrets if image_pull_secrets else None,
        ),
        resources=_compile_resources(nim_config.gpu),
        storage=_compile_storage(backend_config, resource_name, pvc_size, nimcache_name),
        expose=_compile_expose(),
        env=env_vars,
        startupProbe=_compile_startup_probe(startup_grace_seconds),
        replicas=1,
        labels=spec_labels,
        annotations=spec_annotations,
        userID=backend_config.default_user_id,
        groupID=backend_config.default_group_id,
        initContainers=plugin_containers,
        sidecarContainers=sidecar_containers,
    )

    # Apply configuration in precedence order: backend defaults < per-deployment k8s_nim_operator_config < override_config

    # Apply backend config defaults
    backend_defaults = {}
    if backend_config.default_resources:
        backend_defaults["resources"] = backend_config.default_resources
    if backend_config.default_tolerations:
        backend_defaults["tolerations"] = backend_config.default_tolerations
    if backend_config.default_node_selector:
        backend_defaults["node_selector"] = backend_config.default_node_selector

    spec = _apply_k8s_nim_operator_config(spec, backend_defaults)

    # Apply per-deployment k8s_nim_operator_config (overrides backend defaults)
    if nim_config.k8s_nim_operator_config:
        spec = _apply_k8s_nim_operator_config(spec, nim_config.k8s_nim_operator_config)

    # Apply override_config (final override)
    if nim_config.override_config:
        spec = _apply_override_config(spec, nim_config.override_config)

    nimservice_metadata: dict[str, Any] = {
        "name": resource_name,
        "namespace": k8s_namespace,
        "labels": _merge_default_labels(
            backend_config.default_labels,
            {
                "app.kubernetes.io/name": resource_name,
                MODEL_MANAGED_BY_LABEL: MODEL_MANAGED_BY_MODELS_CONTROLLER,
                "nmp.nvidia.com/deployment-workspace": deployment.workspace,
                "nmp.nvidia.com/deployment-name": deployment.name,
            },
        ),
    }
    nimservice_cr_annotations = _merge_default_annotations(backend_config.default_annotations)
    if nimservice_cr_annotations:
        nimservice_metadata["annotations"] = nimservice_cr_annotations

    nimservice = NIMService(
        apiVersion="apps.nvidia.com/v1alpha1",
        kind="NIMService",
        metadata=nimservice_metadata,
        spec=spec,
    )

    logger.info(f"Compiled NIMService {k8s_namespace}/{resource_name}")
    return nimservice


def _compile_resources(gpu_count: int) -> Resources:
    return Resources(
        limits={"nvidia.com/gpu": Limits1(root=str(gpu_count))},
        requests={"cpu": Requests1(root="1000m")},
    )


def _compile_storage(
    backend_config: K8sNimOperatorConfig, resource_name: str, disk_size: str, nimcache_name: str | None = None
) -> Storage:
    """Compile storage configuration for the NIMService.

    If nimcache_name is provided, configures the NIMService to use the NIMCache.
    Otherwise, creates a standard PVC.
    """
    if nimcache_name:
        logger.info(f"Configuring NIMService to use NIMCache: {nimcache_name}")
        return Storage(
            nimCache={
                "name": nimcache_name,
                "profile": "",
            }
        )
    else:
        return Storage(
            pvc={
                "create": True,
                "name": resource_name,
                "size": disk_size,
                "storageClass": backend_config.default_storage_class or None,
                "volumeAccessMode": "ReadWriteOnce",
            }
        )


def _compile_expose() -> Expose:
    return Expose(service={"type": "ClusterIP", "port": 8000})


def _compile_startup_probe(grace_seconds: int | None = None) -> StartupProbe:
    """Compile startup probe configuration for NIM containers.

    NIMs can take several minutes to start up (downloading/loading models).
    This configures a 10-minute grace period by default.

    Args:
        grace_seconds: Optional grace period in seconds. If provided, failureThreshold
                      is calculated by dividing by 10 (rounded up). Defaults to 600 seconds (10 minutes).
    """
    # Default to 600 seconds (10 minutes) if not specified
    if grace_seconds is None:
        grace_seconds = 600

    # Calculate failureThreshold by dividing grace_seconds by periodSeconds (10s), rounding up
    # Using math.ceil equivalent: (grace_seconds + 9) // 10
    failure_threshold = (grace_seconds + 9) // 10

    return StartupProbe(
        enabled=True,
        probe=Probe2(
            httpGet=HttpGet2(
                path="/v1/health/ready",
                port=8000,
            ),
            periodSeconds=10,
            timeoutSeconds=5,
            failureThreshold=failure_threshold,
            successThreshold=1,
        ),
    )


def _compile_env_vars(
    backend_config: K8sNimOperatorConfig,
    nim_config: DeploymentConfigView,
    nimcache_name: str | None = None,
    model_entity: ModelEntity | None = None,
    tool_call_plugin_path: str | None = None,
) -> list[EnvItem]:
    """Compile environment variables for the NIMService.

    Args:
        backend_config: Backend configuration
        nim_config: NIM deployment configuration
        nimcache_name: Optional NIMCache name when pulling weights from Files service (weights in /model-store).
        model_entity: Optional model entity this deployment references.
        tool_call_plugin_path: Optional resolved plugin path for NIM_TOOL_PARSER_PLUGIN.
    Returns:
        List of environment variables
    """
    default_envs = {"NIM_GUIDED_DECODING_BACKEND": backend_config.nim_guided_decoding_backend}
    env_items = []

    model_fqdn: str | None = None
    if nim_config.model_name:
        parsed_namespace, parsed_name, parsed_revision = parse_model_name_revision(
            model_namespace=nim_config.model_namespace,
            model_name=nim_config.model_name,
            model_revision=nim_config.model_revision,
        )
        if parsed_namespace and parsed_name:
            model_fqdn = f"{parsed_namespace}/{parsed_name}"
        elif parsed_name:
            model_fqdn = parsed_name
        if model_fqdn and parsed_revision:
            model_fqdn += f"@{parsed_revision}"

    if model_fqdn:
        default_envs["NIM_MODEL_NAME"] = model_fqdn
        default_envs["NIM_SERVED_MODEL_NAME"] = model_fqdn

    if nimcache_name:
        # NIMCache is used to pull Files service weights; they're in /model-store.
        default_envs["NIM_MODEL_NAME"] = "/model-store"

    if nim_config.lora_enabled:
        # default_envs["NIM_PEFT_SOURCE"] = backend_config.peft_source
        default_envs["NIM_PEFT_SOURCE"] = "/scratch/loras"
        default_envs["NIM_PEFT_REFRESH_INTERVAL"] = str(backend_config.peft_refresh_interval)

    # Only set NIM_FT_MODEL for model-specific NIM (not multi-LLM). When nimcache_name is set,
    # weights are in /model-store; multi-LLM uses only NIM_MODEL_NAME (see NIM fine-tuned model docs).
    effective_image = nim_config.image_name or backend_config.default_nimservice_image
    if nimcache_name and not is_multi_llm_image(effective_image):
        logger.info("Adding fine-tuned model environment variables for model-specific container")
        default_envs["NIM_FT_MODEL"] = "/model-store"
        default_envs["NIM_CUSTOM_MODEL"] = "/model-store"
        default_envs["NIM_MODEL_PATH"] = "/model-store"  # NIM LLM 2.0 expected parameter

    if model_entity:
        default_envs["NMP_MODEL_ENTITY_WORKSPACE"] = model_entity.workspace
        default_envs["NMP_MODEL_ENTITY_NAME"] = model_entity.name
        if model_entity.trust_remote_code:
            default_envs["NIM_FORCE_TRUST_REMOTE_CODE"] = "1"
            default_envs["NIM_TRUST_CUSTOM_CODE"] = "1"  # NIM LLM 2.0 expected parameter

        # Set NIM env vars from model entity spec (base layer)
        if model_entity.spec:
            if model_entity.spec.chat_template:
                default_envs["NIM_CHAT_TEMPLATE"] = model_entity.spec.chat_template

            if model_entity.spec.tool_call_config:
                tool_cfg = model_entity.spec.tool_call_config
                if tool_cfg.tool_call_parser:
                    default_envs["NIM_TOOL_CALL_PARSER"] = tool_cfg.tool_call_parser
                if tool_call_plugin_path:
                    # Point to the actual .py file discovered in the pulled fileset
                    default_envs["NIM_TOOL_PARSER_PLUGIN"] = tool_call_plugin_path
                if tool_cfg.auto_tool_choice is not None:
                    default_envs["NIM_ENABLE_AUTO_TOOL_CHOICE"] = "1" if tool_cfg.auto_tool_choice else "0"

    # Deployment-level overrides (highest priority).
    if nim_config.chat_template:
        default_envs["NIM_CHAT_TEMPLATE"] = nim_config.chat_template

    deploy_tool_cfg = nim_config.tool_call_config
    if deploy_tool_cfg:
        if deploy_tool_cfg.tool_call_parser:
            default_envs["NIM_TOOL_CALL_PARSER"] = deploy_tool_cfg.tool_call_parser
        if deploy_tool_cfg.tool_call_plugin:
            if tool_call_plugin_path:
                default_envs["NIM_TOOL_PARSER_PLUGIN"] = tool_call_plugin_path
            else:
                logger.warning(
                    "Deployment tool_call_config.tool_call_plugin is set but no plugin path was prepared by init "
                    "containers."
                )
        if deploy_tool_cfg.auto_tool_choice is not None:
            default_envs["NIM_ENABLE_AUTO_TOOL_CHOICE"] = "1" if deploy_tool_cfg.auto_tool_choice else "0"

    if nim_config.additional_envs:
        default_envs.update(nim_config.additional_envs)

    for key, value in default_envs.items():
        env_items.append(EnvItem(name=key, value=str(value)))

    # When using NIMCache (Files service), also pass NGC_API_KEY from auth secret for parity with Docker.
    if nimcache_name:
        env_items.append(
            EnvItem(
                name="NGC_API_KEY",
                valueFrom=ValueFrom(secretKeyRef=SecretKeyRef(name=backend_config.auth_secret, key="NGC_API_KEY")),
            )
        )

    return env_items


def _apply_k8s_nim_operator_config(spec: Spec, k8s_config: Any) -> Spec:
    """Apply k8s_nim_operator_config to the NIMService spec.

    Converts snake_case Python field names to camelCase Kubernetes field names.
    """
    logger.info("Applying k8s_nim_operator_config to NIMService spec")

    # Convert k8s_config to dict, excluding None values
    if hasattr(k8s_config, "model_dump"):
        k8s_config_dict = k8s_config.model_dump(exclude_none=True)
    elif isinstance(k8s_config, dict):
        # Handle if it's already a dict
        k8s_config_dict = {k: v for k, v in k8s_config.items() if v is not None}
    else:
        # Handle unexpected types gracefully
        logger.warning(f"Unexpected k8s_config type: {type(k8s_config)}, skipping")
        return spec

    if not k8s_config_dict:
        return spec

    # Map snake_case Python field names to camelCase Kubernetes field names
    # Note: startup_probe_grace_seconds is handled separately in _compile_startup_probe
    field_mapping = {
        "resources": "resources",
        "tolerations": "tolerations",
        "node_selector": "nodeSelector",
    }

    # Convert to camelCase for Kubernetes
    k8s_spec_updates = {}
    for python_field, k8s_field in field_mapping.items():
        if python_field in k8s_config_dict:
            k8s_spec_updates[k8s_field] = k8s_config_dict[python_field]

    # Apply to spec
    spec_dict = spec.model_dump(exclude_none=True)
    _deep_merge(spec_dict, k8s_spec_updates)

    return Spec(**spec_dict)


def _apply_override_config(spec: Spec, override_config: dict[str, Any]) -> Spec:
    """Apply override configuration to the NIMService spec."""
    logger.info("Applying override configuration to NIMService spec")

    spec_dict = spec.model_dump(exclude_none=True)
    _deep_merge(spec_dict, override_config)
    return Spec(**spec_dict)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _merge_default_labels(default_labels: Optional[dict[str, str]], base: dict[str, str]) -> dict[str, str]:
    """Merge default labels with base; base takes precedence on conflict."""
    out = dict(default_labels or {})
    out.update(base)
    return out


def _merge_default_annotations(default_annotations: Optional[dict[str, str]]) -> Optional[dict[str, str]]:
    """Return default annotations dict or None if empty."""
    if not default_annotations:
        return None
    return dict(default_annotations)
