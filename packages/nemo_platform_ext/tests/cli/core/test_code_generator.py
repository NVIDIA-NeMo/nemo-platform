# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for code generation."""

import pytest
from nemo_platform_ext.cli.core.code_generator import generate_python_code


def test_generate_python_code_simple_list():
    """Test generating code for a simple list operation."""
    code = generate_python_code(
        resource_path=["models"],
        method="list",
        args={},
        base_url=None,
    )

    assert "from nemo_platform_plugin.client.client import NemoClient" in code
    assert "client = NeMoPlatform()" in code
    assert "response = client.models.list()" in code
    assert "print(response)" in code


def test_generate_python_code_with_base_url():
    """Test generating code with base URL."""
    code = generate_python_code(
        resource_path=["datasets"],
        method="list",
        args={},
        base_url="http://test.example.com",
    )

    assert 'client = NeMoPlatform(base_url="http://test.example.com")' in code


def test_generate_python_code_with_args():
    """Test generating code with arguments."""
    code = generate_python_code(
        resource_path=["models"],
        method="retrieve",
        args={"model_name": "my-model", "namespace": "default"},
        base_url=None,
    )

    assert 'model_name="my-model"' in code
    assert 'namespace="default"' in code
    assert "client.models.retrieve" in code


def test_generate_python_code_nested_resource():
    """Test generating code for nested resources."""
    code = generate_python_code(
        resource_path=["customization", "configs"],
        method="list",
        args={},
        base_url=None,
    )

    assert "client.customization.configs.list()" in code


def test_generate_python_code_with_dict_args():
    """Test generating code with dictionary arguments."""
    code = generate_python_code(
        resource_path=["models"],
        method="list",
        args={
            "filter": {"namespace": "default", "name": "test"},
            "page": 1,
        },
        base_url=None,
    )

    assert "filter=" in code
    assert "page=1" in code
    assert '"namespace": "default"' in code or "'namespace': 'default'" in code


def test_generate_python_code_multiline_format():
    """Test that code with many args is formatted multiline."""
    code = generate_python_code(
        resource_path=["models"],
        method="create",
        args={
            "name": "my-model",
            "namespace": "default",
            "description": "A test model",
            "files_url": "s3://bucket/path",
        },
        base_url=None,
    )

    # Should be multiline with many args
    lines = code.split("\n")
    # Check that args are on separate lines
    assert any("name=" in line and line.strip().startswith("name=") for line in lines)
    assert any("namespace=" in line and line.strip().startswith("namespace=") for line in lines)


def test_generate_python_code_with_platform_job_wait():
    code = generate_python_code(
        resource_path=["customization", "jobs"],
        method="create",
        args={"workspace": "default", "name": "job-a", "spec": {"training_type": "sft"}},
        wait_config={"type": "platform_job", "resource_label": "customization job"},
        wait_options={"timeout": 42, "poll_interval": 7},
    )

    assert "import time" in code
    assert "response = client.customization.jobs.create" in code
    assert 'resource_name = getattr(response, "name", None) or "job-a"' in code
    assert 'raise RuntimeError("Unable to determine created resource name for --wait")' in code
    assert "deadline = time.monotonic() + 42" in code
    assert 'client.customization.jobs.get_status(resource_name, workspace="default")' in code
    assert 'status = str(status_response.status or "").lower()' in code
    assert "response = status_response" in code
    assert code.rindex("print(response)") > code.index("response = status_response")
    assert "time.sleep(min(7, remaining))" in code
    compile(code, "<generated-code>", "exec")


def test_generate_python_code_with_inference_deployment_wait():
    code = generate_python_code(
        resource_path=["inference", "deployments"],
        method="create",
        args={"workspace": "default", "name": "deployment-a", "config": "deployment-config"},
        wait_config={"type": "inference_deployment", "resource_label": "deployment"},
        wait_options={"timeout": 90, "poll_interval": 10},
    )

    assert "import time" in code
    for symbol in ("APIConnectionError", "APIStatusError", "APITimeoutError", "NeMoPlatform", "NotFoundError"):
        assert symbol in code
    assert "deadline = time.monotonic() + 90" in code
    assert 'resource_name = getattr(response, "name", None) or "deployment-a"' in code
    assert 'raise RuntimeError("Unable to determine created resource name for --wait")' in code
    assert 'client.inference.deployments.retrieve(resource_name, workspace="default")' in code
    assert 'model_provider_id = getattr(deployment, "model_provider_id", None)' in code
    assert 'provider_workspace, _, provider_name = model_provider_id.partition("/")' in code
    assert "client.inference.gateway.provider.ready(provider_name, workspace=provider_workspace)" in code
    assert "except NotFoundError:" in code
    assert "except (APIConnectionError, APITimeoutError):" in code
    assert "except APIStatusError as exc:" in code
    assert "except Exception:" not in code
    assert "response = deployment" in code
    assert code.rindex("print(response)") > code.index("response = deployment")
    assert "time.sleep(min(10, remaining))" in code
    compile(code, "<generated-code>", "exec")


def test_generate_python_code_escapes_platform_job_wait_label():
    code = generate_python_code(
        resource_path=["customization", "jobs"],
        method="create",
        args={"workspace": "default", "name": "job-a"},
        wait_config={"type": "platform_job", "resource_label": 'customization "job" {label}'},
        wait_options={"timeout": 42, "poll_interval": 7},
    )

    compile(code, "<generated-code>", "exec")
    assert '"customization \\"job\\" {label}" + f" {resource_name!r}' in code


def test_generate_python_code_rejects_unknown_wait_type():
    with pytest.raises(ValueError, match="Unsupported wait config type: 'unknown'"):
        generate_python_code(
            resource_path=["customization", "jobs"],
            method="create",
            args={"workspace": "default", "name": "job-a"},
            wait_config={"type": "unknown", "resource_label": "customization job"},
        )
