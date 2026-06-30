# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Idempotent, 404-tolerant Kubernetes object deletion.

Teardown deletes every resource type a deployment could own *by name* (no engine
detection), so it can self-heal partial-deletion states and is safe to call for
orphan reconciliation. :class:`ResourceDeleter` owns that single-object delete
semantics so both reconcilers can *compose* it rather than inherit it.
"""

from logging import getLogger
from typing import Optional

from kubernetes import client as k8s_client
from kubernetes.dynamic import exceptions as k8s_dynamic_exceptions

logger = getLogger(__name__)


class ResourceDeleter:
    """Deletes namespaced Kubernetes objects by name, tolerating "already gone"."""

    def __init__(self, k8s_namespace: str) -> None:
        self._k8s_namespace = k8s_namespace

    def delete_one(self, delete_fn, kind: str, obj_name: str) -> Optional[str]:
        """Delete a single namespaced object by name, tolerating "already gone".

        A 404 (object absent) is success. Any other failure is logged concisely
        (no stack trace) and returned as a short error string so the caller can
        aggregate and surface it (we must NOT mark a deployment DELETED if cluster
        resources may remain).
        """
        try:
            delete_fn(name=obj_name, namespace=self._k8s_namespace)
            logger.info(f"Deleted {kind} {self._k8s_namespace}/{obj_name}")
            return None
        except (k8s_client.exceptions.ApiException, k8s_dynamic_exceptions.NotFoundError) as e:
            # NotFound (typed status 404 or dynamic NotFoundError) -> already gone.
            if isinstance(e, k8s_dynamic_exceptions.NotFoundError) or getattr(e, "status", None) == 404:
                logger.debug(f"{kind} {obj_name} not found, already deleted")
                return None
            return self._classify_delete_error(e, kind, obj_name)
        except Exception as e:
            # Any other failure (forbidden, connection/transport error, dynamic API
            # error, ...) must be classified and returned -- never raised -- so the
            # caller's per-resource delete loop continues and aggregates failures
            # rather than aborting cleanup partway and risking a false DELETED.
            return self._classify_delete_error(e, kind, obj_name)

    @staticmethod
    def _classify_delete_error(e: Exception, kind: str, obj_name: str) -> str:
        """Concise, human-readable delete failure (no stack trace) for aggregation."""
        status = getattr(e, "status", None)
        is_forbidden = status == 403 or isinstance(e, k8s_dynamic_exceptions.ForbiddenError)
        if is_forbidden:
            # With the models ServiceAccount RBAC in place this should not happen;
            # if it does, the SA is missing delete on this resource type.
            msg = f"forbidden to delete {kind} {obj_name} (ServiceAccount lacks RBAC)"
            logger.error(msg)
            return msg
        msg = f"error deleting {kind} {obj_name}: {status or type(e).__name__}"
        logger.warning(msg)
        return msg
