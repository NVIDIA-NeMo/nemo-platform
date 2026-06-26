# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Direct-emission Kubernetes reconciler for the vLLM and generic engines.

Emits native Kubernetes objects (PVC / weight-puller Job / Deployment / Service)
directly -- there is no operator. Whether creation is staged depends on whether
the deployment has platform-managed weights (a fileset-backed model), NOT on the
engine:

* **Weighted** (vLLM always; generic when a fileset is present): a staged rollout.
  * P0 (``create``): emit the PVC + weight-puller Job. The serving Deployment +
    Service are intentionally NOT created yet so the controller can gate on weight
    readiness.
  * P3 (in ``get_status``, once the puller Job succeeds): delete the completed
    puller Job to release its ReadWriteOnce volume, then emit the serving
    Deployment + Service with ownerReferences so a later delete cascades.
* **Weightless** (generic with no fileset): the serving Deployment + Service are
  emitted immediately at ``create`` -- no PVC, no puller Job, no ``/model-store``
  mount; the container runs purely from its image.

The engine selects only the compiler (image/args/env), the pod uid/gid, and
whether the LoRA sidecar is wired; the staged-vs-immediate decision is driven by
weight presence. Inputs arrive pre-resolved on a :class:`ResolvedDeployment` (the
ServiceBackend does the SDK / entity-shaping work); this reconciler talks only to
Kubernetes.
"""

from logging import getLogger
from typing import Any, Optional

from kubernetes import client as k8s_client
from nemo_platform.types.inference.model_deployment import ModelDeployment
from nemo_platform.types.models.model_entity import ModelEntity
from nmp.common.config import get_platform_config
from nmp.core.models.app import ModelWeightsType, get_deployment_resource_name
from nmp.core.models.app.constants import MODEL_MANAGED_BY_LABEL, MODEL_MANAGED_BY_MODELS_CONTROLLER
from nmp.core.models.controllers.backends import generic_compiler, vllm_compiler
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate
from nmp.core.models.controllers.backends.engine import (
    ENGINE_GENERIC,
    ENGINE_VLLM,
    config_engine,
    resolve_health_path,
)
from nmp.core.models.controllers.backends.k8s_nim_operator import vllm_k8s_compiler
from nmp.core.models.controllers.backends.k8s_nim_operator.config import K8sNimOperatorConfig
from nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.base import (
    Reconciler,
    ResolvedDeployment,
)
from nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.resource_deleter import ResourceDeleter
from nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.status_projector import StatusProjector

logger = getLogger(__name__)


class K8sReconciler(Reconciler):
    """Reconciles a deployment by emitting native Kubernetes objects directly.

    Handles the ``vllm`` and ``generic`` engines, which share this direct-emission
    path. The rollout shape is chosen by **weight presence**, not engine:

    * Weighted (vLLM always; generic with a fileset) -- a staged rollout
      (PVC + weight-puller Job -> serving Deployment + Service), advanced one phase
      at a time as it is polled via :meth:`get_status`.
    * Weightless (generic with no fileset) -- the serving Deployment + Service are
      emitted immediately at create, with no PVC/puller and no ``/model-store``
      mount.

    The engine (:func:`config_engine`) selects only the compiler, uid/gid, and
    LoRA wiring (see :meth:`_serving_plan`). Holds its own typed API clients
    (CoreV1 / AppsV1 / BatchV1), composes a :class:`StatusProjector` (serving-pod
    readiness/diagnostics) and a :class:`ResourceDeleter`.
    """

    def __init__(
        self,
        k8s_client_: k8s_client.ApiClient,
        backend_config: K8sNimOperatorConfig,
        k8s_namespace: str,
        huggingface_model_puller: str,
        status: StatusProjector,
        deleter: ResourceDeleter,
    ) -> None:
        self._k8s_client = k8s_client_
        self._backend_config = backend_config
        self._k8s_namespace = k8s_namespace
        self._core_v1 = k8s_client.CoreV1Api(k8s_client_)
        self._apps_v1 = k8s_client.AppsV1Api(k8s_client_)
        self._batch_v1 = k8s_client.BatchV1Api(k8s_client_)
        self._huggingface_model_puller = huggingface_model_puller
        self._status = status
        self._deleter = deleter

    # ------------------------------------------------------------------
    # Reconciler interface
    # ------------------------------------------------------------------

    @staticmethod
    def _has_weights(resolved: ResolvedDeployment) -> bool:
        """True when the platform pulls weights for this deployment.

        vLLM always pulls weights (it serves a model from the Files service).
        Generic is weightless by default and only pulls weights when its config
        resolves to a Files-service model (a fileset-backed entity). This -- not
        the engine alone -- decides staged vs. immediate rollout.
        """
        if config_engine(resolved.config) == ENGINE_GENERIC:
            return resolved.weights_type == ModelWeightsType.FILES_SERVICE
        # vLLM (the only other engine routed here) is always weighted.
        return True

    async def create(self, resolved: ResolvedDeployment) -> DeploymentStatusUpdate:
        """Create the deployment's backend resources.

        Weighted deployments start at phase P0: emit the PVC + weight-puller Job
        (the Deployment + Service are created later by the status path once the Job
        completes -- controller-side weight-readiness gating). Weightless generic
        deployments have nothing to pull, so the serving Deployment + Service are
        emitted immediately.
        """
        if not self._has_weights(resolved):
            return self._create_serving_objects(resolved)

        deployment = resolved.deployment
        engine = config_engine(resolved.config)
        logger.info(
            f"Creating {engine} deployment: {deployment.workspace}/{deployment.name} "
            f"(version: {deployment.entity_version})"
        )
        try:
            resource_name = resolved.resource_name
            view = resolved.view
            model_repo, source_tag = self._model_source(resolved)
            disk_size = view.disk_size or self._backend_config.default_pvc_size
            if resolved.files_hf_url is None:
                raise ValueError(f"Cannot create {engine} deployment: Files HF endpoint was not resolved")

            user_id, group_id = self._pod_user(engine)
            pvc = vllm_k8s_compiler.compile_pvc(
                resource_name=resource_name,
                workspace=deployment.workspace,
                name=deployment.name,
                engine=engine,
                disk_size=disk_size,
                storage_class=self._backend_config.default_storage_class,
                model_source=source_tag,
                namespace=self._k8s_namespace,
                annotations=self._backend_config.default_annotations,
            )
            job = vllm_k8s_compiler.compile_puller_job(
                resource_name=resource_name,
                workspace=deployment.workspace,
                name=deployment.name,
                engine=engine,
                image=self._huggingface_model_puller,
                container_args=["download", model_repo, "--local-dir", vllm_k8s_compiler.MODEL_STORE_PATH],
                env={"HF_ENDPOINT": resolved.files_hf_url, "HF_TOKEN": "service:models"},
                gpu=view.gpu,
                namespace=self._k8s_namespace,
                service_account_name=self._backend_config.service_account_name,
                image_pull_secret=self._backend_config.huggingface_model_puller_image_pull_secret,
                user_id=user_id,
                group_id=group_id,
                model_source=source_tag,
            )

            self._create_or_skip(self._core_v1.create_namespaced_persistent_volume_claim, pvc, "PVC")
            self._create_or_skip(self._batch_v1.create_namespaced_job, job, "puller Job")

            return DeploymentStatusUpdate(
                status="PENDING",
                status_message="Provisioning model weights",
                host_url=self._status.host_url(resource_name),
            )
        except Exception as e:
            logger.error(f"Failed to create {engine} deployment for {deployment.workspace}/{deployment.name}: {e}")
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message=f"Failed to create deployment {deployment.workspace}/{deployment.name} due to a service backend error",
                error_details={"error": str(e), "error_type": type(e).__name__},
                host_url=None,
            )

    async def update(self, resolved: ResolvedDeployment) -> DeploymentStatusUpdate:
        """Update a deployment.

        For weighted deployments, weights are only re-pulled when the model source
        (name/revision) changes: a changed source deletes the objects (cascading
        PVC + Job) and drops back to the phased create; an unchanged source patches
        the serving Deployment + Service in place if they exist, else lets the
        status path create them at P3.

        Weightless generic deployments have no weight source, so update just
        patches (or creates) the serving Deployment + Service from the latest
        config.
        """
        deployment = resolved.deployment
        engine = config_engine(resolved.config)
        resource_name = resolved.resource_name
        logger.info(
            f"Updating {engine} deployment: {deployment.workspace}/{deployment.name} "
            f"(version: {deployment.entity_version})"
        )
        try:
            if not self._has_weights(resolved):
                # No weights => no PVC/puller; the serving objects are the whole
                # deployment. Re-apply them (patch in place if present).
                self._apply_serving_objects(resolved)
                return DeploymentStatusUpdate(
                    status="PENDING",
                    status_message="Update accepted",
                    host_url=self._status.host_url(resource_name),
                )

            _, source_tag = self._model_source(resolved)
            existing_source = self._existing_model_source(resource_name)
            if existing_source is not None and existing_source != source_tag:
                logger.info(
                    f"Model source changed ({existing_source} -> {source_tag}); re-pulling weights for {resource_name}"
                )
                self._delete_serving_resources(resource_name)
                return await self.create(resolved)

            # Unchanged source: patch the serving Deployment + Service in place if
            # present.
            if self._serving_deployment_exists(resource_name):
                self._apply_serving_objects(resolved)
                return DeploymentStatusUpdate(
                    status="PENDING",
                    status_message="Update accepted",
                    host_url=self._status.host_url(resource_name),
                )
            # No serving Deployment yet. If the puller Job is still present we're
            # mid-pull; the status path will emit the serving objects at P3, so the
            # update is a no-op (re-running create() here would re-assert the PVC +
            # Job needlessly). Only fall back to create() if the pull objects are
            # gone (genuine drift).
            if self._puller_job_exists(resource_name):
                return DeploymentStatusUpdate(
                    status="PENDING",
                    status_message="Update accepted",
                    host_url=self._status.host_url(resource_name),
                )
            return await self.create(resolved)
        except Exception as e:
            logger.error(f"Failed to update {engine} deployment for {deployment.workspace}/{deployment.name}: {e}")
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message=f"Failed to update deployment {deployment.workspace}/{deployment.name} due to a service backend error",
                error_details={"error": str(e), "error_type": type(e).__name__},
                host_url=None,
            )

    async def get_status(self, resolved: ResolvedDeployment) -> DeploymentStatusUpdate:
        """Project status, driving the phased lifecycle for weighted deployments.

        Weightless generic deployments have no puller phase: the Deployment is
        created at ``create`` time, so a 404 means it was deleted externally (LOST).

        Weighted deployments read the puller Job + (once created) the Deployment;
        when the Job has completed and the Deployment doesn't exist yet, this
        advances creation (phase P3) by emitting the Deployment + Service.
        """
        resource_name = resolved.resource_name

        # The serving Deployment is the source of truth once it exists.
        try:
            self._apps_v1.read_namespaced_deployment(name=resource_name, namespace=self._k8s_namespace)
            deployment_exists = True
        except k8s_client.exceptions.ApiException as e:
            if e.status != 404:
                raise
            deployment_exists = False

        if deployment_exists:
            return self._project_deployment_readiness(resource_name)

        # No Deployment. For weightless deployments it should have been created at
        # create-time, so its absence is external deletion -> LOST.
        if not self._has_weights(resolved):
            return DeploymentStatusUpdate(
                status="LOST",
                status_message="Serving Deployment not found; resources may have been deleted externally.",
                host_url=None,
            )

        # Weighted: we're still in the pull phase. Consult the puller Job.
        job_name = vllm_k8s_compiler.pull_job_name(resource_name)
        try:
            job = self._batch_v1.read_namespaced_job(name=job_name, namespace=self._k8s_namespace)
        except k8s_client.exceptions.ApiException as e:
            if e.status != 404:
                raise
            # Job absent. This is one of:
            # (a) the transient P3 window after we deleted a *succeeded* puller
            #     Job to release the RWO volume (the PVC still exists and holds the
            #     weights -> resume P3 by creating the serving objects); or
            # (b) genuine drift (PVC also gone -> LOST).
            if self._pvc_exists(resource_name):
                return self._create_serving_objects(resolved)
            return DeploymentStatusUpdate(
                status="LOST",
                status_message="Weight-puller Job and PVC not found; resources may have been deleted externally.",
                host_url=None,
            )

        job_status = job.status
        if job_status and job_status.failed and job_status.failed >= 1 and not (job_status.succeeded or 0):
            pod_name = self._find_job_pod_name(job_name)
            logs = self._status.fetch_pod_logs(pod_name) if pod_name else ""
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message="Model weight download failed.",
                error_details={"reason": "weight_pull_failed", "job": job_name, "error_stack": logs or None},
                host_url=None,
            )

        job_complete = bool(job_status and job_status.succeeded and job_status.succeeded >= 1)
        if not job_complete:
            return DeploymentStatusUpdate(status="PENDING", status_message="Downloading model weights", host_url=None)

        # Job complete and no Deployment yet: phase P3 -- create the serving objects.
        return self._create_serving_objects(resolved)

    async def delete(self, workspace: str, name: str) -> DeploymentStatusUpdate:
        """Delete the directly-emitted vLLM objects this reconciler owns.

        Returns an aggregated update; the ServiceBackend combines this with the
        other reconciler's delete result.
        """
        resource_name = get_deployment_resource_name(workspace, name)
        errors = self._delete_serving_resources(resource_name)
        if errors:
            summary = "; ".join(errors)
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message=f"Failed to fully delete deployment {workspace}/{name}: {summary}",
                error_details={"errors": errors},
                host_url=None,
            )
        return DeploymentStatusUpdate(
            status="DELETED",
            status_message="Deployment deletion initiated successfully",
            host_url=None,
        )

    async def list_managed_deployment_names(self) -> list[str]:
        """List ``workspace/name`` for directly-emitted Deployments we manage."""
        label_selector = f"{MODEL_MANAGED_BY_LABEL}={MODEL_MANAGED_BY_MODELS_CONTROLLER}"
        seen: set[str] = set()
        try:
            deployments = self._apps_v1.list_namespaced_deployment(
                namespace=self._k8s_namespace, label_selector=label_selector
            )
            for dep in deployments.items:
                labels = (dep.metadata.labels or {}) if dep.metadata else {}
                workspace = labels.get(vllm_k8s_compiler.DEPLOYMENT_WORKSPACE_LABEL)
                name = labels.get(vllm_k8s_compiler.DEPLOYMENT_NAME_LABEL)
                if workspace and name:
                    seen.add(f"{workspace}/{name}")
        except Exception as e:
            logger.warning(f"Failed to list vLLM Deployments for orphan reconciliation: {e}")
        return sorted(seen)

    # ------------------------------------------------------------------
    # vLLM-specific helpers (moved verbatim)
    # ------------------------------------------------------------------

    @staticmethod
    def _model_source(resolved: ResolvedDeployment) -> tuple[str, str]:
        """Resolve the puller's model repo (``namespace/name``) and a source tag.

        The source tag (``namespace/name@revision``) is stamped on the PVC + Job so
        the update path can detect a weight-source change and decide to re-pull.
        """
        namespace = resolved.model_namespace
        name = resolved.model_name
        revision = resolved.model_revision
        if not namespace or not name:
            raise ValueError(f"Cannot resolve model source for vLLM deployment: namespace='{namespace}', name='{name}'")
        model_repo = f"{namespace}/{name}"
        source_tag = f"{model_repo}@{revision}" if revision else model_repo
        return model_repo, source_tag

    def _serving_deployment_exists(self, resource_name: str) -> bool:
        """True if the serving Deployment for this resource already exists."""
        try:
            self._apps_v1.read_namespaced_deployment(name=resource_name, namespace=self._k8s_namespace)
            return True
        except k8s_client.exceptions.ApiException as e:
            if e.status == 404:
                return False
            raise

    def _pvc_exists(self, resource_name: str) -> bool:
        """True if the model-weights PVC for this deployment exists."""
        try:
            self._core_v1.read_namespaced_persistent_volume_claim(
                name=vllm_k8s_compiler.pvc_name(resource_name), namespace=self._k8s_namespace
            )
            return True
        except k8s_client.exceptions.ApiException as e:
            if e.status == 404:
                return False
            raise

    def _puller_job_exists(self, resource_name: str) -> bool:
        """True if the weight-puller Job for this deployment still exists.

        Used by the update path to detect the mid-pull window (PVC + Job created,
        serving Deployment not yet emitted) so an unchanged-source update is a
        no-op rather than re-running create().
        """
        try:
            self._batch_v1.read_namespaced_job(
                name=vllm_k8s_compiler.pull_job_name(resource_name), namespace=self._k8s_namespace
            )
            return True
        except k8s_client.exceptions.ApiException as e:
            if e.status == 404:
                return False
            raise

    def _create_or_skip(self, create_fn, body, kind: str) -> None:
        """Create a namespaced object, tolerating 409 Conflict (already exists)."""
        try:
            create_fn(namespace=self._k8s_namespace, body=body)
            logger.info(f"Created {kind} {body.metadata.name} in {self._k8s_namespace}")
        except k8s_client.exceptions.ApiException as e:
            if e.status == 409:
                logger.info(f"{kind} {body.metadata.name} already exists, skipping creation")
                return
            raise

    def _project_deployment_readiness(self, resource_name: str) -> DeploymentStatusUpdate:
        """Map the serving Deployment's status to a DeploymentStatusUpdate."""
        deployment = self._apps_v1.read_namespaced_deployment(name=resource_name, namespace=self._k8s_namespace)
        ready = (deployment.status.ready_replicas or 0) if deployment.status else 0
        if ready >= 1:
            return DeploymentStatusUpdate(
                status="READY", status_message="", host_url=self._status.host_url(resource_name)
            )
        # Not ready yet: reuse the pod-drilldown (crash loop, image pull, events).
        return self._status.pod_status_from_deployment(resource_name)

    # ------------------------------------------------------------------
    # Engine-parameterized serving objects (shared by vLLM + generic)
    # ------------------------------------------------------------------

    def _pod_user(self, engine: str) -> tuple[Optional[int], Optional[int]]:
        """Pod securityContext uid/gid for an engine.

        vLLM pins its image's user (2000/0); a generic container runs as its own
        image's user (unset), since we can't assume an arbitrary image tolerates a
        forced uid/gid.
        """
        if engine == ENGINE_VLLM:
            return self._backend_config.default_vllm_user_id, self._backend_config.default_vllm_group_id
        return None, None

    def _serving_spec(
        self,
        resolved: ResolvedDeployment,
        *,
        mount_model_store: bool,
    ) -> tuple[k8s_client.V1Deployment, k8s_client.V1Service]:
        """Compile the serving Deployment + Service for the deployment's engine.

        The engine selects the compiler (image/args/env), uid/gid, and LoRA wiring;
        ``mount_model_store`` controls whether the model-weights PVC is mounted
        (True for weighted deployments, False for a weightless generic container).
        """
        deployment = resolved.deployment
        view = resolved.view
        engine = config_engine(resolved.config)
        resource_name = resolved.resource_name
        health_path = resolve_health_path(engine, view)
        startup_grace = self._backend_config.default_startup_probe_grace_period_seconds or 600
        user_id, group_id = self._pod_user(engine)

        if engine == ENGINE_GENERIC:
            image_name, image_tag = generic_compiler.resolve_generic_image(view)
            args = generic_compiler.compile_generic_args(view)
            env = generic_compiler.compile_generic_env_vars(view)
            init_containers: Optional[list] = None
            sidecar_containers: Optional[list] = None
        else:
            image_name, image_tag = vllm_compiler.resolve_vllm_image(
                view, self._backend_config.default_vllm_image, self._backend_config.default_vllm_image_tag
            )
            args = vllm_compiler.compile_vllm_args(view, resolved.model_entity)
            env = vllm_compiler.compile_vllm_env_vars(view)
            init_containers, sidecar_containers = self._build_lora_containers(deployment, view, resolved.model_entity)

        dep_obj = vllm_k8s_compiler.compile_deployment(
            resource_name=resource_name,
            workspace=deployment.workspace,
            name=deployment.name,
            engine=engine,
            image=f"{image_name}:{image_tag}",
            args=args,
            health_path=health_path,
            env=env,
            gpu=view.gpu,
            namespace=self._k8s_namespace,
            service_account_name=self._backend_config.service_account_name,
            user_id=user_id,
            group_id=group_id,
            shared_memory_size_limit=self._backend_config.default_shared_memory_size_limit,
            startup_grace_seconds=startup_grace,
            init_containers=init_containers,
            sidecar_containers=sidecar_containers,
            mount_model_store=mount_model_store,
        )
        svc_obj = vllm_k8s_compiler.compile_service(
            resource_name=resource_name,
            workspace=deployment.workspace,
            name=deployment.name,
            engine=engine,
            namespace=self._k8s_namespace,
        )
        return dep_obj, svc_obj

    def _create_serving_objects(self, resolved: ResolvedDeployment) -> DeploymentStatusUpdate:
        """Create the serving Deployment + Service for an engine.

        For weighted deployments this is phase P3: the completed puller Job is
        deleted first so its pod releases the ReadWriteOnce PVC's volume attachment
        (a completed pod keeps the volume attached to its node, which would
        otherwise block the server pod with a Multi-Attach error if it scheduled
        onto a different node). For a weightless generic deployment there is no
        Job/PVC, so this runs straight through.

        Sets ownerReferences (PVC + Service -> Deployment) so deleting the
        Deployment cascades the rest.
        """
        resource_name = resolved.resource_name
        has_weights = self._has_weights(resolved)

        if has_weights:
            # Release the RWO volume from the completed puller before the server
            # needs it. Idempotent: a missing Job/pod counts as released.
            if not self._delete_puller_job(resource_name):
                return DeploymentStatusUpdate(
                    status="PENDING",
                    status_message="Releasing model weights volume",
                    host_url=self._status.host_url(resource_name),
                )

        dep_obj, svc_obj = self._serving_spec(resolved, mount_model_store=has_weights)

        try:
            created_dep = self._apps_v1.create_namespaced_deployment(namespace=self._k8s_namespace, body=dep_obj)
            logger.info(f"Created Deployment {resource_name} in {self._k8s_namespace}")
        except k8s_client.exceptions.ApiException as e:
            if e.status != 409:
                raise
            created_dep = self._apps_v1.read_namespaced_deployment(name=resource_name, namespace=self._k8s_namespace)

        # Owner reference -> Deployment, so PVC/Service cascade on delete.
        owner_ref = k8s_client.V1OwnerReference(
            api_version="apps/v1",
            kind="Deployment",
            name=created_dep.metadata.name,
            uid=created_dep.metadata.uid,
            controller=True,
            block_owner_deletion=True,
        )
        svc_obj.metadata.owner_references = [owner_ref]
        self._create_or_skip(self._core_v1.create_namespaced_service, svc_obj, "Service")
        if has_weights:
            self._set_owner_reference_on_pvc(resource_name, owner_ref)

        return DeploymentStatusUpdate(status="PENDING", status_message="Starting server", host_url=None)

    def _apply_serving_objects(self, resolved: ResolvedDeployment) -> None:
        """Re-apply the serving Deployment + Service for an update.

        Patches the Deployment and Service when they already exist (so changed
        image/args/env/health/gpu/labels actually take effect), and creates them
        when they don't. Used by the update path; the PVC (if any) is unaffected.
        """
        resource_name = resolved.resource_name
        has_weights = self._has_weights(resolved)
        dep_obj, svc_obj = self._serving_spec(resolved, mount_model_store=has_weights)

        if self._serving_deployment_exists(resource_name):
            self._apps_v1.patch_namespaced_deployment(name=resource_name, namespace=self._k8s_namespace, body=dep_obj)
            logger.info(f"Patched Deployment {resource_name} in {self._k8s_namespace}")
            try:
                self._core_v1.patch_namespaced_service(name=resource_name, namespace=self._k8s_namespace, body=svc_obj)
            except k8s_client.exceptions.ApiException as e:
                if e.status != 404:
                    raise
                self._core_v1.create_namespaced_service(namespace=self._k8s_namespace, body=svc_obj)
            return

        # Deployment absent: create both (idempotent on Service).
        self._apps_v1.create_namespaced_deployment(namespace=self._k8s_namespace, body=dep_obj)
        self._create_or_skip(self._core_v1.create_namespaced_service, svc_obj, "Service")

    def _delete_puller_job(self, resource_name: str) -> bool:
        """Delete the puller Job and confirm its pod is gone (releases RWO volume).

        Deletes the Job with foreground/background propagation so its pod is
        removed, freeing the volume attachment for the server pod. Returns True
        once no puller pod remains; False if a pod is still terminating (caller
        should retry on the next poll). Idempotent: a missing Job/pod counts as
        released.
        """
        job_name = vllm_k8s_compiler.pull_job_name(resource_name)
        try:
            self._batch_v1.delete_namespaced_job(
                name=job_name,
                namespace=self._k8s_namespace,
                propagation_policy="Background",
            )
            logger.info(f"Deleted puller Job {job_name} to release the model-weights volume")
        except k8s_client.exceptions.ApiException as e:
            if e.status != 404:
                raise

        # The volume stays attached until the pod object is gone, so confirm.
        try:
            pods = self._core_v1.list_namespaced_pod(
                namespace=self._k8s_namespace, label_selector=f"job-name={job_name}"
            )
        except Exception:
            return True
        return len(pods.items) == 0

    def _build_lora_containers(
        self, deployment: ModelDeployment, view: Any, model_entity: Optional[ModelEntity]
    ) -> tuple[Optional[list], Optional[list]]:
        """Build the LoRA init container + adapter sidecar for a vLLM Deployment.

        Returns ``(init_containers, sidecar_containers)``; both ``None`` when LoRA
        is not enabled.

        - The init container pre-creates ``/scratch/loras`` (vLLM's filesystem
          resolver validates the dir exists at startup).
        - The sidecar runs the engine-agnostic ``nmp-api`` adapters controller,
          pointed at the same dir, rewriting each adapter's base-model name to the
          served model path (``VLLM_LORA_BASE_MODEL_OVERRIDE=/model-store``).
        """
        if not view.lora_enabled:
            return None, None

        lora_dir = vllm_compiler.VLLM_LORA_CACHE_DIR
        platform_config = get_platform_config()
        sidecar_image = f"{platform_config.image_registry}/nmp-api:{platform_config.image_tag}"

        init_container = k8s_client.V1Container(
            name="lora-cache-init",
            image=f"{self._backend_config.busybox_image}:{self._backend_config.busybox_image_tag}",
            command=["sh", "-c", f"mkdir -p {lora_dir} && chmod -R 777 {lora_dir}"],
            volume_mounts=[k8s_client.V1VolumeMount(name="scratch", mount_path=vllm_k8s_compiler.SCRATCH_PATH)],
        )

        sidecar_env = {
            "NIM_PEFT_SOURCE": lora_dir,
            "NIM_PEFT_REFRESH_INTERVAL": str(self._backend_config.peft_refresh_interval),
            "VLLM_LORA_BASE_MODEL_OVERRIDE": vllm_compiler.MODEL_STORE_PATH,
            "NMP_MODEL_ENTITY_WORKSPACE": deployment.workspace,
            "NMP_MODEL_ENTITY_NAME": deployment.name,
        }
        if model_entity is not None:
            sidecar_env["NMP_MODEL_ENTITY_WORKSPACE"] = model_entity.workspace
            sidecar_env["NMP_MODEL_ENTITY_NAME"] = model_entity.name
        sidecar_env.update(platform_config.to_shared_envvars())

        sidecar = k8s_client.V1Container(
            name="lora-sidecar",
            image=sidecar_image,
            image_pull_policy="IfNotPresent",
            command=["nemo", "services", "run", "--sidecars", "adapters"],
            env=[k8s_client.V1EnvVar(name=k, value=str(v)) for k, v in sidecar_env.items()],
            volume_mounts=[
                k8s_client.V1VolumeMount(
                    name="model-store", mount_path=vllm_k8s_compiler.MODEL_STORE_PATH, read_only=True
                ),
                k8s_client.V1VolumeMount(name="scratch", mount_path=vllm_k8s_compiler.SCRATCH_PATH),
            ],
        )
        # NOTE: the sidecar image comes from the platform registry, but
        # imagePullSecrets are pod-level (not per-container), so we don't set them
        # on the sidecar here. The pod relies on the models ServiceAccount's pull
        # secret, which is applied at the chart level.
        return [init_container], [sidecar]

    def _set_owner_reference_on_pvc(self, resource_name: str, owner_ref: k8s_client.V1OwnerReference) -> None:
        """Patch the PVC to be owned by the Deployment (best-effort).

        The puller Job is deleted before the Deployment is created (to release the
        RWO volume), so only the PVC needs an ownerRef here; the Service gets its
        ownerRef at create time.
        """
        patch = {"metadata": {"ownerReferences": [self._k8s_client.sanitize_for_serialization(owner_ref)]}}
        try:
            self._core_v1.patch_namespaced_persistent_volume_claim(
                name=vllm_k8s_compiler.pvc_name(resource_name), namespace=self._k8s_namespace, body=patch
            )
        except Exception as e:
            logger.warning(f"Failed to set ownerReference on PVC for {resource_name}: {e}")

    def _find_job_pod_name(self, job_name: str) -> str | None:
        """Find the most recent pod for a Job (best-effort, for failure logs)."""
        try:
            pods = self._core_v1.list_namespaced_pod(
                namespace=self._k8s_namespace, label_selector=f"job-name={job_name}"
            )
            if not pods.items:
                return None
            return max(pods.items, key=lambda p: p.metadata.creation_timestamp).metadata.name
        except Exception:
            return None

    def _existing_model_source(self, resource_name: str) -> str | None:
        """Read the model-source annotation off the existing puller Job, if any."""
        try:
            job = self._batch_v1.read_namespaced_job(
                name=vllm_k8s_compiler.pull_job_name(resource_name), namespace=self._k8s_namespace
            )
        except k8s_client.exceptions.ApiException:
            return None
        annotations = (job.metadata.annotations or {}) if job.metadata else {}
        return annotations.get(vllm_k8s_compiler.MODEL_SOURCE_ANNOTATION)

    def _delete_serving_resources(self, resource_name: str) -> list[str]:
        """Delete the directly-emitted objects by name (idempotent).

        Covers the Deployment + Service plus the (optional) puller Job + PVC; a
        weightless generic deployment simply has no Job/PVC, so those deletes are
        404-tolerant no-ops. Returns concise error strings for any real (non-404)
        failures; empty when everything was deleted or already absent.
        """
        deleters = [
            (self._apps_v1.delete_namespaced_deployment, "Deployment", resource_name),
            (self._core_v1.delete_namespaced_service, "Service", resource_name),
            (self._batch_v1.delete_namespaced_job, "puller Job", vllm_k8s_compiler.pull_job_name(resource_name)),
            (self._core_v1.delete_namespaced_persistent_volume_claim, "PVC", vllm_k8s_compiler.pvc_name(resource_name)),
        ]
        errors: list[str] = []
        for delete_fn, kind, obj_name in deleters:
            err = self._deleter.delete_one(delete_fn, kind, obj_name)
            if err:
                errors.append(err)
        return errors
