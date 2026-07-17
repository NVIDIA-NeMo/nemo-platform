# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""E2E tests for the nemo-deployments plugin on Kubernetes.

The Kubernetes counterpart to ``test_nemo_deployments_docker.py``: it drives the
deployments plugin's own public API (DeploymentConfig / Deployment / Volume) and
asserts the reconcile controller turns those entities into real Kubernetes
workloads — a Deployment+Service for the long-lived nginx service, a Job for the
one-shot alpine workloads, and a PVC for the volume round-trip. The
backend-agnostic scenario cores are shared with the docker variant via
``e2e.deployments_helpers``; this module owns only the k8s-specific wiring.

What it proves — the deployments reconcile chain end to end, on Kubernetes::

    sdk._client POST /apis/deployments/v2/...   (config / volume / deployment)
      -> deployments reconcile controller
      -> k8s executor creates the Deployment+Service / Job / PVC
      -> Deployment.status converges (READY for the service, SUCCEEDED for jobs)

How it runs, and where:

- ``container_only``: this test only runs against an **external cluster**
  (``NMP_BASE_URL`` set) — the Kind CPU e2e CI job, whose Helm-deployed platform
  is configured with a nemo-deployments ``k8s`` executor (see
  ``e2e/k8s/values/kind.yaml``). It is skipped for the subprocess harness (local
  / plain e2e job), which has no k8s executor. This is the inverse of the docker
  module's ``subprocess_only``.
- The workloads use small public images (``alpine`` / ``nginx``) pulled by the
  kind nodes on demand, so — unlike the agents k8s test — this does not depend on
  a node-pre-pulled ``nmp-api`` image and carries no ``needs_nmp_api_image``
  marker. Pulling public ``docker.io/library/...`` images at cluster runtime is
  the same pattern the kind e2e job already relies on for postgres / busybox /
  cloud-provider-kind (there is no pull-through cache configured). The refs are
  env-overridable (see ``e2e.deployments_helpers``) for parity with the
  ``POSTGRES_IMAGE`` / ``BUSYBOX_IMAGE`` install knobs.
- The workloads land in the executor's namespace (the Helm release namespace,
  beside the platform), reachable in-cluster.
- Pod scheduling, PVC binding, and (internet) image pulls can take longer than
  the local docker path, so the scenario cores are given a wider timeout.
"""

from __future__ import annotations

import pytest
from nemo_platform import NeMoPlatform

from e2e.deployments_helpers import (
    run_job_deployment_lifecycle,
    run_service_deployment_lifecycle,
    run_volume_deployment_round_trip,
)

# Pod scheduling + PVC binding + image pulls in a fresh cluster take longer than
# a local docker container start.
_K8S_TIMEOUT_SECONDS = 420

pytestmark = [pytest.mark.container_only]


def test_k8s_service_deployment_reaches_ready(sdk: NeMoPlatform, workspace: str) -> None:
    """A restart_policy=Always nginx service reconciles to a k8s Deployment+Service (READY)."""
    run_service_deployment_lifecycle(
        sdk,
        workspace=workspace,
        backend_key="k8s",
        running_timeout_seconds=_K8S_TIMEOUT_SECONDS,
    )


def test_k8s_job_deployment_reaches_succeeded(sdk: NeMoPlatform, workspace: str) -> None:
    """A restart_policy=Never alpine job reconciles to a k8s Job that completes (SUCCEEDED)."""
    run_job_deployment_lifecycle(
        sdk,
        workspace=workspace,
        backend_key="k8s",
        running_timeout_seconds=_K8S_TIMEOUT_SECONDS,
    )


def test_k8s_volume_is_provisioned_mounted_and_readable(sdk: NeMoPlatform, workspace: str) -> None:
    """A PVC is provisioned, mounted into a Job, written to, and read back."""
    run_volume_deployment_round_trip(
        sdk,
        workspace=workspace,
        backend_key="k8s",
        running_timeout_seconds=_K8S_TIMEOUT_SECONDS,
    )
