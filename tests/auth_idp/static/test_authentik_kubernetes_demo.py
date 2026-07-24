# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import ast
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from nemo_platform_plugin.client.constants import WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR

pytestmark = [pytest.mark.auth_idp]

AUTHENTIK_DIR = Path("contrib/auth/authentik")
HELM_DIR = AUTHENTIK_DIR / "helm"
AUTHENTIK_SCRIPT_TIMEOUT_SECONDS = 30
HELM_TEMPLATE_TIMEOUT_SECONDS = 60
ENVOY_SERVICE_URL_TEMPLATE = (
    '{{ include "nemo-platform-authentik.serviceUrl" '
    '(dict "root" . "serviceName" "nemo-platform-envoy" '
    '"namespace" .Values.envoyProxy.serviceNamespace "scheme" "https" "port" 8080) }}'
)
ENVOY_CONTROLLER_ENV_URL = "https://nemo-platform-envoy.$(POD_NAMESPACE).svc.cluster.local:8080"
AUTHENTIK_SERVICE_URL_TEMPLATE = '{{ include "nemo-platform-authentik.serviceUrl" (dict "root" . "serviceName" "authentik-server" "scheme" "http") }}'
PUBLIC_GATEWAY_URL_TEMPLATE = '{{ include "nemo-platform-authentik.publicGatewayUrl" . }}'


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _literal_run_commands(path: Path) -> set[tuple[str, ...]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    commands: set[tuple[str, ...]] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "_run":
            continue
        if not node.args:
            continue

        try:
            command = ast.literal_eval(node.args[0])
        except (SyntaxError, ValueError):
            continue

        if isinstance(command, list) and all(isinstance(part, str) for part in command):
            commands.add(tuple(command))

    return commands


def _workflow_job_block(workflow: str, job_name: str) -> str:
    lines = workflow.splitlines()
    start = next(index for index, line in enumerate(lines) if line == f"  {job_name}:")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            end = index
            break
    return "\n".join(lines[start:end])


def _load_authentik_k8s_live_module() -> ModuleType:
    module_path = Path("tests/auth_idp/runtime_kubernetes.py")
    spec = importlib.util.spec_from_file_location("authentik_k8s_live_for_unit", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_authentik_script(*args: str, env: dict[str, str] | None = None) -> str:
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    completed = subprocess.run(
        [str(AUTHENTIK_DIR / "run.sh"), *args],
        text=True,
        capture_output=True,
        check=False,
        env=process_env,
        timeout=AUTHENTIK_SCRIPT_TIMEOUT_SECONDS,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed.stdout


def test_authentik_run_local_defaults_workload_identity_password_for_compose() -> None:
    env = os.environ.copy()
    env.pop("AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD", None)
    completed = subprocess.run(
        [str(AUTHENTIK_DIR / "run.sh"), "run-local", "--dry-run"],
        text=True,
        capture_output=True,
        check=False,
        env=env,
        timeout=AUTHENTIK_SCRIPT_TIMEOUT_SECONDS,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "helm/files/blueprints/nemo.yaml" in completed.stdout
    assert "contrib/auth/authentik/.generated/workload-token-private-key.pem" in completed.stdout
    assert "contrib/auth/authentik/.generated/gateway-tls" in completed.stdout
    assert "contrib/auth/authentik/compose" in completed.stdout
    assert "AUTHENTIK_WORKLOAD_IDENTITY_PASSWORD=<redacted>" in completed.stdout
    assert "docker compose up" in completed.stdout


def test_authentik_prepare_local_creates_shared_generated_inputs() -> None:
    output = _run_authentik_script("prepare-local", "--dry-run")

    assert "helm/files/blueprints/nemo.yaml" in output
    assert "contrib/auth/authentik/.generated/workload-token-private-key.pem" in output
    assert "contrib/auth/authentik/.generated/gateway-tls" in output
    assert "docker compose up" not in output


def test_authentik_user_startup_docs_use_manual_runtime_steps() -> None:
    top_level_readme = (AUTHENTIK_DIR / "README.md").read_text(encoding="utf-8")
    tutorial = (AUTHENTIK_DIR / "tutorial.md").read_text(encoding="utf-8")
    compose_readme = (AUTHENTIK_DIR / "compose" / "README.md").read_text(encoding="utf-8")
    compose_details = (AUTHENTIK_DIR / "compose" / "implementation-details.md").read_text(encoding="utf-8")
    kubernetes_readme = (AUTHENTIK_DIR / "kubernetes" / "README.md").read_text(encoding="utf-8")
    kubernetes_details = (AUTHENTIK_DIR / "kubernetes" / "implementation-details.md").read_text(encoding="utf-8")

    assert "run.sh --help" in top_level_readme
    assert "(tutorial.md)" in top_level_readme
    assert "(compose/implementation-details.md)" in top_level_readme
    assert "(kubernetes/implementation-details.md)" in top_level_readme
    assert "### Docker Compose" in tutorial
    assert "### Kubernetes" in tutorial
    assert "## Wait For The Gateway" in tutorial
    assert "${AUTHENTIK_BASE_URL}/health/gateway/ready" in tutorial
    assert "NeMo Platform and Authentik Ready" in tutorial
    assert "uv run nemo auth login \\" in tutorial
    assert '--context "$AUTHENTIK_CONTEXT"' in tutorial
    assert '--base-url "$AUTHENTIK_BASE_URL"' in tutorial
    assert '--principal "$AUTHENTIK_WORKLOAD_GROUP"' in tutorial
    assert "contrib/auth/authentik/run.sh prepare-local" in tutorial
    assert "cd contrib/auth/authentik/compose" not in tutorial
    assert "docker compose -f contrib/auth/authentik/compose/docker-compose.yml up" in tutorial
    assert "docker compose -f contrib/auth/authentik/compose/docker-compose.yml down -v" in tutorial
    assert (
        "--set-file workloadTokenSigningKey.privateKeyPem="
        "contrib/auth/authentik/.generated/workload-token-private-key.pem"
    ) in tutorial
    assert "contrib/auth/authentik/run.sh run-local" not in tutorial
    assert "contrib/auth/authentik/run.sh compose" not in tutorial
    assert "contrib/auth/authentik/run.sh k8s" not in tutorial
    assert "run.sh" not in compose_readme
    assert "run.sh" not in kubernetes_readme
    assert "docker compose up" in compose_readme
    assert "nemo-platform-authentik" in compose_readme
    assert "helm --kube-context" in kubernetes_readme
    assert "(implementation-details.md)" in compose_readme
    assert "(implementation-details.md)" in kubernetes_readme
    assert "For the step-by-step test flow, see the" in compose_details
    assert "[shared tutorial](../tutorial.md)" in compose_details
    assert "COMPOSE_PROJECT_NAME" in compose_details
    assert "For the step-by-step test flow, see the [shared tutorial](../tutorial.md)." in kubernetes_details


def test_authentik_tutorial_grants_workloads_job_log_permissions() -> None:
    tutorial = (AUTHENTIK_DIR / "tutorial.md").read_text(encoding="utf-8")

    editor_group_block = """
uv run nemo --context "$AUTHENTIK_CONTEXT" workspaces members create \\
  --workspace "$WORKSPACE" \\
  --principal nemo-editors \\
  --roles Viewer \\
  --wait-role-propagation
"""
    service_account_group_block = """
uv run nemo --context "$AUTHENTIK_CONTEXT" workspaces members create \\
  --workspace "$WORKSPACE" \\
  --principal "$AUTHENTIK_WORKLOAD_GROUP" \\
  --roles Viewer \\
  --roles JobRunner \\
  --wait-role-propagation
"""

    assert editor_group_block in tutorial
    assert service_account_group_block in tutorial
    assert "dedicated `nemo-workloads` Authentik group" in tutorial
    assert "permission to upload workload" in tutorial


def test_authentik_e2e_ci_requires_published_nmp_api_image() -> None:
    ci_workflow = Path(".github/workflows/ci.yaml").read_text(encoding="utf-8")
    job = _workflow_job_block(ci_workflow, "python-auth-idp-e2e-test")

    assert "needs.policy-wasm.result == 'success'" in job
    assert "needs.build-cpu-smoke-images.result == 'success'" in job
    assert "needs.build-cpu-smoke-images.outputs.publish_images == 'true'" in job
    assert "needs.python-auth-idp-static-test.result == 'success'" in job
    assert '--image "${IMAGE_REGISTRY}/nmp-api:${BAKE_TAG}"' in job


def _helm_template_authentik_demo(template: str) -> str:
    if shutil.which("helm") is None:
        pytest.skip("helm is required to render the Authentik Kubernetes demo chart")

    completed = subprocess.run(
        [
            "helm",
            "template",
            "authentik-demo",
            str(AUTHENTIK_DIR / "helm"),
            "-n",
            "nemo-authentik",
            "--show-only",
            template,
        ],
        text=True,
        capture_output=True,
        check=False,
        timeout=HELM_TEMPLATE_TIMEOUT_SECONDS,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def _load_rendered_authentik_envoy_config() -> dict:
    rendered = _helm_template_authentik_demo("charts/nemo-platform/templates/proxy/envoy-configmap.yaml")
    config_map = next(
        document
        for document in yaml.safe_load_all(rendered)
        if document and document["kind"] == "ConfigMap" and document["metadata"]["name"] == "nemo-platform-envoy"
    )
    return yaml.safe_load(config_map["data"]["envoy.yaml"])


def test_authentik_umbrella_chart_declares_expected_dependencies() -> None:
    chart = _load_yaml(HELM_DIR / "Chart.yaml")
    dependencies = {dependency["name"]: dependency for dependency in chart["dependencies"]}

    assert chart["name"] == "nemo-platform-authentik"
    assert "cert-manager" not in dependencies
    assert dependencies["authentik"] == {
        "name": "authentik",
        "version": "2026.5.4",
        "repository": "https://charts.goauthentik.io",
    }
    assert "postgresql" not in dependencies
    assert dependencies["nemo-platform"] == {
        "name": "nemo-platform",
        "version": "0.1.0",
        "repository": "file://../../../../k8s/helm",
    }


def test_authentik_umbrella_values_use_latest_authentik_chart_without_image_tag_override() -> None:
    values = _load_yaml(HELM_DIR / "values.yaml")
    authentik_values = values["authentik"]

    assert authentik_values["fullnameOverride"] == "authentik"
    assert authentik_values["postgresql"]["enabled"] is False
    assert authentik_values["blueprints"]["configMaps"] == ["authentik-nemo-blueprint"]
    assert {
        "name": "AUTHENTIK_POSTGRESQL__PASSWORD",
        "valueFrom": {
            "secretKeyRef": {
                "name": "shared-postgresql",
                "key": "authentik-password",
            }
        },
    } in authentik_values["global"]["env"]
    assert authentik_values["authentik"]["postgresql"] == {
        "host": "shared-postgresql",
        "name": "authentik",
        "user": "authentik",
        "port": 5432,
    }
    assert authentik_values.get("global", {}).get("image", {}).get("tag", "") == ""


def test_authentik_umbrella_values_define_one_shared_postgresql_instance() -> None:
    values = _load_yaml(HELM_DIR / "values.yaml")
    initdb_template = (HELM_DIR / "templates" / "shared-postgres-initdb-configmap.yaml").read_text(encoding="utf-8")
    secret_template = (HELM_DIR / "templates" / "shared-postgres-secret.yaml").read_text(encoding="utf-8")
    nemo_secret_template = (HELM_DIR / "templates" / "shared-postgres-nemo-secret.yaml").read_text(encoding="utf-8")
    helpers_template = (HELM_DIR / "templates" / "_helpers.tpl").read_text(encoding="utf-8")

    assert values["sharedPostgresql"]["enabled"] is True
    assert values["sharedPostgresql"]["serviceName"] == "shared-postgresql"
    assert "password" not in values["sharedPostgresql"]["authentik"]
    assert "cert-manager" not in values
    assert "shared-postgresql" not in values
    assert 'define "nemo-platform-authentik.sharedPostgresql.password"' in helpers_template
    assert 'define "nemo-platform-authentik.existingSecretData"' in helpers_template
    assert 'include "nemo-platform-authentik.existingSecretData"' in helpers_template
    assert 'lookup "v1" "PersistentVolumeClaim" $root.Release.Namespace $pvcName' in helpers_template
    assert "restore the Secret or rotate the PostgreSQL role before changing it" in helpers_template
    assert secret_template.count('include "nemo-platform-authentik.sharedPostgresql.password"') == 3
    assert '"secretKey" "authentik-password" "value" .Values.sharedPostgresql.authentik.password "generate" true' in (
        secret_template
    )
    assert "authentik-password: {{ $authentikPassword | quote }}" in secret_template
    assert nemo_secret_template.startswith("{{- if .Values.sharedPostgresql.enabled }}\n{{- $nemoPassword :=")
    assert nemo_secret_template.rstrip().endswith("{{- end }}")
    assert 'include "nemo-platform-authentik.sharedPostgresql.password"' in nemo_secret_template
    assert "--set=" not in initdb_template
    assert "<<'EOSQL'" in initdb_template
    assert "\\set authentik_password `printf '%s' \"$AUTHENTIK_PASSWORD\"`" in initdb_template
    assert "\\set nemo_password `printf '%s' \"$NEMO_PASSWORD\"`" in initdb_template
    assert "CREATE USER :\"authentik_username\" WITH PASSWORD :'authentik_password';" in initdb_template
    assert "CREATE USER :\"nemo_username\" WITH PASSWORD :'nemo_password';" in initdb_template

    nemo_database = values["nemo-platform"]["externalDatabase"]
    assert values["nemo-platform"]["postgresql"]["enabled"] is False
    assert nemo_database == {
        "host": "shared-postgresql",
        "port": 5432,
        "user": "nemo",
        "database": "nemoplatform",
        "existingSecret": "shared-postgresql-nemo",
        "existingSecretPasswordKey": "password",
    }


def test_authentik_kubernetes_helm_args_can_reuse_precreated_ngc_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NMP_AUTHENTIK_K8S_NGC_EXISTING_SECRET", "ngc-api")

    live_test = _load_authentik_k8s_live_module()

    args = live_test._helm_upgrade_args("kind-ci")
    assert "nemo-platform.existingSecret=ngc-api" in args


def test_authentik_kubernetes_helm_args_can_override_public_gateway_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NMP_AUTHENTIK_K8S_GATEWAY_PORT", "18082")

    live_test = _load_authentik_k8s_live_module()

    args = live_test._helm_upgrade_args("kind-ci")
    assert "nemo-platform.authentikPublicGateway.port=18082" in args


def test_authentik_kubernetes_live_timeouts_are_named_constants() -> None:
    live_test = _load_authentik_k8s_live_module()

    args = live_test._helm_upgrade_args("kind-ci")
    assert args[args.index("--timeout") + 1] == live_test.HELM_WAIT_TIMEOUT
    assert live_test.HELM_WAIT_TIMEOUT == "10m"
    assert live_test.HELM_UPGRADE_COMMAND_TIMEOUT_SECONDS == 900
    assert live_test.PORT_FORWARD_READY_TIMEOUT_SECONDS == 30


def test_authentik_kubernetes_reuse_context_validates_runtime() -> None:
    live_test = _load_authentik_k8s_live_module()

    assert live_test._reuse_context("kind", "ci") == "kind-ci"
    assert live_test._reuse_context("k3d", "ci") == "k3d-ci"
    with pytest.raises(ValueError, match="unsupported NMP_AUTHENTIK_K8S_RUNTIME='minikube'; expected kind or k3d"):
        live_test._reuse_context("minikube", "ci")


def test_authentik_kubernetes_reuse_or_create_uses_existing_cluster(monkeypatch: pytest.MonkeyPatch) -> None:
    live_test = _load_authentik_k8s_live_module()
    existing = live_test.Cluster(name="ci", runtime="kind", context="kind-ci")

    monkeypatch.setattr(live_test, "_existing_cluster", lambda runtime, name: existing)
    monkeypatch.setattr(
        live_test,
        "_create_cluster",
        lambda runtime, name: pytest.fail("reuse should not create an existing cluster"),
    )

    assert live_test._reuse_or_create_cluster("kind", "ci") == existing


def test_authentik_kubernetes_reuse_or_create_creates_missing_cluster(monkeypatch: pytest.MonkeyPatch) -> None:
    live_test = _load_authentik_k8s_live_module()
    created = live_test.Cluster(name="ci", runtime="kind", context="kind-ci")

    monkeypatch.setattr(live_test, "_existing_cluster", lambda runtime, name: None)
    monkeypatch.setattr(live_test, "_create_cluster", lambda runtime, name: created)

    assert live_test._reuse_or_create_cluster("kind", "ci") == created


def test_authentik_kubernetes_kind_create_uses_isolated_kubeconfig(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live_test = _load_authentik_k8s_live_module()
    kubeconfig = tmp_path / "kind-kubeconfig.yaml"
    commands: list[list[str]] = []

    monkeypatch.setattr(live_test, "_temporary_kubeconfig_path", lambda cluster_name: kubeconfig)
    monkeypatch.setattr(live_test, "_require_tool", lambda name: None)

    def record_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(live_test, "_run", record_command)

    cluster = live_test._create_cluster("kind", "ci")

    assert cluster == live_test.Cluster(
        name="ci",
        runtime="kind",
        context="kind-ci",
        kubeconfig=kubeconfig,
        cleanup_kubeconfig=True,
    )
    assert commands == [
        [
            "kind",
            "create",
            "cluster",
            "--name",
            "ci",
            "--kubeconfig",
            str(kubeconfig),
            "--wait",
            live_test.KIND_CREATE_WAIT_TIMEOUT,
        ]
    ]


def test_authentik_kubernetes_k3d_create_does_not_update_default_kubeconfig(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    live_test = _load_authentik_k8s_live_module()
    kubeconfig = tmp_path / "k3d-kubeconfig.yaml"
    commands: list[list[str]] = []

    monkeypatch.setattr(live_test, "_temporary_kubeconfig_path", lambda cluster_name: kubeconfig)
    monkeypatch.setattr(live_test, "_require_tool", lambda name: None)

    def record_command(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        if args == ["k3d", "kubeconfig", "get", "ci"]:
            return subprocess.CompletedProcess(args, 0, stdout="apiVersion: v1\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(live_test, "_run", record_command)

    cluster = live_test._create_cluster("k3d", "ci")

    assert cluster == live_test.Cluster(
        name="ci",
        runtime="k3d",
        context="k3d-ci",
        kubeconfig=kubeconfig,
        cleanup_kubeconfig=True,
    )
    assert commands[0] == [
        "k3d",
        "cluster",
        "create",
        "ci",
        "--wait",
        "--agents",
        "0",
        "--k3s-arg",
        "--disable=traefik@server:0",
        "--kubeconfig-update-default=false",
    ]
    assert commands[1] == ["k3d", "kubeconfig", "get", "ci"]
    assert kubeconfig.read_text(encoding="utf-8") == "apiVersion: v1\n"


def test_authentik_kubernetes_commands_accept_isolated_kubeconfig() -> None:
    live_test = _load_authentik_k8s_live_module()
    kubeconfig = Path("/tmp/nmp-authentik-kubeconfig.yaml")

    assert live_test._kubectl_command("kind-ci", ["get", "pods"], kubeconfig) == [
        "kubectl",
        "--kubeconfig",
        str(kubeconfig),
        "--context",
        "kind-ci",
        "get",
        "pods",
    ]
    assert live_test._helm_upgrade_args("kind-ci", kubeconfig)[:5] == [
        "helm",
        "--kubeconfig",
        str(kubeconfig),
        "--kube-context",
        "kind-ci",
    ]


def test_authentik_kubernetes_port_forward_times_out_without_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    live_test = _load_authentik_k8s_live_module()

    class FakeProcess:
        returncode = None

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout: int | None = None) -> None:
            return None

        def kill(self) -> None:
            return None

    monotonic_values = iter([0.0, 0.0, 31.0])
    monkeypatch.setattr(live_test, "_free_port", lambda: 19001)
    monkeypatch.setattr(live_test.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(live_test.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(live_test.time, "sleep", lambda seconds: None)
    requested_urls = []

    def fake_get(url: str, **_kwargs: object):
        requested_urls.append(url)
        raise live_test.httpx.ConnectError("not ready")

    monkeypatch.setattr(live_test.httpx, "get", fake_get)

    with pytest.raises(TimeoutError, match="timed out waiting for port-forward readiness"):
        live_test._start_port_forward_service("kind-ci", "nemo-platform-envoy", Path("ca.crt"))

    assert requested_urls == ["https://127.0.0.1:19001/health/gateway/ready"]


def test_authentik_kubernetes_port_forward_waits_after_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    live_test = _load_authentik_k8s_live_module()
    events: list[object] = []

    class FakeProcess:
        returncode = None

        def poll(self) -> int | None:
            return self.returncode

        def terminate(self) -> None:
            events.append("terminate")

        def wait(self, timeout: int | None = None) -> int:
            events.append(("wait", timeout))
            if timeout is not None:
                raise live_test.subprocess.TimeoutExpired(cmd="kubectl", timeout=timeout)
            self.returncode = -9
            return self.returncode

        def kill(self) -> None:
            events.append("kill")

    monotonic_values = iter([0.0, 0.0, 31.0])
    monkeypatch.setattr(live_test, "_free_port", lambda: 19001)
    monkeypatch.setattr(live_test.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(live_test.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(live_test.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        live_test.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(live_test.httpx.ConnectError("not ready")),
    )

    with pytest.raises(TimeoutError, match="timed out waiting for port-forward readiness"):
        live_test._start_port_forward_service("kind-ci", "nemo-platform-envoy", Path("ca.crt"))

    assert events == [
        "terminate",
        ("wait", live_test.PORT_FORWARD_TERMINATE_TIMEOUT_SECONDS),
        "kill",
        ("wait", None),
    ]


def test_authentik_kubernetes_diagnostics_records_pod_discovery_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    live_test = _load_authentik_k8s_live_module()
    monkeypatch.setenv("NMP_AUTHENTIK_K8S_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(live_test, "_write_diagnostic_process", lambda *args, **kwargs: None)

    def raise_timeout(args: list[str], **kwargs: object) -> None:
        raise live_test.subprocess.TimeoutExpired(
            cmd=args,
            timeout=kwargs["timeout"],
            output="partial pod list\n",
            stderr="kubectl timed out\n",
        )

    monkeypatch.setattr(live_test.subprocess, "run", raise_timeout)

    log_dir = live_test._collect_kubernetes_diagnostics("kind-ci", "ci")

    assert log_dir == tmp_path / "k8s-authentik-ci"
    pod_discovery = log_dir / "get-pods-for-logs.txt"
    assert pod_discovery.read_text(encoding="utf-8") == "\n".join(
        (
            "command: kubectl --context kind-ci -n nemo-authentik get pods -o "
            "jsonpath={range .items[*]}{.metadata.name}{'\\n'}{end}",
            "timeout: 60",
            "stdout:",
            "partial pod list\n",
            "stderr:",
            "kubectl timed out\n",
        )
    )
    assert not list(log_dir.glob("logs-*.txt"))


def test_authentik_kubernetes_cleanup_deletes_cluster_when_diagnostics_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_test = _load_authentik_k8s_live_module()
    runtime = live_test.KubernetesAuthIdpRuntime.__new__(live_test.KubernetesAuthIdpRuntime)
    runtime.cluster = live_test.Cluster(name="ci", runtime="kind", context="kind-ci")
    runtime._port_forward_process = None
    runtime._ca_temp_file = None
    runtime._previous_client_ssl_cert_file = os.environ.get(live_test.NMP_CLIENT_SSL_CERT_FILE_ENVVAR)
    runtime._diagnostics_collected = False
    runtime._reuse_cluster = False
    runtime._keep_cluster = False
    deleted: list[tuple[str, str]] = []

    def raise_diagnostics(context: str, cluster_name: str, kubeconfig: Path | None = None) -> Path:
        raise RuntimeError(f"diagnostics failed for {context}/{cluster_name}")

    def delete_cluster(runtime_name: str, cluster_name: str, kubeconfig: Path | None = None) -> None:
        deleted.append((runtime_name, cluster_name))

    monkeypatch.setattr(live_test, "_collect_kubernetes_diagnostics", raise_diagnostics)
    monkeypatch.setattr(live_test, "_delete_cluster", delete_cluster)

    runtime.cleanup()

    assert deleted == [("kind", "ci")]
    assert runtime.cluster is None
    assert runtime._diagnostics_collected is True


def test_authentik_kubernetes_startup_preserves_original_error_when_diagnostics_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_test = _load_authentik_k8s_live_module()
    runtime = live_test.KubernetesAuthIdpRuntime.__new__(live_test.KubernetesAuthIdpRuntime)
    runtime.cluster = None
    runtime.ca_bundle = None
    runtime._port_forward_process = None
    runtime._ca_temp_file = None
    runtime._previous_client_ssl_cert_file = os.environ.get(live_test.NMP_CLIENT_SSL_CERT_FILE_ENVVAR)
    runtime._diagnostics_collected = False
    runtime._reuse_cluster = False
    runtime._keep_cluster = False
    diagnostics_calls: list[tuple[str, str]] = []
    deleted: list[tuple[str, str]] = []

    def raise_startup_error(runtime_name: str, cluster_name: str, image: str) -> None:
        raise RuntimeError(f"startup failed for {runtime_name}/{cluster_name}/{image}")

    def raise_diagnostics(context: str, cluster_name: str, kubeconfig: Path | None = None) -> Path:
        diagnostics_calls.append((context, cluster_name))
        raise RuntimeError(f"diagnostics failed for {context}/{cluster_name}")

    def delete_cluster(runtime_name: str, cluster_name: str, kubeconfig: Path | None = None) -> None:
        deleted.append((runtime_name, cluster_name))

    monkeypatch.setenv("NMP_AUTHENTIK_K8S_RUNTIME", "kind")
    monkeypatch.setenv("NMP_AUTHENTIK_K8S_CLUSTER_NAME", "ci")
    monkeypatch.delenv("NMP_AUTHENTIK_K8S_REUSE_CLUSTER", raising=False)
    monkeypatch.delenv("NMP_AUTHENTIK_K8S_KEEP_CLUSTER", raising=False)
    monkeypatch.setattr(
        live_test,
        "_create_cluster",
        lambda runtime_name, cluster_name: live_test.Cluster(
            name=cluster_name,
            runtime=runtime_name,
            context="kind-ci",
            kubeconfig=Path("isolated-kubeconfig.yaml"),
            cleanup_kubeconfig=True,
        ),
    )
    monkeypatch.setattr(live_test, "_platform_image", lambda: "nmp:test")
    monkeypatch.setattr(live_test, "_load_platform_image", raise_startup_error)
    monkeypatch.setattr(live_test, "_collect_kubernetes_diagnostics", raise_diagnostics)
    monkeypatch.setattr(live_test, "_delete_cluster", delete_cluster)

    with pytest.raises(RuntimeError, match="startup failed"):
        runtime._start()

    assert diagnostics_calls == [("kind-ci", "ci")]
    assert deleted == [("kind", "ci")]
    assert runtime.cluster is None
    assert runtime._diagnostics_collected is True


@pytest.mark.auth_idp_k8s
def test_authentik_umbrella_values_configure_nemo_envoy_as_the_only_edge_proxy() -> None:
    values = _load_yaml(HELM_DIR / "values.yaml")
    helpers_template = (HELM_DIR / "templates" / "_helpers.tpl").read_text(encoding="utf-8")
    nemo_values = values["nemo-platform"]
    envoy = nemo_values["envoyProxy"]
    envoy_config = _load_rendered_authentik_envoy_config()
    http_manager = envoy_config["static_resources"]["listeners"][0]["filter_chains"][0]["filters"][0]["typed_config"]
    routes = http_manager["route_config"]["virtual_hosts"][0]["routes"]
    forwarded_proto_header = [
        {
            "header": {"key": "x-forwarded-proto", "value": "https"},
            "append_action": "OVERWRITE_IF_EXISTS_OR_ADD",
        }
    ]
    jwt_filter = next(
        filter_config
        for filter_config in http_manager["http_filters"]
        if filter_config["name"] == "envoy.filters.http.jwt_authn"
    )
    jwt_providers = jwt_filter["typed_config"]["providers"]
    clusters = {cluster["name"]: cluster for cluster in envoy_config["static_resources"]["clusters"]}

    assert envoy["configOverride"] == '{{ include "nemo-platform-authentik.envoyConfig" . }}'
    gateway_ready_route = next(route for route in routes if route["match"] == {"path": "/health/gateway/ready"})
    health_route = next(route for route in routes if route["match"] == {"prefix": "/health/"})
    assert routes.index(gateway_ready_route) < routes.index(health_route)
    assert gateway_ready_route["direct_response"] == {
        "status": 503,
        "body": {"inline_string": '{"status":"not_ready"}'},
    }
    for match in (
        {"prefix": "/.well-known/nemo-platform/"},
        {"prefix": "/apis/"},
        {"prefix": "/health/"},
        {"path": "/status"},
        {"prefix": "/studio/"},
    ):
        route = next(
            route for route in routes if route.get("route", {}).get("cluster") == "nemo" and route["match"] == match
        )
        assert route["request_headers_to_add"] == forwarded_proto_header
    lua_filter = next(
        filter_config
        for filter_config in http_manager["http_filters"]
        if filter_config["name"] == "envoy.filters.http.lua"
    )
    lua_code = lua_filter["typed_config"]["inline_code"]
    assert 'headers:get(":path") ~= "/health/gateway/ready"' in lua_code
    assert 'gateway_ready_http_call(request_handle, "nemo", "nemo-platform-api", "/health/ready")' in lua_code
    assert (
        'gateway_ready_http_call(request_handle, "authentik", "authentik-server", '
        '"/application/o/nemo/.well-known/openid-configuration")'
    ) in lua_code
    assert jwt_providers["authentik_workload"]["remote_jwks"]["http_uri"] == {
        "uri": "https://nemo-platform-envoy:8080/application/o/nemo/jwks/",
        "cluster": "nemo_envoy_https",
        "timeout": "5s",
    }
    assert jwt_providers["workload_exchange"]["remote_jwks"]["http_uri"] == {
        "uri": "https://nemo-platform-envoy:8080/apis/auth/jwks",
        "cluster": "nemo_envoy_https",
        "timeout": "5s",
    }
    envoy_jwks_cluster = clusters["nemo_envoy_https"]
    assert envoy_jwks_cluster["transport_socket"]["typed_config"]["common_tls_context"]["validation_context"][
        "trusted_ca"
    ] == {"filename": "/etc/nmp/workload-token-tls/ca.crt"}

    platform_config = nemo_values["platformConfig"].get("platform", {})
    assert "base_url" not in platform_config
    assert "auth" not in platform_config.get("service_discovery", {})
    oidc = nemo_values["platformConfig"]["auth"]["oidc"]
    assert oidc["issuer"] == f"{AUTHENTIK_SERVICE_URL_TEMPLATE}/application/o/nemo-cli/"
    assert oidc["additional_issuers"][0] == f"{AUTHENTIK_SERVICE_URL_TEMPLATE}/application/o/nemo/"
    assert oidc["additional_issuers"][1] == f"{PUBLIC_GATEWAY_URL_TEMPLATE}/application/o/nemo-cli/"
    assert oidc["additional_issuers"][2] == f"{PUBLIC_GATEWAY_URL_TEMPLATE}/application/o/nemo/"
    assert oidc["workload_token_issuer"] == f"{ENVOY_SERVICE_URL_TEMPLATE}/apis/auth"
    assert oidc["workload_token_endpoint"] == f"{ENVOY_SERVICE_URL_TEMPLATE}/apis/auth/token"
    assert oidc["token_endpoint"] == f"{PUBLIC_GATEWAY_URL_TEMPLATE}/application/o/token/"
    assert oidc["device_authorization_endpoint"] == f"{PUBLIC_GATEWAY_URL_TEMPLATE}/application/o/device/"
    assert nemo_values["authentikPublicGateway"] == {
        "scheme": "https",
        "host": "127.0.0.1",
        "port": 18081,
    }
    assert "nemo-platform.authentikPublicGateway.host is required" in helpers_template
    assert "nemo-platform.authentikPublicGateway.port is required" in helpers_template
    assert 'default "127.0.0.1"' not in helpers_template
    assert "default 18081" not in helpers_template
    assert nemo_values["authentikEnvoy"] == {"serviceName": "authentik-server", "servicePort": 80}
    assert nemo_values["envoyProxy"]["serviceNamespace"] == ""
    assert values["integration"]["nemoPlatform"]["envoyServiceName"] == "nemo-platform-envoy"
    assert nemo_values["rbac"]["volcanoEnabled"] is False
    assert nemo_values["platformConfig"]["models"]["controller"]["backends"] == {
        "deployments_plugin": {"enabled": True},
    }


def test_nemo_platform_chart_does_not_use_volcano_disable_config() -> None:
    values_template = Path("k8s/helm/values.yaml").read_text(encoding="utf-8")

    assert "enable_default_volcano_executor" not in values_template


def test_authentik_umbrella_values_mount_workload_token_signing_key_as_file() -> None:
    values = _load_yaml(HELM_DIR / "values.yaml")
    signing_key = values["workloadTokenSigningKey"]
    nemo_values = values["nemo-platform"]
    oidc = nemo_values["platformConfig"]["auth"]["oidc"]

    assert signing_key["secretName"] == "nemo-workload-token-signing-key"
    assert signing_key["key"] == "private-key.pem"
    assert signing_key["mountPath"] == "/etc/nmp/workload-token"
    assert signing_key["privateKeyPem"] == ""
    assert oidc["workload_token_private_key_file"] == "/etc/nmp/workload-token/private-key.pem"

    assert nemo_values["api"]["extraVolumes"] == [
        {
            "name": "workload-token-signing-key",
            "secret": {"secretName": "nemo-workload-token-signing-key"},
        }
    ]
    assert nemo_values["api"]["extraVolumeMounts"] == [
        {
            "name": "workload-token-signing-key",
            "mountPath": "/etc/nmp/workload-token",
            "readOnly": True,
        }
    ]


def test_authentik_umbrella_chart_does_not_locally_template_subchart_workloads() -> None:
    template_names = {path.name for path in (HELM_DIR / "templates").glob("*.yaml")}

    forbidden = {
        "authentik-deployment.yaml",
        "authentik-server-deployment.yaml",
        "authentik-worker-deployment.yaml",
        "postgres-deployment.yaml",
        "postgres-statefulset.yaml",
        "redis-deployment.yaml",
        "nemo-deployment.yaml",
        "nemo-service.yaml",
        "gateway-configmap.yaml",
        "gateway-deployment.yaml",
        "gateway-service.yaml",
    }
    assert template_names.isdisjoint(forbidden)


def test_authentik_umbrella_chart_uses_single_canonical_authentik_blueprint() -> None:
    packaged = (HELM_DIR / "files" / "blueprints" / "nemo.yaml").read_text(encoding="utf-8")
    configmap_template = (HELM_DIR / "templates" / "blueprint-configmap.yaml").read_text(encoding="utf-8")

    assert not (AUTHENTIK_DIR / "blueprints" / "nemo.yaml").exists()
    assert "grant_types:" in packaged
    assert "- password" in packaged
    assert "- urn:ietf:params:oauth:grant-type:device_code" in packaged
    assert 'blueprints.goauthentik.io/instantiate: "true"' in packaged
    assert '.Files.Get "files/blueprints/nemo.yaml"' in configmap_template

    values = _load_yaml(HELM_DIR / "values.yaml")
    assert values["blueprintApplyJob"]["enabled"] is True
    assert values["blueprintApplyJob"]["image"]["tag"] == "2026.5.4"


def test_authentik_umbrella_chart_applies_blueprint_with_waitable_helm_hook() -> None:
    template = (HELM_DIR / "templates" / "blueprint-apply-job.yaml").read_text(encoding="utf-8")

    assert "kind: Job" in template
    assert '"helm.sh/hook": post-install,post-upgrade' in template
    assert '"helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded' in template
    assert "- ak" in template
    assert "- apply_blueprint" in template
    assert "- /blueprints/mounted/cm-authentik-nemo-blueprint/nemo.yaml" in template
    assert "authentik-nemo-blueprint" in template
    assert "automountServiceAccountToken: false" in template
    assert "nmp.nvidia.com/blueprint-checksum" not in template


def test_authentik_kubernetes_runner_uses_helm_not_kustomize() -> None:
    run_sh = (AUTHENTIK_DIR / "run.sh").read_text(encoding="utf-8")
    live_test_path = Path("tests/auth_idp/k8s/test_authentik_kubernetes_live.py")
    live_test = live_test_path.read_text(encoding="utf-8")
    runtime_path = Path("tests/auth_idp/runtime_kubernetes.py")
    runtime_impl = runtime_path.read_text(encoding="utf-8")
    ci_workflow = Path(".github/workflows/ci.yaml").read_text(encoding="utf-8")
    setup_kind_action = Path(".github/actions/setup-kind-cluster/action.yaml").read_text(encoding="utf-8")
    run_commands = _literal_run_commands(runtime_path)

    assert "NMP_AUTHENTIK_K8S_HELM_RELEASE" in run_sh
    assert 'K8S_RUNTIME="${NMP_AUTHENTIK_K8S_RUNTIME:-kind}"' in run_sh
    assert "uv run --frozen pytest tests/auth_idp/contracts" in run_sh
    assert "--auth-idp-runtime authentik-kubernetes" in run_sh
    assert "-m auth_idp_runtime" in run_sh
    assert "--run-e2e" not in run_sh
    assert "uv run --frozen pytest tests/auth_idp/static -v" in ci_workflow
    assert 'uv run --frozen pytest tests/auth_idp -v -m "auth_idp and not auth_idp_runtime"' not in ci_workflow
    assert "--runtime RUNTIME" in run_sh
    assert "validate_k8s_runtime" in run_sh
    assert "--reuse" in run_sh
    assert "--cluster-name" not in run_sh
    assert "--reuse-cluster" not in run_sh
    assert "--keep-cluster" not in run_sh
    assert "--skip-image-load" in run_sh
    expected_skip_image_load_line = (
        "NMP_AUTHENTIK_K8S_SKIP_IMAGE_LOAD: "
        "${{ needs.build-cpu-smoke-images.outputs.publish_images == 'true' && '1' || '0' }}"
    )
    assert expected_skip_image_load_line in ci_workflow
    assert "NMP_AUTHENTIK_K8S_NAMESPACE: nemo-authentik" in ci_workflow
    assert "kube-namespace: ${{ env.NMP_AUTHENTIK_K8S_NAMESPACE }}" in ci_workflow
    assert "NMP_AUTHENTIK_K8S_IMAGE_PULL_SECRET: ghcr-pull" in ci_workflow
    assert "NMP_AUTHENTIK_K8S_NGC_EXISTING_SECRET: ngc-api" in ci_workflow
    assert 'K8S_IMAGE_PULL_SECRET="${NMP_AUTHENTIK_K8S_IMAGE_PULL_SECRET:-}"' in run_sh
    assert "NMP_AUTHENTIK_K8S_IMAGE_PULL_SECRET=${K8S_IMAGE_PULL_SECRET}" in run_sh
    assert "NMP_AUTHENTIK_K8S_IMAGE_PULL_SECRET" in runtime_impl
    assert "nemo-platform.imagePullSecrets[0].name=" in runtime_impl
    assert "NMP_AUTHENTIK_K8S_NGC_EXISTING_SECRET" in runtime_impl
    assert "nemo-platform.existingSecret=" in runtime_impl
    assert 'K8S_GATEWAY_PORT="${NMP_AUTHENTIK_K8S_GATEWAY_PORT:-18082}"' in run_sh
    assert "NMP_AUTHENTIK_K8S_GATEWAY_PORT=${K8S_GATEWAY_PORT}" in run_sh
    assert "NMP_AUTHENTIK_K8S_GATEWAY_PORT" in runtime_impl
    assert "nemo-platform.authentikPublicGateway.port=" in runtime_impl
    assert "GITHUB_TOKEN: ${{ inputs['kind-image-pull-token'] }}" in setup_kind_action
    assert "CERT_MANAGER_CHART" not in runtime_impl
    assert "_install_cert_manager" not in runtime_impl
    assert ("helm", "repo", "add", "nvidia", "https://helm.ngc.nvidia.com/nvidia", "--force-update") in run_commands
    assert ("helm", "repo", "add", "authentik", "https://charts.goauthentik.io", "--force-update") in run_commands
    assert 'os.environ.get("NMP_AUTHENTIK_K8S_RUNTIME", "kind")' in runtime_impl
    assert '"--no-hooks"' not in runtime_impl
    assert "HELM_UPGRADE_COMMAND_TIMEOUT_SECONDS = 900" in runtime_impl
    assert "_run(_helm_upgrade_args(context, kubeconfig), timeout=HELM_UPGRADE_COMMAND_TIMEOUT_SECONDS)" in runtime_impl
    assert "PORT_FORWARD_READY_TIMEOUT_SECONDS = 30" in runtime_impl
    assert "certificates.cert-manager.io" not in runtime_impl
    assert "issuers.cert-manager.io" not in runtime_impl
    assert "NMP_AUTHENTIK_K8S_KUSTOMIZATION" not in run_sh
    assert "NMP_AUTHENTIK_K8S_KUSTOMIZATION" not in runtime_impl
    assert 'kubectl", "--context", context, "apply"' not in runtime_impl
    assert "auth_idp_k8s" in live_test
    assert "nmp.nvidia.com/blueprint-checksum" not in (HELM_DIR / "values.yaml").read_text(encoding="utf-8")


def test_authentik_kubernetes_runner_builds_when_only_image_tag_env_is_set() -> None:
    output = _run_authentik_script(
        "k8s",
        "--dry-run",
        env={
            "IMAGE_REGISTRY": "registry.example.test/nemo",
            "BAKE_TAG": "tag-from-env",
            "NMP_AUTHENTIK_K8S_REUSE_CLUSTER": "0",
            "NMP_AUTHENTIK_K8S_SKIP_IMAGE_LOAD": "0",
        },
    )

    assert "Building auth-idp test image for" in output
    assert "make docker-load DOCKER_TARGET=nmp-api-docker" in output
    assert "Using prebuilt auth-idp Kubernetes test image" not in output


def test_authentik_compose_runner_reuse_uses_stable_project_and_port() -> None:
    output = _run_authentik_script("compose", "--dry-run", "--reuse")

    assert "workload-token-private-key.pem" in output
    assert "NMP_E2E_COMPOSE_LIFECYCLE=reuse" in output
    assert "NMP_AUTHENTIK_COMPOSE_PROJECT_NAME=authentik-e2e-reuse" in output
    assert "NMP_AUTHENTIK_COMPOSE_GATEWAY_PORT=18083" in output
    assert "--auth-idp-runtime authentik-compose" in output


def test_authentik_kubernetes_runner_reuse_uses_stable_cluster() -> None:
    output = _run_authentik_script("k8s", "--dry-run", "--reuse")

    assert "NMP_AUTHENTIK_K8S_CLUSTER_NAME=nmp-authentik-reuse" in output
    assert "NMP_AUTHENTIK_K8S_GATEWAY_PORT=18082" in output
    assert "NMP_AUTHENTIK_K8S_REUSE_CLUSTER=1" in output
    assert "NMP_AUTHENTIK_K8S_KEEP_CLUSTER=1" in output
    assert "--auth-idp-runtime authentik-kubernetes" in output


def test_authentik_down_cleans_reused_compose_and_kubernetes_resources() -> None:
    output = _run_authentik_script("down", "--dry-run")

    assert "docker compose down -v --remove-orphans" in output
    assert "COMPOSE_PROJECT_NAME=authentik-e2e-reuse" in output
    assert "AUTHENTIK_GATEWAY_PORT=18083" in output
    assert "AUTHENTIK_GATEWAY_TLS_VOLUME=authentik-e2e-18083-gateway-tls" in output
    assert "AUTHENTIK_WORKLOAD_NETWORK_NAME=authentik-e2e-18083-workload" in output
    assert "kind delete cluster --name nmp-authentik-reuse" in output


def test_authentik_down_accepts_kubernetes_runtime_for_reuse_cleanup() -> None:
    output = _run_authentik_script("down", "--dry-run", "--runtime", "k3d")

    assert "k3d cluster delete nmp-authentik-reuse" in output


def test_authentik_kubernetes_runner_skips_build_only_for_explicit_image() -> None:
    output = _run_authentik_script("k8s", "--dry-run", "--image", "registry.example.test/nmp-api:prebuilt")

    assert "Using prebuilt auth-idp Kubernetes test image: registry.example.test/nmp-api:prebuilt" in output
    assert "make docker-load DOCKER_TARGET=nmp-api-docker" not in output
    assert "NMP_AUTHENTIK_K8S_WORKLOAD_TOKEN_PRIVATE_KEY_FILE=" in output


def test_authentik_kubernetes_runtime_uses_provisioned_signing_key_file() -> None:
    run_sh = (AUTHENTIK_DIR / "run.sh").read_text(encoding="utf-8")
    runtime_impl = Path("tests/auth_idp/runtime_kubernetes.py").read_text(encoding="utf-8")
    helpers = (HELM_DIR / "templates" / "_helpers.tpl").read_text(encoding="utf-8")

    assert "ensure_workload_token_private_key" in run_sh
    assert "NMP_AUTHENTIK_K8S_WORKLOAD_TOKEN_PRIVATE_KEY_FILE" in run_sh
    assert "WORKLOAD_TOKEN_PRIVATE_KEY_FILE_ENV" in runtime_impl
    assert '"--set-file"' in runtime_impl
    assert "workloadTokenSigningKey.privateKeyPem=" in runtime_impl
    assert "workloadTokenSigningKey.privateKeyPem" in helpers
    assert 'genPrivateKey "rsa"' in helpers


def test_authentik_kubernetes_live_test_uses_workload_client_audience_for_subject_token() -> None:
    runtime_impl = Path("tests/auth_idp/runtime_kubernetes.py").read_text(encoding="utf-8")
    runtime_tree = ast.parse(runtime_impl)

    assert any(
        isinstance(node, ast.List)
        and any(
            isinstance(argument_node, ast.Constant)
            and argument_node.value == "--audience"
            and isinstance(value_node, ast.Name)
            and value_node.id == "WORKLOAD_CLIENT_ID"
            for argument_node, value_node in zip(node.elts, node.elts[1:])
        )
        for node in ast.walk(runtime_tree)
    )
    assert '"audience": WORKLOAD_AUDIENCE,' in runtime_impl


def test_authentik_runners_capture_ci_and_local_diagnostics() -> None:
    run_sh = (AUTHENTIK_DIR / "run.sh").read_text(encoding="utf-8")
    runtime_impl = Path("tests/auth_idp/runtime_kubernetes.py").read_text(encoding="utf-8")

    assert "diagnostics_dir()" in run_sh
    assert "prepare_diagnostics_dir()" in run_sh
    assert "write_diagnostics_metadata()" in run_sh
    assert '>"${output}/run-metadata.txt"' in run_sh
    assert "E2E_SERVICES_LOG_DIR=${diagnostics}" in run_sh
    assert "NMP_AUTHENTIK_K8S_LOG_DIR=${k8s_diagnostics}" in run_sh
    assert 'tee "${diagnostics}/pytest.log"' in run_sh
    assert "Auth-idp Compose diagnostics:" in run_sh
    assert "Auth-idp Kubernetes diagnostics:" in run_sh

    assert 'configured_dir = os.environ.get("NMP_AUTHENTIK_K8S_LOG_DIR")' in runtime_impl
    assert '"helm-status.txt"' in runtime_impl
    assert '"helm-list.txt"' in runtime_impl
    assert '"get-nodes.txt"' in runtime_impl
    assert '"get-pods-json.txt"' in runtime_impl
    assert "self._diagnostics_collected = False" in runtime_impl
    assert "def _collect_diagnostics_best_effort" in runtime_impl
    assert "with contextlib.suppress(Exception):" in runtime_impl
    assert "Collected Authentik Kubernetes diagnostics:" in runtime_impl


def test_authentik_compose_runner_uses_nemo_scoped_ca_bundle() -> None:
    run_sh = (AUTHENTIK_DIR / "run.sh").read_text(encoding="utf-8")

    assert "NMP_CLIENT_SSL_CERT_FILE=$(gateway_tls_cert_file)" in run_sh
    assert '"NMP_CLIENT_SSL_CERT_FILE=$(gateway_tls_cert_file)" \\' in run_sh
    assert "uv run --frozen pytest tests/auth_idp/contracts" in run_sh
    assert "--auth-idp-runtime authentik-compose" in run_sh
    assert "-m auth_idp_runtime" in run_sh
    stripped_lines = [line.strip() for line in run_sh.splitlines()]
    assert not any(line.startswith('SSL_CERT_FILE="$(gateway_tls_cert_file)"') for line in stripped_lines)
    assert not any(line.startswith('REQUESTS_CA_BUNDLE="$(gateway_tls_cert_file)"') for line in stripped_lines)


def test_authentik_umbrella_values_configure_workload_token_tls() -> None:
    values = _load_yaml(HELM_DIR / "values.yaml")
    tls_values = values["workloadTokenTls"]
    nemo_values = values["nemo-platform"]
    tls_template = (HELM_DIR / "templates" / "workload-token-tls.yaml").read_text(encoding="utf-8")
    helpers_template = (HELM_DIR / "templates" / "_helpers.tpl").read_text(encoding="utf-8")

    assert tls_values["create"] is True
    assert tls_values["secretName"] == "nemo-platform-envoy-tls"
    assert tls_values["durationDays"] == 365
    assert tls_values["mountPath"] == "/etc/nmp/workload-token-tls"
    assert tls_values["caBundleFile"] == "/etc/nmp/workload-token-ca/ca.crt"
    assert tls_values["dnsNames"] == ["localhost"]
    assert "127.0.0.1" in tls_values["ipAddresses"]
    assert "selfSignedIssuerName" not in tls_values
    assert "caIssuerName" not in tls_values
    assert "caSecretName" not in tls_values
    assert "type: kubernetes.io/tls" in tls_template
    assert 'define "nemo-platform-authentik.serviceDnsNames"' in helpers_template
    assert 'include "nemo-platform-authentik.serviceDnsNames"' in tls_template
    assert ".Values.integration.nemoPlatform.envoyServiceName" in tls_template
    assert "$nemoPlatformValues.envoyProxy.serviceNamespace" in tls_template
    assert 'include "nemo-platform-authentik.existingSecretData"' in tls_template
    assert "genSignedCert" in tls_template
    assert "kind: Issuer" not in tls_template
    assert "kind: Certificate" not in tls_template
    assert "cert-manager.io/v1" not in tls_template
    assert nemo_values["envoyProxy"]["extraVolumes"] == [
        {"name": "tmp", "emptyDir": {}},
        {"name": "workload-token-tls", "secret": {"secretName": "nemo-platform-envoy-tls"}},
    ]
    assert nemo_values["envoyProxy"]["extraVolumeMounts"] == [
        {"name": "tmp", "mountPath": "/tmp"},
        {"name": "workload-token-tls", "mountPath": "/etc/nmp/workload-token-tls", "readOnly": True},
    ]
    assert nemo_values["core"]["controller"]["env"] == {
        "NMP_PLATFORM_URL": ENVOY_CONTROLLER_ENV_URL,
        "NMP_AUTH_URL": ENVOY_CONTROLLER_ENV_URL,
    }
    assert nemo_values["platformConfig"]["jobs"]["executor_defaults"]["kubernetes_job"]["env"] == {
        "SSL_CERT_FILE": "/etc/nmp/workload-token-ca/ca.crt",
        "REQUESTS_CA_BUNDLE": "/etc/nmp/workload-token-ca/ca.crt",
    }
    assert "service_discovery" not in nemo_values["platformConfig"]["jobs"]["executor_defaults"]["kubernetes_job"]
    assert nemo_values["platformConfig"]["jobs"]["executor_defaults"]["kubernetes_job"]["storage"] == {
        "additional_volumes": [
            {
                "name": "workload-token-tls-ca",
                "secret": {
                    "secret_name": "nemo-platform-envoy-tls",
                    "items": [{"key": "ca.crt", "path": "ca.crt"}],
                },
            }
        ],
        "additional_volume_mounts": [
            {
                "name": "workload-token-tls-ca",
                "mount_path": "/etc/nmp/workload-token-ca",
                "read_only": True,
            }
        ],
    }
    workload_executor = next(
        executor
        for executor in nemo_values["platformConfig"]["jobs"]["executors"]
        if executor["provider"] == "cpu" and executor["profile"] == "workload"
    )
    workload_config = workload_executor["config"]
    assert workload_config["launcher_image"] == '{{ include "nmp-core.image" . }}'
    assert "default_task_image" not in workload_config
    assert "service_discovery" not in workload_config
    assert workload_config["env"] == {
        "SSL_CERT_FILE": "/etc/nmp/workload-token-ca/ca.crt",
        "REQUESTS_CA_BUNDLE": "/etc/nmp/workload-token-ca/ca.crt",
    }
    expected_storage = nemo_values["platformConfig"]["jobs"]["executor_defaults"]["kubernetes_job"]["storage"]
    assert workload_config["storage"] == expected_storage
    assert not any(
        executor["provider"] == "gpu_distributed" and executor["profile"] == "default"
        for executor in nemo_values["platformConfig"]["jobs"]["executors"]
    )


def test_nemo_platform_seed_hook_uses_internal_api_service_url() -> None:
    template = Path("k8s/helm/templates/platform-seed-job.yaml").read_text(encoding="utf-8")

    assert "- name: NMP_BASE_URL" in template
    assert 'include "nemo-platform.internalBaseUrl"' in template


def test_nemo_platform_controller_uses_internal_api_service_url_for_embedded_pdp() -> None:
    template = Path("k8s/helm/templates/core/controller-deployment.yaml").read_text(encoding="utf-8")

    assert "- name: NMP_BASE_URL" in template
    assert "- name: NMP_AUTH_POLICY_DECISION_POINT_BASE_URL" in template
    assert (
        "name: NMP_AUTH_POLICY_DECISION_POINT_BASE_URL\n"
        '              value: {{ include "nemo-platform.internalBaseUrl" . | quote }}'
    ) in template


def test_nemo_platform_api_uses_internal_api_service_url_for_agent_configs() -> None:
    """NMP_BASE_URL on the API pod must be the Service address, never loopback.

    The API copies this value into agent workflow configs, which run in a different
    container -- loopback there resolves to the agent itself, not the platform.
    Embedded PDP gets its loopback from NMP_AUTH_POLICY_DECISION_POINT_BASE_URL instead.
    """
    template = Path("k8s/helm/templates/api/api-deployment.yaml").read_text(encoding="utf-8")

    assert (
        'name: NMP_BASE_URL\n              value: {{ include "nemo-platform.internalBaseUrl" . | quote }}'
    ) in template
    assert "nemo-platform.apiLoopbackBaseUrl" not in template.split("NMP_AUTOMODEL")[0]
    assert (
        "name: NMP_AUTH_POLICY_DECISION_POINT_BASE_URL\n              value: "
        '{{ include "nemo-platform.apiLoopbackBaseUrl" . | quote }}'
    ) in template


def test_authentik_helm_demo_does_not_inject_legacy_workload_token_envs() -> None:
    template_files = sorted(path for path in (HELM_DIR / "templates").rglob("*") if path.is_file())
    text_files = [
        HELM_DIR / "values.yaml",
        *template_files,
        AUTHENTIK_DIR / "run.sh",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in text_files)

    assert "NEMO_WORKLOAD_TOKEN" not in combined
    assert "NEMO_WORKLOAD_TOKEN_FILE" not in combined
    assert WORKLOAD_IDENTITY_TOKEN_FILE_ENVVAR not in combined
