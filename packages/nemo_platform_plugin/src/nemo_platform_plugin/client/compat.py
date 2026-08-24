# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backward-compatible method aliases for the old Stainless SDK interface.

Adds old SDK method names (retrieve, create, list, delete, etc.) as aliases
on the new typed HTTP clients.  Exists so the spine flip (sdk_factory returns
NemoClient instead of NeMoPlatform) can happen before all consumers are
migrated to the new method names.

Each wrapper translates the old calling convention (positional path params,
individual body fields) to the new one (keyword-only params, body models).

Temporary: removed after all consumers are migrated.
"""

from __future__ import annotations

from typing import Any

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient
from nemo_platform_plugin.client.method import method

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SDK_KWARGS = frozenset({"extra_headers", "extra_query", "extra_body", "timeout", "max_retries"})


def _build_model(model_cls: type, kwargs: dict[str, Any]) -> Any:
    """Construct a Pydantic model from kwargs, keeping only valid fields."""
    valid = set(model_cls.model_fields.keys())
    return model_cls(**{k: v for k, v in kwargs.items() if k in valid and v is not None})


def _clean(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Strip old-SDK transport kwargs that typed clients don't accept."""
    return {k: v for k, v in kwargs.items() if k not in _SDK_KWARGS}


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------

from nemo_platform_plugin.workspaces import endpoints as _ws_ep
from nemo_platform_plugin.workspaces.types import (
    CreateWorkspaceMemberRequest as _CWM,
)
from nemo_platform_plugin.workspaces.types import (
    CreateWorkspaceRequest as _CWS,
)
from nemo_platform_plugin.workspaces.types import (
    ListWorkspacesQueryParams as _LWSQP,
)
from nemo_platform_plugin.workspaces.types import (
    UpdateWorkspaceMemberRequest as _UWM,
)
from nemo_platform_plugin.workspaces.types import (
    UpdateWorkspaceRequest as _UWS,
)


def _ws_retrieve(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _ws_ep.get_workspace(workspace=workspace, name=name, **_clean(kw))


def _ws_create(*, workspace: str | None = None, body: Any = None, exist_ok: bool = False, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_CWS, kw)
    return _ws_ep.create_workspace(workspace=workspace, body=body, exist_ok=exist_ok)


def _ws_update(name: str, *, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_UWS, kw)
    return _ws_ep.update_workspace(workspace=workspace, name=name, body=body)


def _ws_delete(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _ws_ep.delete_workspace(workspace=workspace, name=name)


def _ws_list(*, workspace: str | None = None, query_params: Any = None, **kw: Any) -> Any:
    if query_params is None:
        query_params = _build_model(_LWSQP, kw)
    return _ws_ep.list_workspaces(workspace=workspace, query_params=query_params)


def _wsm_create(*, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_CWM, kw)
    return _ws_ep.create_workspace_member(workspace=workspace, body=body)


def _wsm_update(principal_id: str, *, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_UWM, kw)
    return _ws_ep.update_workspace_member(workspace=workspace, principal_id=principal_id, body=body)


def _wsm_delete(principal_id: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _ws_ep.delete_workspace_member(workspace=workspace, principal_id=principal_id)


def _wsm_list(*, workspace: str | None = None, **kw: Any) -> Any:
    return _ws_ep.list_workspace_members(workspace=workspace)


class _WorkspaceMembersCompatMixin:
    create = method(_wsm_create)
    list = method(_wsm_list)
    update = method(_wsm_update)
    delete = method(_wsm_delete)


class _WorkspaceMembersCompat(_WorkspaceMembersCompatMixin, NemoClient):
    pass


class _AsyncWorkspaceMembersCompat(_WorkspaceMembersCompatMixin, AsyncNemoClient):
    pass


class WorkspacesCompat:
    retrieve = method(_ws_retrieve)
    create = method(_ws_create)
    update = method(_ws_update)
    delete = method(_ws_delete)
    list = method(_ws_list)

    @property
    def members(self) -> Any:
        if isinstance(self, AsyncNemoClient):
            return _AsyncWorkspaceMembersCompat.from_client(self)
        return _WorkspaceMembersCompat.from_client(self)


# ---------------------------------------------------------------------------
# Guardrail
# ---------------------------------------------------------------------------

from nemo_platform_plugin.guardrail import endpoints as _gr_ep
from nemo_platform_plugin.guardrail.types import (
    CreateGuardrailConfigRequest as _CGRC,
)
from nemo_platform_plugin.guardrail.types import (
    GuardrailCheckRequest as _GCR,
)
from nemo_platform_plugin.guardrail.types import (
    ListGuardrailConfigsQueryParams as _LGCQP,
)
from nemo_platform_plugin.guardrail.types import (
    UpdateGuardrailConfigRequest as _UGRC,
)


def _gr_check(*, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_GCR, kw)
    return _gr_ep.check_guardrail(workspace=workspace, body=body)


def _grc_retrieve(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _gr_ep.get_guardrail_config(workspace=workspace, name=name)


def _grc_create(*, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_CGRC, kw)
    return _gr_ep.create_guardrail_config(workspace=workspace, body=body)


def _grc_update(name: str, *, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_UGRC, kw)
    return _gr_ep.update_guardrail_config(workspace=workspace, name=name, body=body)


def _grc_delete(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _gr_ep.delete_guardrail_config(workspace=workspace, name=name)


def _grc_list(*, workspace: str | None = None, query_params: Any = None, **kw: Any) -> Any:
    if query_params is None:
        query_params = _build_model(_LGCQP, kw)
    return _gr_ep.list_guardrail_configs(workspace=workspace, query_params=query_params)


class _GuardrailConfigsCompatMixin:
    retrieve = method(_grc_retrieve)
    create = method(_grc_create)
    update = method(_grc_update)
    delete = method(_grc_delete)
    list = method(_grc_list)


class _GuardrailConfigsCompat(_GuardrailConfigsCompatMixin, NemoClient):
    pass


class _AsyncGuardrailConfigsCompat(_GuardrailConfigsCompatMixin, AsyncNemoClient):
    pass


class GuardrailCompat:
    check = method(_gr_check)

    @property
    def configs(self) -> Any:
        if isinstance(self, AsyncNemoClient):
            return _AsyncGuardrailConfigsCompat.from_client(self)
        return _GuardrailConfigsCompat.from_client(self)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

from nemo_platform_plugin.projects import endpoints as _pj_ep
from nemo_platform_plugin.projects.types import (
    CreateProjectRequest as _CPJ,
)
from nemo_platform_plugin.projects.types import (
    ListProjectsQueryParams as _LPJQP,
)
from nemo_platform_plugin.projects.types import (
    UpdateProjectRequest as _UPJ,
)


def _pj_retrieve(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _pj_ep.get_project(workspace=workspace, name=name)


def _pj_create(*, workspace: str | None = None, body: Any = None, exist_ok: bool = False, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_CPJ, kw)
    return _pj_ep.create_project(workspace=workspace, body=body, exist_ok=exist_ok)


def _pj_update(name: str, *, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_UPJ, kw)
    return _pj_ep.update_project(workspace=workspace, name=name, body=body)


def _pj_delete(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _pj_ep.delete_project(workspace=workspace, name=name)


def _pj_list(*, workspace: str | None = None, query_params: Any = None, **kw: Any) -> Any:
    if query_params is None:
        query_params = _build_model(_LPJQP, kw)
    return _pj_ep.list_projects(workspace=workspace, query_params=query_params)


class ProjectsCompat:
    retrieve = method(_pj_retrieve)
    create = method(_pj_create)
    update = method(_pj_update)
    delete = method(_pj_delete)
    list = method(_pj_list)


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

from nemo_platform_plugin.agents import endpoints as _ag_ep
from nemo_platform_plugin.agents.types import (
    CreateAgentDeploymentRequest as _CAD,
)
from nemo_platform_plugin.agents.types import (
    CreateAgentRequest as _CAG,
)
from nemo_platform_plugin.agents.types import (
    InvokeAgentRequest as _IAG,
)
from nemo_platform_plugin.agents.types import (
    ListAgentsQueryParams as _LAGQP,
)
from nemo_platform_plugin.agents.types import (
    ListDeploymentsQueryParams as _LDGQP,
)


def _ag_get(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _ag_ep.get_agent(workspace=workspace, name=name)


def _ag_create(*, workspace: str | None = None, body: Any = None, exist_ok: bool = False, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_CAG, kw)
    return _ag_ep.create_agent(workspace=workspace, body=body, exist_ok=exist_ok)


def _ag_delete(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _ag_ep.delete_agent(workspace=workspace, name=name)


def _ag_list(*, workspace: str | None = None, query_params: Any = None, **kw: Any) -> Any:
    if query_params is None:
        query_params = _build_model(_LAGQP, kw)
    return _ag_ep.list_agents(workspace=workspace, query_params=query_params)


def _ag_invoke(name: str, *, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_IAG, kw)
    return _ag_ep.invoke_agent(workspace=workspace, name=name, body=body)


def _agd_get(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _ag_ep.get_deployment(workspace=workspace, name=name)


def _agd_create(*, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_CAD, kw)
    return _ag_ep.create_deployment(workspace=workspace, body=body)


def _agd_delete(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _ag_ep.delete_deployment(workspace=workspace, name=name)


def _agd_list(*, workspace: str | None = None, query_params: Any = None, **kw: Any) -> Any:
    if query_params is None:
        query_params = _build_model(_LDGQP, kw)
    return _ag_ep.list_deployments(workspace=workspace, query_params=query_params)


class _AgentDeploymentsCompatMixin:
    get = method(_agd_get)
    create = method(_agd_create)
    delete = method(_agd_delete)
    list = method(_agd_list)


class _AgentDeploymentsCompat(_AgentDeploymentsCompatMixin, NemoClient):
    pass


class _AsyncAgentDeploymentsCompat(_AgentDeploymentsCompatMixin, AsyncNemoClient):
    pass


class AgentsCompat:
    get = method(_ag_get)
    create = method(_ag_create)
    delete = method(_ag_delete)
    list = method(_ag_list)
    invoke = method(_ag_invoke)

    @property
    def deployments(self) -> Any:
        if isinstance(self, AsyncNemoClient):
            return _AsyncAgentDeploymentsCompat.from_client(self)
        return _AgentDeploymentsCompat.from_client(self)


# ---------------------------------------------------------------------------
# Auditor
# ---------------------------------------------------------------------------

from nemo_platform_plugin.auditor import endpoints as _au_ep
from nemo_platform_plugin.auditor.types import (
    CreateAuditConfigRequest as _CAUC,
)
from nemo_platform_plugin.auditor.types import (
    CreateAuditTargetRequest as _CAUT,
)
from nemo_platform_plugin.auditor.types import (
    ListAuditConfigsQueryParams as _LAUCQP,
)
from nemo_platform_plugin.auditor.types import (
    ListAuditJobsQueryParams as _LAUJQP,
)
from nemo_platform_plugin.auditor.types import (
    ListAuditTargetsQueryParams as _LAUTQP,
)
from nemo_platform_plugin.auditor.types import (
    SubmitAuditRequest as _SAU,
)
from nemo_platform_plugin.auditor.types import (
    UpdateAuditConfigRequest as _UAUC,
)
from nemo_platform_plugin.auditor.types import (
    UpdateAuditTargetRequest as _UAUT,
)


def _au_submit(*, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_SAU, kw)
    return _au_ep.submit_audit(workspace=workspace, body=body)


def _au_list_jobs(*, workspace: str | None = None, query_params: Any = None, **kw: Any) -> Any:
    if query_params is None:
        query_params = _build_model(_LAUJQP, kw)
    return _au_ep.list_audit_jobs(workspace=workspace, query_params=query_params)


def _auc_get(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _au_ep.get_audit_config(workspace=workspace, name=name)


def _auc_create(*, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_CAUC, kw)
    return _au_ep.create_audit_config(workspace=workspace, body=body)


def _auc_update(name: str, *, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_UAUC, kw)
    return _au_ep.update_audit_config(workspace=workspace, name=name, body=body)


def _auc_delete(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _au_ep.delete_audit_config(workspace=workspace, name=name)


def _auc_list(*, workspace: str | None = None, query_params: Any = None, **kw: Any) -> Any:
    if query_params is None:
        query_params = _build_model(_LAUCQP, kw)
    return _au_ep.list_audit_configs(workspace=workspace, query_params=query_params)


def _aut_get(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _au_ep.get_audit_target(workspace=workspace, name=name)


def _aut_create(*, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_CAUT, kw)
    return _au_ep.create_audit_target(workspace=workspace, body=body)


def _aut_update(name: str, *, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_UAUT, kw)
    return _au_ep.update_audit_target(workspace=workspace, name=name, body=body)


def _aut_delete(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _au_ep.delete_audit_target(workspace=workspace, name=name)


def _aut_list(*, workspace: str | None = None, query_params: Any = None, **kw: Any) -> Any:
    if query_params is None:
        query_params = _build_model(_LAUTQP, kw)
    return _au_ep.list_audit_targets(workspace=workspace, query_params=query_params)


class _AuditConfigsCompatMixin:
    get = method(_auc_get)
    create = method(_auc_create)
    update = method(_auc_update)
    delete = method(_auc_delete)
    list = method(_auc_list)


class _AuditConfigsCompat(_AuditConfigsCompatMixin, NemoClient):
    pass


class _AsyncAuditConfigsCompat(_AuditConfigsCompatMixin, AsyncNemoClient):
    pass


class _AuditTargetsCompatMixin:
    get = method(_aut_get)
    create = method(_aut_create)
    update = method(_aut_update)
    delete = method(_aut_delete)
    list = method(_aut_list)


class _AuditTargetsCompat(_AuditTargetsCompatMixin, NemoClient):
    pass


class _AsyncAuditTargetsCompat(_AuditTargetsCompatMixin, AsyncNemoClient):
    pass


class AuditorCompat:
    submit = method(_au_submit)
    list_jobs = method(_au_list_jobs)

    @property
    def configs(self) -> Any:
        if isinstance(self, AsyncNemoClient):
            return _AsyncAuditConfigsCompat.from_client(self)
        return _AuditConfigsCompat.from_client(self)

    @property
    def targets(self) -> Any:
        if isinstance(self, AsyncNemoClient):
            return _AsyncAuditTargetsCompat.from_client(self)
        return _AuditTargetsCompat.from_client(self)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

from nemo_platform_plugin.evaluator import endpoints as _ev_ep
from nemo_platform_plugin.evaluator.types import (
    CreateMetricRequest as _CMT,
)
from nemo_platform_plugin.evaluator.types import (
    ListEvalResultsQueryParams as _LERQP,
)
from nemo_platform_plugin.evaluator.types import (
    ListMetricsQueryParams as _LMQP,
)
from nemo_platform_plugin.evaluator.types import (
    SubmitEvaluateJobRequest as _SEVJ,
)


def _ev_submit(*, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_SEVJ, kw)
    return _ev_ep.submit_evaluate_job(workspace=workspace, body=body)


def _evr_retrieve(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _ev_ep.get_eval_result(workspace=workspace, name=name)


def _evr_list(*, workspace: str | None = None, query_params: Any = None, **kw: Any) -> Any:
    if query_params is None:
        query_params = _build_model(_LERQP, kw)
    return _ev_ep.list_eval_results(workspace=workspace, query_params=query_params)


def _evm_retrieve(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _ev_ep.get_metric(workspace=workspace, name=name)


def _evm_create(*, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_CMT, kw)
    return _ev_ep.create_metric(workspace=workspace, body=body)


def _evm_delete(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _ev_ep.delete_metric(workspace=workspace, name=name)


def _evm_list(*, workspace: str | None = None, query_params: Any = None, **kw: Any) -> Any:
    if query_params is None:
        query_params = _build_model(_LMQP, kw)
    return _ev_ep.list_metrics(workspace=workspace, query_params=query_params)


class _EvalResultsCompatMixin:
    retrieve = method(_evr_retrieve)
    list = method(_evr_list)


class _EvalResultsCompat(_EvalResultsCompatMixin, NemoClient):
    pass


class _AsyncEvalResultsCompat(_EvalResultsCompatMixin, AsyncNemoClient):
    pass


class _MetricsCompatMixin:
    retrieve = method(_evm_retrieve)
    create = method(_evm_create)
    delete = method(_evm_delete)
    list = method(_evm_list)


class _MetricsCompat(_MetricsCompatMixin, NemoClient):
    pass


class _AsyncMetricsCompat(_MetricsCompatMixin, AsyncNemoClient):
    pass


class EvaluatorCompat:
    submit = method(_ev_submit)

    @property
    def eval_results(self) -> Any:
        if isinstance(self, AsyncNemoClient):
            return _AsyncEvalResultsCompat.from_client(self)
        return _EvalResultsCompat.from_client(self)

    @property
    def metrics(self) -> Any:
        if isinstance(self, AsyncNemoClient):
            return _AsyncMetricsCompat.from_client(self)
        return _MetricsCompat.from_client(self)


# ---------------------------------------------------------------------------
# Data Designer
# ---------------------------------------------------------------------------

from nemo_platform_plugin.data_designer import endpoints as _dd_ep
from nemo_platform_plugin.data_designer.types import DataDesignerJobRequest as _DDJ


def _dd_create(*, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_DDJ, kw)
    return _dd_ep.create_job(workspace=workspace, body=body)


class DataDesignerCompat:
    create = method(_dd_create)


# ---------------------------------------------------------------------------
# Secrets (existing typed client)
# ---------------------------------------------------------------------------

from nemo_platform_plugin.secrets import endpoints as _sec_ep
from nemo_platform_plugin.secrets.types import (
    ListSecretsQueryParams as _LSECQP,
)
from nemo_platform_plugin.secrets.types import (
    PlatformSecretCreateRequest as _CSEC,
)


def _sec_retrieve(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _sec_ep.get_secret(workspace=workspace, name=name)


def _sec_create(*, workspace: str | None = None, body: Any = None, exist_ok: bool = False, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_CSEC, kw)
    return _sec_ep.create_secret(workspace=workspace, body=body, exist_ok=exist_ok)


def _sec_delete(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _sec_ep.delete_secret(workspace=workspace, name=name)


def _sec_list(*, workspace: str | None = None, query_params: Any = None, **kw: Any) -> Any:
    if query_params is None:
        query_params = _build_model(_LSECQP, kw)
    return _sec_ep.list_secrets(workspace=workspace, query_params=query_params)


def _sec_access(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _sec_ep.access_secret(workspace=workspace, name=name)


class SecretsCompat:
    retrieve = method(_sec_retrieve)
    create = method(_sec_create)
    delete = method(_sec_delete)
    list = method(_sec_list)
    access = method(_sec_access)


# ---------------------------------------------------------------------------
# Jobs (existing typed client)
# ---------------------------------------------------------------------------

from nemo_platform_plugin.jobs import endpoints as _job_ep
from nemo_platform_plugin.jobs.schemas import ListJobsQueryParams as _LJQP


def _job_retrieve(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _job_ep.get_job(workspace=workspace, name=name)


def _job_delete(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _job_ep.delete_job(workspace=workspace, name=name)


def _job_list(*, workspace: str | None = None, query_params: Any = None, **kw: Any) -> Any:
    if query_params is None:
        query_params = _build_model(_LJQP, kw)
    return _job_ep.list_jobs(workspace=workspace, query_params=query_params)


def _job_cancel(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _job_ep.cancel_job(workspace=workspace, name=name)


def _job_pause(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _job_ep.pause_job(workspace=workspace, name=name)


def _job_resume(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _job_ep.resume_job(workspace=workspace, name=name)


def _job_get_status(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _job_ep.get_job_status(workspace=workspace, name=name)


def _job_get_logs(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _job_ep.list_job_logs(workspace=workspace, name=name)


class JobsCompat:
    retrieve = method(_job_retrieve)
    delete = method(_job_delete)
    list = method(_job_list)
    cancel = method(_job_cancel)
    pause = method(_job_pause)
    resume = method(_job_resume)
    get_status = method(_job_get_status)
    get_logs = method(_job_get_logs)


# ---------------------------------------------------------------------------
# Iron Swarm gap methods (delegate to plugin SDK resource)
# ---------------------------------------------------------------------------


class IronSwarmCompat:
    """Compat for plugin-level methods not on IronSwarmClient."""

    def run(self, **kw: Any) -> Any:
        from nemo_iron_swarm_plugin.sdk import IronSwarmPluginResource

        return IronSwarmPluginResource(self).run(**kw)

    def synth_benign(self, **kw: Any) -> Any:
        from nemo_iron_swarm_plugin.sdk import IronSwarmPluginResource

        return IronSwarmPluginResource(self).synth_benign(**kw)

    def sanity_check(self, **kw: Any) -> Any:
        from nemo_iron_swarm_plugin.sdk import IronSwarmPluginResource

        return IronSwarmPluginResource(self).sanity_check(**kw)


# ---------------------------------------------------------------------------
# Files (existing typed client)
# ---------------------------------------------------------------------------

from nemo_platform_plugin.files import endpoints as _f_ep


def _f_upload_content(
    *, content: Any, remote_path: str, fileset: str | None = None, workspace: str | None = None, **kw: Any
) -> Any:
    return _f_ep.upload_file(workspace=workspace, name=fileset, path=remote_path, content=content)


def _f_download_content(
    *, remote_path: str, fileset: str | None = None, workspace: str | None = None, **kw: Any
) -> Any:
    return _f_ep.download_file(workspace=workspace, name=fileset, path=remote_path)


def _f_upload(*, name: str, path: str, content: Any, workspace: str | None = None, **kw: Any) -> Any:
    return _f_ep.upload_file(workspace=workspace, name=name, path=path, content=content)


def _f_download(*, name: str, path: str, workspace: str | None = None, **kw: Any) -> Any:
    return _f_ep.download_file(workspace=workspace, name=name, path=path)


def _f_delete(*, name: str, path: str, workspace: str | None = None, **kw: Any) -> Any:
    return _f_ep.delete_file(workspace=workspace, name=name, path=path)


def _f_list(*, name: str, workspace: str | None = None, **kw: Any) -> Any:
    return _f_ep.list_files(workspace=workspace, name=name)


# Filesets sub-resource
def _ff_create(*, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    from nemo_platform_plugin.files.types import CreateFilesetRequest

    if body is None:
        body = _build_model(CreateFilesetRequest, kw)
    return _f_ep.create_fileset(workspace=workspace, body=body)


def _ff_retrieve(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _f_ep.get_fileset(workspace=workspace, name=name)


def _ff_update(name: str, *, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    from nemo_platform_plugin.files.types import UpdateFilesetRequest

    if body is None:
        body = _build_model(UpdateFilesetRequest, kw)
    return _f_ep.update_fileset(workspace=workspace, name=name, body=body)


def _ff_delete(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _f_ep.delete_fileset(workspace=workspace, name=name)


def _ff_list(*, workspace: str | None = None, **kw: Any) -> Any:
    from nemo_platform_plugin.files.types import ListFilesetsQueryParams

    return _f_ep.list_filesets(workspace=workspace, query_params=_build_model(ListFilesetsQueryParams, kw))


class _FilesetsCompatMixin:
    create = method(_ff_create)
    retrieve = method(_ff_retrieve)
    update = method(_ff_update)
    delete = method(_ff_delete)
    list = method(_ff_list)


class _FilesetsCompat(_FilesetsCompatMixin, NemoClient):
    pass


class _AsyncFilesetsCompat(_FilesetsCompatMixin, AsyncNemoClient):
    pass


class FilesCompat:
    upload_content = method(_f_upload_content)
    download_content = method(_f_download_content)
    upload = method(_f_upload)
    download = method(_f_download)
    delete = method(_f_delete)
    list = method(_f_list)

    @property
    def filesets(self) -> Any:
        if isinstance(self, AsyncNemoClient):
            return _AsyncFilesetsCompat.from_client(self)
        return _FilesetsCompat.from_client(self)


# ---------------------------------------------------------------------------
# Models (existing typed client)
# ---------------------------------------------------------------------------

from nemo_platform_plugin.models import endpoints as _m_ep
from nemo_platform_plugin.models.types import (
    CreateModelEntityRequest as _CME,
)
from nemo_platform_plugin.models.types import (
    ListModelsQueryParams as _LMQM,
)
from nemo_platform_plugin.models.types import (
    UpdateModelEntityRequest as _UME,
)


def _m_retrieve(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _m_ep.get_model(workspace=workspace, name=name)


def _m_create(*, workspace: str | None = None, body: Any = None, exist_ok: bool = False, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_CME, kw)
    return _m_ep.create_model(workspace=workspace, body=body, exist_ok=exist_ok)


def _m_update(name: str, *, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_UME, kw)
    return _m_ep.update_model(workspace=workspace, name=name, body=body)


def _m_delete(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _m_ep.delete_model(workspace=workspace, name=name)


def _m_list(*, workspace: str | None = None, query_params: Any = None, **kw: Any) -> Any:
    if query_params is None:
        query_params = _build_model(_LMQM, kw)
    return _m_ep.list_models(workspace=workspace, query_params=query_params)


class ModelsCompat:
    retrieve = method(_m_retrieve)
    create = method(_m_create)
    update = method(_m_update)
    delete = method(_m_delete)
    list = method(_m_list)


# ---------------------------------------------------------------------------
# Entities (existing typed client)
# ---------------------------------------------------------------------------

from nemo_platform_plugin.entities import endpoints as _ent_ep
from nemo_platform_plugin.entities.types import EntityCreateInput as _ECI


def _ent_create(entity_type: str, *, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_ECI, kw)
    return _ent_ep.create_entity(workspace=workspace, entity_type=entity_type, body=body)


def _ent_list(*, entity_type: str, workspace: str | None = None, **kw: Any) -> Any:
    from nemo_platform_plugin.entities.types import ListEntitiesQueryParams

    return _ent_ep.list_entities(
        workspace=workspace, entity_type=entity_type, query_params=_build_model(ListEntitiesQueryParams, kw)
    )


class EntitiesCompat:
    create = method(_ent_create)
    list = method(_ent_list)


# ---------------------------------------------------------------------------
# Inference sub-resource compat (providers, deployments, deployment_configs)
# ---------------------------------------------------------------------------


def _inf_prov_retrieve(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _m_ep.get_provider(workspace=workspace, name=name)


def _inf_prov_create(*, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    from nemo_platform_plugin.models.types import CreateModelProviderRequest

    if body is None:
        body = _build_model(CreateModelProviderRequest, kw)
    return _m_ep.create_provider(workspace=workspace, body=body)


def _inf_prov_update(name: str, *, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    from nemo_platform_plugin.models.types import UpsertModelProviderRequest

    if body is None:
        body = _build_model(UpsertModelProviderRequest, kw)
    return _m_ep.upsert_provider(workspace=workspace, name=name, body=body)


def _inf_prov_delete(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _m_ep.delete_provider(workspace=workspace, name=name)


def _inf_prov_list(*, workspace: str | None = None, **kw: Any) -> Any:
    from nemo_platform_plugin.models.types import ListProvidersQueryParams

    return _m_ep.list_providers(workspace=workspace, query_params=_build_model(ListProvidersQueryParams, kw))


def _inf_prov_update_status(name: str, *, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    from nemo_platform_plugin.models.types import UpdateProviderStatusRequest

    if body is None:
        body = _build_model(UpdateProviderStatusRequest, kw)
    return _m_ep.update_provider_status(workspace=workspace, name=name, body=body)


class _InferenceProvidersCompatMixin:
    retrieve = method(_inf_prov_retrieve)
    create = method(_inf_prov_create)
    update = method(_inf_prov_update)
    delete = method(_inf_prov_delete)
    list = method(_inf_prov_list)
    update_status = method(_inf_prov_update_status)


class _InferenceProvidersCompat(_InferenceProvidersCompatMixin, NemoClient):
    pass


class _AsyncInferenceProvidersCompat(_InferenceProvidersCompatMixin, AsyncNemoClient):
    pass


def _inf_dep_retrieve(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _m_ep.get_deployment(workspace=workspace, name=name)


def _inf_dep_create(*, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    from nemo_platform_plugin.models.types import CreateModelDeploymentRequest

    if body is None:
        body = _build_model(CreateModelDeploymentRequest, kw)
    return _m_ep.create_deployment(workspace=workspace, body=body)


def _inf_dep_update(name: str, *, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    from nemo_platform_plugin.models.types import UpdateModelDeploymentRequest

    if body is None:
        body = _build_model(UpdateModelDeploymentRequest, kw)
    return _m_ep.update_deployment(workspace=workspace, name=name, body=body)


def _inf_dep_delete(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _m_ep.delete_deployment(workspace=workspace, name=name)


def _inf_dep_list(*, workspace: str | None = None, **kw: Any) -> Any:
    from nemo_platform_plugin.models.types import ListDeploymentsQueryParams

    return _m_ep.list_deployments(workspace=workspace, query_params=_build_model(ListDeploymentsQueryParams, kw))


def _inf_dep_update_status(name: str, *, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    from nemo_platform_plugin.models.types import UpdateDeploymentStatusRequest

    if body is None:
        body = _build_model(UpdateDeploymentStatusRequest, kw)
    return _m_ep.update_deployment_status(workspace=workspace, name=name, body=body)


class _InferenceDeploymentsCompatMixin:
    retrieve = method(_inf_dep_retrieve)
    create = method(_inf_dep_create)
    update = method(_inf_dep_update)
    delete = method(_inf_dep_delete)
    list = method(_inf_dep_list)
    update_status = method(_inf_dep_update_status)


class _InferenceDeploymentsCompat(_InferenceDeploymentsCompatMixin, NemoClient):
    pass


class _AsyncInferenceDeploymentsCompat(_InferenceDeploymentsCompatMixin, AsyncNemoClient):
    pass


def _inf_dc_retrieve(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _m_ep.get_deployment_config(workspace=workspace, name=name)


def _inf_dc_create(*, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    from nemo_platform_plugin.models.types import CreateModelDeploymentConfigRequest

    if body is None:
        body = _build_model(CreateModelDeploymentConfigRequest, kw)
    return _m_ep.create_deployment_config(workspace=workspace, body=body)


def _inf_dc_update(name: str, *, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    from nemo_platform_plugin.models.types import UpdateModelDeploymentConfigRequest

    if body is None:
        body = _build_model(UpdateModelDeploymentConfigRequest, kw)
    return _m_ep.update_deployment_config(workspace=workspace, name=name, body=body)


def _inf_dc_delete(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _m_ep.delete_deployment_config(workspace=workspace, name=name)


def _inf_dc_list(*, workspace: str | None = None, **kw: Any) -> Any:
    from nemo_platform_plugin.models.types import ListDeploymentConfigsQueryParams

    return _m_ep.list_deployment_configs(
        workspace=workspace, query_params=_build_model(ListDeploymentConfigsQueryParams, kw)
    )


class _InferenceDeploymentConfigsCompatMixin:
    retrieve = method(_inf_dc_retrieve)
    create = method(_inf_dc_create)
    update = method(_inf_dc_update)
    delete = method(_inf_dc_delete)
    list = method(_inf_dc_list)


class _InferenceDeploymentConfigsCompat(_InferenceDeploymentConfigsCompatMixin, NemoClient):
    pass


class _AsyncInferenceDeploymentConfigsCompat(_InferenceDeploymentConfigsCompatMixin, AsyncNemoClient):
    pass


# Virtual models compat
from nemo_platform_plugin.virtual_models import endpoints as _vm_ep
from nemo_platform_plugin.virtual_models.types import (
    CreateVirtualModelRequest as _CVM,
)
from nemo_platform_plugin.virtual_models.types import (
    UpdateVirtualModelRequest as _UVM,
)


def _vm_retrieve(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _vm_ep.get_virtual_model(workspace=workspace, name=name)


def _vm_create(*, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_CVM, kw)
    return _vm_ep.create_virtual_model(workspace=workspace, body=body)


def _vm_update(name: str, *, workspace: str | None = None, body: Any = None, **kw: Any) -> Any:
    if body is None:
        body = _build_model(_UVM, kw)
    return _vm_ep.update_virtual_model(workspace=workspace, name=name, body=body)


def _vm_delete(name: str, *, workspace: str | None = None, **kw: Any) -> Any:
    return _vm_ep.delete_virtual_model(workspace=workspace, name=name)


def _vm_list(*, workspace: str | None = None, **kw: Any) -> Any:
    from nemo_platform_plugin.virtual_models.types import ListVirtualModelsQueryParams

    return _vm_ep.list_virtual_models(workspace=workspace, query_params=_build_model(ListVirtualModelsQueryParams, kw))


class _InferenceVirtualModelsCompatMixin:
    retrieve = method(_vm_retrieve)
    create = method(_vm_create)
    update = method(_vm_update)
    delete = method(_vm_delete)
    list = method(_vm_list)


class _InferenceVirtualModelsCompat(_InferenceVirtualModelsCompatMixin, NemoClient):
    pass


class _AsyncInferenceVirtualModelsCompat(_InferenceVirtualModelsCompatMixin, AsyncNemoClient):
    pass
