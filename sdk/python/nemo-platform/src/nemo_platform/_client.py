# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# File generated from our OpenAPI spec by Stainless. See CONTRIBUTING.md for details.

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Mapping
from typing_extensions import Self, override

import httpx

from . import _exceptions
from ._qs import Querystring
from ._types import (
    Omit,
    Timeout,
    NotGiven,
    Transport,
    ProxiesTypes,
    RequestOptions,
    not_given,
)
from ._utils import (
    is_given,
    is_mapping_t,
    get_async_library,
)
from ._compat import cached_property
from ._version import __version__
from ._streaming import Stream as Stream, AsyncStream as AsyncStream
from ._exceptions import APIStatusError
from ._base_client import (
    DEFAULT_MAX_RETRIES,
    SyncAPIClient,
    AsyncAPIClient,
)
from pathlib import Path

if TYPE_CHECKING:
    from .resources import (
        iam,
        jobs,
        files,
        intake,
        models,
        secrets,
        adapters,
        entities,
        projects,
        guardrail,
        inference,
        workspaces,
        experiments,
        experiment_groups,
    )
    from .resources.iam.iam import IamResource, AsyncIamResource
    from .resources.jobs.jobs import JobsResource, AsyncJobsResource
    from .filesets.resources import FilesResource, AsyncFilesResource
    from .resources.intake.intake import IntakeResource, AsyncIntakeResource
    from .models import ModelsResource, AsyncModelsResource
    from .resources.secrets.secrets import SecretsResource, AsyncSecretsResource
    from .resources.adapters.adapters import AdaptersResource, AsyncAdaptersResource
    from .resources.entities.entities import EntitiesResource, AsyncEntitiesResource
    from .resources.projects.projects import ProjectsResource, AsyncProjectsResource
    from .resources.guardrail.guardrail import GuardrailResource, AsyncGuardrailResource
    from .resources.inference.inference import InferenceResource, AsyncInferenceResource
    from .resources.workspaces.workspaces import WorkspacesResource, AsyncWorkspacesResource
    from .resources.experiments.experiments import ExperimentsResource, AsyncExperimentsResource
    from .resources.experiment_groups.experiment_groups import ExperimentGroupsResource, AsyncExperimentGroupsResource

__all__ = [
    "Timeout",
    "Transport",
    "ProxiesTypes",
    "RequestOptions",
    "NeMoPlatform",
    "AsyncNeMoPlatform",
    "Client",
    "AsyncClient",
]


class NeMoPlatform(SyncAPIClient):
    # client options
    workspace: str | None
    def __init__(
        self,
        *,
        workspace: str | None = None,
        base_url: str | httpx.URL | None = None,
        inference_base_url: str | httpx.URL | None = None,
        config_path: Path | None = None,
        context_name: str | None = None,
        access_token: str | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
        max_retries: int = DEFAULT_MAX_RETRIES,
        default_headers: Mapping[str, str] | None = None,
        default_query: Mapping[str, object] | None = None,
        # Configure a custom httpx client.
        # We provide a `DefaultHttpxClient` class that you can pass to retain the default values we use for `limits`, `timeout` & `follow_redirects`.
        # See the [httpx documentation](https://www.python-httpx.org/api/#client) for more details.
        http_client: httpx.Client | None = None,
        # Enable or disable schema validation for data returned by the API.
        # When enabled an error APIResponseValidationError is raised
        # if the API responds with invalid data for the expected schema.
        #
        # This parameter may be removed or changed in the future.
        # If you rely on this feature, please open a GitHub issue
        # outlining your use-case to help us decide if it should be
        # part of our public interface in the future.
        _strict_response_validation: bool = False,
    ) -> None:
        """Construct a new synchronous NeMoPlatform client instance.

        Calling with no arguments reads configuration from the active context in
        ``~/.config/nmp/config.yaml`` and wires up transparent OIDC token refresh.

        Passing only ``base_url`` activates *direct mode* — no config file is read
        and no auth headers are injected. To combine a custom ``base_url`` with
        config-based auth, also pass ``context_name`` or ``access_token``.

        Example — zero-config (reads from ``nemo auth login`` credentials):

        .. code-block:: python

            from nemo_platform import NeMoPlatform
            client = NeMoPlatform()

        Example — explicit token for automation:

        .. code-block:: python

            import os
            from nemo_platform import NeMoPlatform
            client = NeMoPlatform(
                base_url=os.environ["NMP_BASE_URL"],
                access_token=os.environ["NMP_ACCESS_TOKEN"],
                workspace="default",
            )

        Args:
            workspace: Workspace name used as a path parameter in all resource
                routes (``/workspaces/{workspace}/...``). Can also be supplied
                per-method. Raises ``ValueError`` at call time if absent from both.
            base_url: Base URL of the NeMo Platform API. If omitted, read from
                the active context in the nmp config file. Passing this parameter
                without ``context_name`` or ``access_token`` activates direct mode
                (no config file is read, no auth headers are injected).
            config_path: Path to the nmp config file. Defaults to
                ``~/.config/nmp/config.yaml``. Override in containers or CI where
                the default path is not available or writable.
            context_name: Name of the context to activate from the config file.
                Use this to switch between clusters. Also forces the auth bootstrap
                when ``base_url`` is explicitly set.
            access_token: Explicit Bearer token. Bypasses config-file auth and is
                suitable for CI/CD pipelines that obtain tokens externally.
                Automatic token refresh is not performed when this parameter is used.
            timeout: HTTP request timeout applied to all API calls. Accepts a float
                (seconds), an ``httpx.Timeout`` object, or ``None`` (no timeout).
                Individual methods can override this with their own ``timeout``
                argument.
            max_retries: Maximum number of automatic retries on transient failures.
                Defaults to ``2``. Set to ``0`` to disable retries.
            default_headers: Additional HTTP headers sent with every request.
            default_query: Additional query parameters appended to every request URL.
            http_client: Custom ``httpx.Client`` instance. When provided, the auth
                bootstrap is skipped entirely regardless of other parameters.
        """
        # Backward compatibility: an explicit base_url means direct mode (no config bootstrap),
        # unless config-specific overrides are provided.
        should_bootstrap = http_client is None and (
            base_url is None or config_path is not None or context_name is not None or access_token is not None
        )
        if should_bootstrap:
            try:
                from nemo_platform.client.factory import build_client_init_kwargs

                client_init_kwargs = build_client_init_kwargs(
                    config_path=config_path,
                    base_url=base_url,
                    context_name=context_name,
                    access_token=access_token,
                    extra_headers=default_headers,
                )
                base_url = client_init_kwargs.base_url
                if workspace is None:
                    workspace = client_init_kwargs.workspace
                default_headers = client_init_kwargs.default_headers
                http_client = client_init_kwargs.http_client
            except Exception as e:
                raise RuntimeError(f"NeMoPlatform client initialization failed: {e}")

        self.workspace = workspace

        super().__init__(
            version=__version__,
            base_url=base_url,
            max_retries=max_retries,
            timeout=timeout,
            http_client=http_client,
            custom_headers=default_headers,
            custom_query=default_query,
            _strict_response_validation=_strict_response_validation,
        )

        # TODO: needs to be removed
        self.inference_base_url = self._enforce_trailing_slash(httpx.URL(inference_base_url or base_url))

    @cached_property
    def entities(self) -> EntitiesResource:
        from .resources.entities import EntitiesResource

        return EntitiesResource(self)

    @cached_property
    def files(self) -> FilesResource:
        from .filesets.resources import FilesResource

        return FilesResource(self)

    @cached_property
    def guardrail(self) -> GuardrailResource:
        from .resources.guardrail import GuardrailResource

        return GuardrailResource(self)

    @cached_property
    def inference(self) -> InferenceResource:
        from .resources.inference import InferenceResource

        return InferenceResource(self)

    @cached_property
    def jobs(self) -> JobsResource:
        from .resources.jobs import JobsResource

        return JobsResource(self)

    @cached_property
    def models(self) -> ModelsResource:
        from .models import ModelsResource

        return ModelsResource(self)

    @cached_property
    def workspaces(self) -> WorkspacesResource:
        from .resources.workspaces import WorkspacesResource

        return WorkspacesResource(self)

    @cached_property
    def secrets(self) -> SecretsResource:
        from .resources.secrets import SecretsResource

        return SecretsResource(self)

    @cached_property
    def iam(self) -> IamResource:
        from .resources.iam import IamResource

        return IamResource(self)

    @cached_property
    def projects(self) -> ProjectsResource:
        from .resources.projects import ProjectsResource

        return ProjectsResource(self)

    @cached_property
    def adapters(self) -> AdaptersResource:
        from .resources.adapters import AdaptersResource

        return AdaptersResource(self)

    @cached_property
    def intake(self) -> IntakeResource:
        from .resources.intake import IntakeResource

        return IntakeResource(self)

    @cached_property
    def experiment_groups(self) -> ExperimentGroupsResource:
        from .resources.experiment_groups import ExperimentGroupsResource

        return ExperimentGroupsResource(self)

    @cached_property
    def experiments(self) -> ExperimentsResource:
        from .resources.experiments import ExperimentsResource

        return ExperimentsResource(self)

    @cached_property
    def with_raw_response(self) -> NeMoPlatformWithRawResponse:
        return NeMoPlatformWithRawResponse(self)

    @cached_property
    def with_streaming_response(self) -> NeMoPlatformWithStreamedResponse:
        return NeMoPlatformWithStreamedResponse(self)

    @property
    @override
    def qs(self) -> Querystring:
        return Querystring(array_format="comma")

    @property
    @override
    def default_headers(self) -> dict[str, str | Omit]:
        return {
            **super().default_headers,
            "X-Stainless-Async": "false",
            **self._custom_headers,
        }

    def copy(
        self,
        *,
        workspace: str | None = None,
        base_url: str | httpx.URL | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
        http_client: httpx.Client | None = None,
        max_retries: int | NotGiven = not_given,
        default_headers: Mapping[str, str] | None = None,
        set_default_headers: Mapping[str, str] | None = None,
        default_query: Mapping[str, object] | None = None,
        set_default_query: Mapping[str, object] | None = None,
        _extra_kwargs: Mapping[str, Any] = {},
    ) -> Self:
        """
        Create a new client instance re-using the same options given to the current client with optional overriding.
        """
        if default_headers is not None and set_default_headers is not None:
            raise ValueError("The `default_headers` and `set_default_headers` arguments are mutually exclusive")

        if default_query is not None and set_default_query is not None:
            raise ValueError("The `default_query` and `set_default_query` arguments are mutually exclusive")

        headers = self._custom_headers
        if default_headers is not None:
            headers = {**headers, **default_headers}
        elif set_default_headers is not None:
            headers = set_default_headers

        params = self._custom_query
        if default_query is not None:
            params = {**params, **default_query}
        elif set_default_query is not None:
            params = set_default_query

        http_client = http_client or self._client
        return self.__class__(
            workspace=workspace or self.workspace,
            base_url=base_url or self.base_url,
            timeout=self.timeout if isinstance(timeout, NotGiven) else timeout,
            http_client=http_client,
            max_retries=max_retries if is_given(max_retries) else self.max_retries,
            default_headers=headers,
            default_query=params,
            **_extra_kwargs,
        )

    # Alias for `copy` for nicer inline usage, e.g.
    # client.with_options(timeout=10).foo.create(...)
    with_options = copy

    def _get_workspace_path_param(self) -> str:
        from_client = self.workspace
        if from_client is not None:
            return from_client

        raise ValueError(
            "Missing workspace argument; Please provide it at the client level, e.g. NeMoPlatform(workspace='abcd') or per method."
        )

    @override
    def _make_status_error(
        self,
        err_msg: str,
        *,
        body: object,
        response: httpx.Response,
    ) -> APIStatusError:
        if response.status_code == 400:
            return _exceptions.BadRequestError(err_msg, response=response, body=body)

        if response.status_code == 401:
            return _exceptions.AuthenticationError(err_msg, response=response, body=body)

        if response.status_code == 403:
            return _exceptions.PermissionDeniedError(err_msg, response=response, body=body)

        if response.status_code == 404:
            return _exceptions.NotFoundError(err_msg, response=response, body=body)

        if response.status_code == 409:
            return _exceptions.ConflictError(err_msg, response=response, body=body)

        if response.status_code == 422:
            return _exceptions.UnprocessableEntityError(err_msg, response=response, body=body)

        if response.status_code == 429:
            return _exceptions.RateLimitError(err_msg, response=response, body=body)

        if response.status_code >= 500:
            return _exceptions.InternalServerError(err_msg, response=response, body=body)
        return APIStatusError(err_msg, response=response, body=body)

    def __getattr__(self, name: str) -> Any:
        from nemo_platform_plugin.discovery import discover_sdk

        plugins = discover_sdk()
        if name not in plugins:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute {name!r}")

        resource_cls = getattr(plugins[name], "sync_resource", None)
        if resource_cls is None:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute {name!r}")

        instance = resource_cls(self)
        self.__dict__[name] = instance
        return instance


class AsyncNeMoPlatform(AsyncAPIClient):
    # client options
    workspace: str | None

    def __init__(
        self,
        *,
        workspace: str | None = None,
        base_url: str | httpx.URL | None = None,
        inference_base_url: str | httpx.URL | None = None,
        config_path: Path | None = None,
        context_name: str | None = None,
        access_token: str | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
        max_retries: int = DEFAULT_MAX_RETRIES,
        default_headers: Mapping[str, str] | None = None,
        default_query: Mapping[str, object] | None = None,
        # Configure a custom httpx client.
        # We provide a `DefaultAsyncHttpxClient` class that you can pass to retain the default values we use for `limits`, `timeout` & `follow_redirects`.
        # See the [httpx documentation](https://www.python-httpx.org/api/#asyncclient) for more details.
        http_client: httpx.AsyncClient | None = None,
        # Enable or disable schema validation for data returned by the API.
        # When enabled an error APIResponseValidationError is raised
        # if the API responds with invalid data for the expected schema.
        #
        # This parameter may be removed or changed in the future.
        # If you rely on this feature, please open a GitHub issue
        # outlining your use-case to help us decide if it should be
        # part of our public interface in the future.
        _strict_response_validation: bool = False,
    ) -> None:
        """Construct a new asynchronous AsyncNeMoPlatform client instance.

        Calling with no arguments reads configuration from the active context in
        ``~/.config/nmp/config.yaml`` and wires up transparent OIDC token refresh.

        Passing only ``base_url`` activates *direct mode* — no config file is read
        and no auth headers are injected. To combine a custom ``base_url`` with
        config-based auth, also pass ``context_name`` or ``access_token``.

        Example — zero-config (reads from ``nemo auth login`` credentials):

        .. code-block:: python

            import asyncio
            from nemo_platform import AsyncNeMoPlatform

            async def main() -> None:
                client = AsyncNeMoPlatform()
                page = await client.workspaces.list()
                print(page.data)

            asyncio.run(main())

        Example — explicit token (CI/CD):

        .. code-block:: python

            import asyncio, os
            from nemo_platform import AsyncNeMoPlatform

            async def main() -> None:
                client = AsyncNeMoPlatform(
                    base_url=os.environ["NMP_BASE_URL"],
                    access_token=os.environ["NMP_ACCESS_TOKEN"],
                    workspace="default",
                )
                page = await client.workspaces.list()
                print(page.data)

            asyncio.run(main())

        Args:
            workspace: Workspace name used as a path parameter in all resource
                routes (``/workspaces/{workspace}/...``). Can also be supplied
                per-method. Raises ``ValueError`` at call time if absent from both.
            base_url: Base URL of the NeMo Platform API. If omitted, read from
                the active context in the nmp config file. Passing this parameter
                without ``context_name`` or ``access_token`` activates direct mode
                (no config file is read, no auth headers are injected).
            config_path: Path to the nmp config file. Defaults to
                ``~/.config/nmp/config.yaml``. Override in containers or CI where
                the default path is not available or writable.
            context_name: Name of the context to activate from the config file.
                Use this to switch between clusters. Also forces the auth bootstrap
                when ``base_url`` is explicitly set.
            access_token: Explicit Bearer token. Bypasses config-file auth and is
                suitable for CI/CD pipelines that obtain tokens externally.
                Automatic token refresh is not performed when this parameter is used.
            timeout: HTTP request timeout applied to all API calls. Accepts a float
                (seconds), an ``httpx.Timeout`` object, or ``None`` (no timeout).
                Individual methods can override this with their own ``timeout``
                argument.
            max_retries: Maximum number of automatic retries on transient failures.
                Defaults to ``2``. Set to ``0`` to disable retries.
            default_headers: Additional HTTP headers sent with every request.
            default_query: Additional query parameters appended to every request URL.
            http_client: Custom ``httpx.AsyncClient`` instance. When provided, the
                auth bootstrap is skipped entirely regardless of other parameters.
        """
        # Backward compatibility: an explicit base_url means direct mode (no config bootstrap),
        # unless config-specific overrides are provided.
        should_bootstrap = http_client is None and (
            base_url is None or config_path is not None or context_name is not None or access_token is not None
        )
        if should_bootstrap:
            try:
                from nemo_platform.client.factory import build_async_client_init_kwargs

                client_init_kwargs = build_async_client_init_kwargs(
                    config_path=config_path,
                    base_url=base_url,
                    context_name=context_name,
                    access_token=access_token,
                    extra_headers=default_headers,
                )
                base_url = client_init_kwargs.base_url
                if workspace is None:
                    workspace = client_init_kwargs.workspace
                default_headers = client_init_kwargs.default_headers
                http_client = client_init_kwargs.http_client
            except Exception as e:
                raise RuntimeError(f"NeMoPlatform client initialization failed: {e}")

        self.workspace = workspace

        super().__init__(
            version=__version__,
            base_url=base_url,
            max_retries=max_retries,
            timeout=timeout,
            http_client=http_client,
            custom_headers=default_headers,
            custom_query=default_query,
            _strict_response_validation=_strict_response_validation,
        )

        self._default_stream_cls = AsyncStream

        # If no inference_base_url is provided, use base_url
        # TODO: needs to be removed
        self.inference_base_url = self._enforce_trailing_slash(httpx.URL(inference_base_url or base_url))

    @cached_property
    def entities(self) -> AsyncEntitiesResource:
        from .resources.entities import AsyncEntitiesResource

        return AsyncEntitiesResource(self)

    @cached_property
    def files(self) -> AsyncFilesResource:
        from .filesets.resources import AsyncFilesResource

        return AsyncFilesResource(self)

    @cached_property
    def guardrail(self) -> AsyncGuardrailResource:
        from .resources.guardrail import AsyncGuardrailResource

        return AsyncGuardrailResource(self)

    @cached_property
    def inference(self) -> AsyncInferenceResource:
        from .resources.inference import AsyncInferenceResource

        return AsyncInferenceResource(self)

    @cached_property
    def jobs(self) -> AsyncJobsResource:
        from .resources.jobs import AsyncJobsResource

        return AsyncJobsResource(self)

    @cached_property
    def models(self) -> AsyncModelsResource:
        from .models import AsyncModelsResource

        return AsyncModelsResource(self)

    @cached_property
    def workspaces(self) -> AsyncWorkspacesResource:
        from .resources.workspaces import AsyncWorkspacesResource

        return AsyncWorkspacesResource(self)

    @cached_property
    def secrets(self) -> AsyncSecretsResource:
        from .resources.secrets import AsyncSecretsResource

        return AsyncSecretsResource(self)

    @cached_property
    def iam(self) -> AsyncIamResource:
        from .resources.iam import AsyncIamResource

        return AsyncIamResource(self)

    @cached_property
    def projects(self) -> AsyncProjectsResource:
        from .resources.projects import AsyncProjectsResource

        return AsyncProjectsResource(self)

    @cached_property
    def adapters(self) -> AsyncAdaptersResource:
        from .resources.adapters import AsyncAdaptersResource

        return AsyncAdaptersResource(self)

    @cached_property
    def intake(self) -> AsyncIntakeResource:
        from .resources.intake import AsyncIntakeResource

        return AsyncIntakeResource(self)

    @cached_property
    def experiment_groups(self) -> AsyncExperimentGroupsResource:
        from .resources.experiment_groups import AsyncExperimentGroupsResource

        return AsyncExperimentGroupsResource(self)

    @cached_property
    def experiments(self) -> AsyncExperimentsResource:
        from .resources.experiments import AsyncExperimentsResource

        return AsyncExperimentsResource(self)

    @cached_property
    def with_raw_response(self) -> AsyncNeMoPlatformWithRawResponse:
        return AsyncNeMoPlatformWithRawResponse(self)

    @cached_property
    def with_streaming_response(self) -> AsyncNeMoPlatformWithStreamedResponse:
        return AsyncNeMoPlatformWithStreamedResponse(self)

    @property
    @override
    def qs(self) -> Querystring:
        return Querystring(array_format="comma")

    @property
    @override
    def default_headers(self) -> dict[str, str | Omit]:
        return {
            **super().default_headers,
            "X-Stainless-Async": f"async:{get_async_library()}",
            **self._custom_headers,
        }

    def copy(
        self,
        *,
        workspace: str | None = None,
        base_url: str | httpx.URL | None = None,
        timeout: float | Timeout | None | NotGiven = not_given,
        http_client: httpx.AsyncClient | None = None,
        max_retries: int | NotGiven = not_given,
        default_headers: Mapping[str, str] | None = None,
        set_default_headers: Mapping[str, str] | None = None,
        default_query: Mapping[str, object] | None = None,
        set_default_query: Mapping[str, object] | None = None,
        _extra_kwargs: Mapping[str, Any] = {},
    ) -> Self:
        """
        Create a new client instance re-using the same options given to the current client with optional overriding.
        """
        if default_headers is not None and set_default_headers is not None:
            raise ValueError("The `default_headers` and `set_default_headers` arguments are mutually exclusive")

        if default_query is not None and set_default_query is not None:
            raise ValueError("The `default_query` and `set_default_query` arguments are mutually exclusive")

        headers = self._custom_headers
        if default_headers is not None:
            headers = {**headers, **default_headers}
        elif set_default_headers is not None:
            headers = set_default_headers

        params = self._custom_query
        if default_query is not None:
            params = {**params, **default_query}
        elif set_default_query is not None:
            params = set_default_query

        http_client = http_client or self._client
        return self.__class__(
            workspace=workspace or self.workspace,
            base_url=base_url or self.base_url,
            timeout=self.timeout if isinstance(timeout, NotGiven) else timeout,
            http_client=http_client,
            max_retries=max_retries if is_given(max_retries) else self.max_retries,
            default_headers=headers,
            default_query=params,
            **_extra_kwargs,
        )

    # Alias for `copy` for nicer inline usage, e.g.
    # client.with_options(timeout=10).foo.create(...)
    with_options = copy

    def _get_workspace_path_param(self) -> str:
        from_client = self.workspace
        if from_client is not None:
            return from_client

        raise ValueError(
            "Missing workspace argument; Please provide it at the client level, e.g. AsyncNeMoPlatform(workspace='abcd') or per method."
        )

    @override
    def _make_status_error(
        self,
        err_msg: str,
        *,
        body: object,
        response: httpx.Response,
    ) -> APIStatusError:
        if response.status_code == 400:
            return _exceptions.BadRequestError(err_msg, response=response, body=body)

        if response.status_code == 401:
            return _exceptions.AuthenticationError(err_msg, response=response, body=body)

        if response.status_code == 403:
            return _exceptions.PermissionDeniedError(err_msg, response=response, body=body)

        if response.status_code == 404:
            return _exceptions.NotFoundError(err_msg, response=response, body=body)

        if response.status_code == 409:
            return _exceptions.ConflictError(err_msg, response=response, body=body)

        if response.status_code == 422:
            return _exceptions.UnprocessableEntityError(err_msg, response=response, body=body)

        if response.status_code == 429:
            return _exceptions.RateLimitError(err_msg, response=response, body=body)

        if response.status_code >= 500:
            return _exceptions.InternalServerError(err_msg, response=response, body=body)
        return APIStatusError(err_msg, response=response, body=body)

    def __getattr__(self, name: str) -> Any:
        from nemo_platform_plugin.discovery import discover_sdk

        plugins = discover_sdk()
        if name not in plugins:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute {name!r}")

        resource_cls = getattr(plugins[name], "async_resource", None)
        if resource_cls is None:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute {name!r}")

        instance = resource_cls(self)
        self.__dict__[name] = instance
        return instance


class NeMoPlatformWithRawResponse:
    _client: NeMoPlatform

    def __init__(self, client: NeMoPlatform) -> None:
        self._client = client

    @cached_property
    def entities(self) -> entities.EntitiesResourceWithRawResponse:
        from .resources.entities import EntitiesResourceWithRawResponse

        return EntitiesResourceWithRawResponse(self._client.entities)

    @cached_property
    def files(self) -> files.FilesResourceWithRawResponse:
        from .resources.files import FilesResourceWithRawResponse

        return FilesResourceWithRawResponse(self._client.files)

    @cached_property
    def guardrail(self) -> guardrail.GuardrailResourceWithRawResponse:
        from .resources.guardrail import GuardrailResourceWithRawResponse

        return GuardrailResourceWithRawResponse(self._client.guardrail)

    @cached_property
    def inference(self) -> inference.InferenceResourceWithRawResponse:
        from .resources.inference import InferenceResourceWithRawResponse

        return InferenceResourceWithRawResponse(self._client.inference)

    @cached_property
    def jobs(self) -> jobs.JobsResourceWithRawResponse:
        from .resources.jobs import JobsResourceWithRawResponse

        return JobsResourceWithRawResponse(self._client.jobs)

    @cached_property
    def models(self) -> models.ModelsResourceWithRawResponse:
        from .resources.models import ModelsResourceWithRawResponse

        return ModelsResourceWithRawResponse(self._client.models)

    @cached_property
    def workspaces(self) -> workspaces.WorkspacesResourceWithRawResponse:
        from .resources.workspaces import WorkspacesResourceWithRawResponse

        return WorkspacesResourceWithRawResponse(self._client.workspaces)

    @cached_property
    def secrets(self) -> secrets.SecretsResourceWithRawResponse:
        from .resources.secrets import SecretsResourceWithRawResponse

        return SecretsResourceWithRawResponse(self._client.secrets)

    @cached_property
    def iam(self) -> iam.IamResourceWithRawResponse:
        from .resources.iam import IamResourceWithRawResponse

        return IamResourceWithRawResponse(self._client.iam)

    @cached_property
    def projects(self) -> projects.ProjectsResourceWithRawResponse:
        from .resources.projects import ProjectsResourceWithRawResponse

        return ProjectsResourceWithRawResponse(self._client.projects)

    @cached_property
    def adapters(self) -> adapters.AdaptersResourceWithRawResponse:
        from .resources.adapters import AdaptersResourceWithRawResponse

        return AdaptersResourceWithRawResponse(self._client.adapters)

    @cached_property
    def intake(self) -> intake.IntakeResourceWithRawResponse:
        from .resources.intake import IntakeResourceWithRawResponse

        return IntakeResourceWithRawResponse(self._client.intake)

    @cached_property
    def experiment_groups(self) -> experiment_groups.ExperimentGroupsResourceWithRawResponse:
        from .resources.experiment_groups import ExperimentGroupsResourceWithRawResponse

        return ExperimentGroupsResourceWithRawResponse(self._client.experiment_groups)

    @cached_property
    def experiments(self) -> experiments.ExperimentsResourceWithRawResponse:
        from .resources.experiments import ExperimentsResourceWithRawResponse

        return ExperimentsResourceWithRawResponse(self._client.experiments)


class AsyncNeMoPlatformWithRawResponse:
    _client: AsyncNeMoPlatform

    def __init__(self, client: AsyncNeMoPlatform) -> None:
        self._client = client

    @cached_property
    def entities(self) -> entities.AsyncEntitiesResourceWithRawResponse:
        from .resources.entities import AsyncEntitiesResourceWithRawResponse

        return AsyncEntitiesResourceWithRawResponse(self._client.entities)

    @cached_property
    def files(self) -> files.AsyncFilesResourceWithRawResponse:
        from .resources.files import AsyncFilesResourceWithRawResponse

        return AsyncFilesResourceWithRawResponse(self._client.files)

    @cached_property
    def guardrail(self) -> guardrail.AsyncGuardrailResourceWithRawResponse:
        from .resources.guardrail import AsyncGuardrailResourceWithRawResponse

        return AsyncGuardrailResourceWithRawResponse(self._client.guardrail)

    @cached_property
    def inference(self) -> inference.AsyncInferenceResourceWithRawResponse:
        from .resources.inference import AsyncInferenceResourceWithRawResponse

        return AsyncInferenceResourceWithRawResponse(self._client.inference)

    @cached_property
    def jobs(self) -> jobs.AsyncJobsResourceWithRawResponse:
        from .resources.jobs import AsyncJobsResourceWithRawResponse

        return AsyncJobsResourceWithRawResponse(self._client.jobs)

    @cached_property
    def models(self) -> models.AsyncModelsResourceWithRawResponse:
        from .resources.models import AsyncModelsResourceWithRawResponse

        return AsyncModelsResourceWithRawResponse(self._client.models)

    @cached_property
    def workspaces(self) -> workspaces.AsyncWorkspacesResourceWithRawResponse:
        from .resources.workspaces import AsyncWorkspacesResourceWithRawResponse

        return AsyncWorkspacesResourceWithRawResponse(self._client.workspaces)

    @cached_property
    def secrets(self) -> secrets.AsyncSecretsResourceWithRawResponse:
        from .resources.secrets import AsyncSecretsResourceWithRawResponse

        return AsyncSecretsResourceWithRawResponse(self._client.secrets)

    @cached_property
    def iam(self) -> iam.AsyncIamResourceWithRawResponse:
        from .resources.iam import AsyncIamResourceWithRawResponse

        return AsyncIamResourceWithRawResponse(self._client.iam)

    @cached_property
    def projects(self) -> projects.AsyncProjectsResourceWithRawResponse:
        from .resources.projects import AsyncProjectsResourceWithRawResponse

        return AsyncProjectsResourceWithRawResponse(self._client.projects)

    @cached_property
    def adapters(self) -> adapters.AsyncAdaptersResourceWithRawResponse:
        from .resources.adapters import AsyncAdaptersResourceWithRawResponse

        return AsyncAdaptersResourceWithRawResponse(self._client.adapters)

    @cached_property
    def intake(self) -> intake.AsyncIntakeResourceWithRawResponse:
        from .resources.intake import AsyncIntakeResourceWithRawResponse

        return AsyncIntakeResourceWithRawResponse(self._client.intake)

    @cached_property
    def experiment_groups(self) -> experiment_groups.AsyncExperimentGroupsResourceWithRawResponse:
        from .resources.experiment_groups import AsyncExperimentGroupsResourceWithRawResponse

        return AsyncExperimentGroupsResourceWithRawResponse(self._client.experiment_groups)

    @cached_property
    def experiments(self) -> experiments.AsyncExperimentsResourceWithRawResponse:
        from .resources.experiments import AsyncExperimentsResourceWithRawResponse

        return AsyncExperimentsResourceWithRawResponse(self._client.experiments)


class NeMoPlatformWithStreamedResponse:
    _client: NeMoPlatform

    def __init__(self, client: NeMoPlatform) -> None:
        self._client = client

    @cached_property
    def entities(self) -> entities.EntitiesResourceWithStreamingResponse:
        from .resources.entities import EntitiesResourceWithStreamingResponse

        return EntitiesResourceWithStreamingResponse(self._client.entities)

    @cached_property
    def files(self) -> files.FilesResourceWithStreamingResponse:
        from .resources.files import FilesResourceWithStreamingResponse

        return FilesResourceWithStreamingResponse(self._client.files)

    @cached_property
    def guardrail(self) -> guardrail.GuardrailResourceWithStreamingResponse:
        from .resources.guardrail import GuardrailResourceWithStreamingResponse

        return GuardrailResourceWithStreamingResponse(self._client.guardrail)

    @cached_property
    def inference(self) -> inference.InferenceResourceWithStreamingResponse:
        from .resources.inference import InferenceResourceWithStreamingResponse

        return InferenceResourceWithStreamingResponse(self._client.inference)

    @cached_property
    def jobs(self) -> jobs.JobsResourceWithStreamingResponse:
        from .resources.jobs import JobsResourceWithStreamingResponse

        return JobsResourceWithStreamingResponse(self._client.jobs)

    @cached_property
    def models(self) -> models.ModelsResourceWithStreamingResponse:
        from .resources.models import ModelsResourceWithStreamingResponse

        return ModelsResourceWithStreamingResponse(self._client.models)

    @cached_property
    def workspaces(self) -> workspaces.WorkspacesResourceWithStreamingResponse:
        from .resources.workspaces import WorkspacesResourceWithStreamingResponse

        return WorkspacesResourceWithStreamingResponse(self._client.workspaces)

    @cached_property
    def secrets(self) -> secrets.SecretsResourceWithStreamingResponse:
        from .resources.secrets import SecretsResourceWithStreamingResponse

        return SecretsResourceWithStreamingResponse(self._client.secrets)

    @cached_property
    def iam(self) -> iam.IamResourceWithStreamingResponse:
        from .resources.iam import IamResourceWithStreamingResponse

        return IamResourceWithStreamingResponse(self._client.iam)

    @cached_property
    def projects(self) -> projects.ProjectsResourceWithStreamingResponse:
        from .resources.projects import ProjectsResourceWithStreamingResponse

        return ProjectsResourceWithStreamingResponse(self._client.projects)

    @cached_property
    def adapters(self) -> adapters.AdaptersResourceWithStreamingResponse:
        from .resources.adapters import AdaptersResourceWithStreamingResponse

        return AdaptersResourceWithStreamingResponse(self._client.adapters)

    @cached_property
    def intake(self) -> intake.IntakeResourceWithStreamingResponse:
        from .resources.intake import IntakeResourceWithStreamingResponse

        return IntakeResourceWithStreamingResponse(self._client.intake)

    @cached_property
    def experiment_groups(self) -> experiment_groups.ExperimentGroupsResourceWithStreamingResponse:
        from .resources.experiment_groups import ExperimentGroupsResourceWithStreamingResponse

        return ExperimentGroupsResourceWithStreamingResponse(self._client.experiment_groups)

    @cached_property
    def experiments(self) -> experiments.ExperimentsResourceWithStreamingResponse:
        from .resources.experiments import ExperimentsResourceWithStreamingResponse

        return ExperimentsResourceWithStreamingResponse(self._client.experiments)


class AsyncNeMoPlatformWithStreamedResponse:
    _client: AsyncNeMoPlatform

    def __init__(self, client: AsyncNeMoPlatform) -> None:
        self._client = client

    @cached_property
    def entities(self) -> entities.AsyncEntitiesResourceWithStreamingResponse:
        from .resources.entities import AsyncEntitiesResourceWithStreamingResponse

        return AsyncEntitiesResourceWithStreamingResponse(self._client.entities)

    @cached_property
    def files(self) -> files.AsyncFilesResourceWithStreamingResponse:
        from .resources.files import AsyncFilesResourceWithStreamingResponse

        return AsyncFilesResourceWithStreamingResponse(self._client.files)

    @cached_property
    def guardrail(self) -> guardrail.AsyncGuardrailResourceWithStreamingResponse:
        from .resources.guardrail import AsyncGuardrailResourceWithStreamingResponse

        return AsyncGuardrailResourceWithStreamingResponse(self._client.guardrail)

    @cached_property
    def inference(self) -> inference.AsyncInferenceResourceWithStreamingResponse:
        from .resources.inference import AsyncInferenceResourceWithStreamingResponse

        return AsyncInferenceResourceWithStreamingResponse(self._client.inference)

    @cached_property
    def jobs(self) -> jobs.AsyncJobsResourceWithStreamingResponse:
        from .resources.jobs import AsyncJobsResourceWithStreamingResponse

        return AsyncJobsResourceWithStreamingResponse(self._client.jobs)

    @cached_property
    def models(self) -> models.AsyncModelsResourceWithStreamingResponse:
        from .resources.models import AsyncModelsResourceWithStreamingResponse

        return AsyncModelsResourceWithStreamingResponse(self._client.models)

    @cached_property
    def workspaces(self) -> workspaces.AsyncWorkspacesResourceWithStreamingResponse:
        from .resources.workspaces import AsyncWorkspacesResourceWithStreamingResponse

        return AsyncWorkspacesResourceWithStreamingResponse(self._client.workspaces)

    @cached_property
    def secrets(self) -> secrets.AsyncSecretsResourceWithStreamingResponse:
        from .resources.secrets import AsyncSecretsResourceWithStreamingResponse

        return AsyncSecretsResourceWithStreamingResponse(self._client.secrets)

    @cached_property
    def iam(self) -> iam.AsyncIamResourceWithStreamingResponse:
        from .resources.iam import AsyncIamResourceWithStreamingResponse

        return AsyncIamResourceWithStreamingResponse(self._client.iam)

    @cached_property
    def projects(self) -> projects.AsyncProjectsResourceWithStreamingResponse:
        from .resources.projects import AsyncProjectsResourceWithStreamingResponse

        return AsyncProjectsResourceWithStreamingResponse(self._client.projects)

    @cached_property
    def adapters(self) -> adapters.AsyncAdaptersResourceWithStreamingResponse:
        from .resources.adapters import AsyncAdaptersResourceWithStreamingResponse

        return AsyncAdaptersResourceWithStreamingResponse(self._client.adapters)

    @cached_property
    def intake(self) -> intake.AsyncIntakeResourceWithStreamingResponse:
        from .resources.intake import AsyncIntakeResourceWithStreamingResponse

        return AsyncIntakeResourceWithStreamingResponse(self._client.intake)

    @cached_property
    def experiment_groups(self) -> experiment_groups.AsyncExperimentGroupsResourceWithStreamingResponse:
        from .resources.experiment_groups import AsyncExperimentGroupsResourceWithStreamingResponse

        return AsyncExperimentGroupsResourceWithStreamingResponse(self._client.experiment_groups)

    @cached_property
    def experiments(self) -> experiments.AsyncExperimentsResourceWithStreamingResponse:
        from .resources.experiments import AsyncExperimentsResourceWithStreamingResponse

        return AsyncExperimentsResourceWithStreamingResponse(self._client.experiments)


Client = NeMoPlatform

AsyncClient = AsyncNeMoPlatform
