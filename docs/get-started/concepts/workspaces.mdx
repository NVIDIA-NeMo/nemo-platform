<a id="workspaces"></a>
# Workspaces

Workspaces are the fundamental organizational and authorization boundary in {{platform_name}}. All platform resources—models, datasets, customization jobs, evaluation results, and more—must belong to a workspace.

When authentication is enabled, users are granted roles (Viewer, Editor, or Admin) within specific workspaces, and all resources within a workspace inherit its access controls.

Create separate workspaces when you need true isolation—for example, to separate teams (`team-ml-research`, `team-nlp`), individual users (`user-jsmith`), environments (`dev`, `staging`, `production`), or clients (`client-acme`). For lighter-weight organization within a workspace that does not require access separation, use projects.

## Built-in Workspaces

The platform automatically creates two built-in workspaces during initialization:

- **`default`** — General-purpose workspace for experimentation, editable by all authenticated users.
- **`system`** — Reserved for platform-provided resources (for example, evaluation targets, customization templates). Read-only for regular users; only platform administrators can modify.

## Create a Workspace

To create a workspace, provide a `name` and optionally a `description`. The `name` must be unique within your deployment.

--8<-- "_snippets/naming-rules.md"

Once created, a workspace cannot be renamed—choose the `name` carefully. The `description` is a free-form text field to help identify the workspace's purpose.

The system also generates a unique `id` (UUID) for internal use, but the `name` is the primary identifier used in API paths and SDK calls.


=== "Python SDK"

    ```python
    import os
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )

    workspace = client.workspaces.create(
        name="ml-team", description="Machine Learning Team workspace"
    )
    ```

=== "CLI"

    ```bash
    nemo workspaces create ml-team \
        --description "Machine Learning Team workspace"
    ```

## List Workspaces

To list workspaces, call the list endpoint. When authentication is enabled, only workspaces the user has access to are returned. The response includes pagination metadata.


=== "Python SDK"

    ```python
    import os
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )

    response = client.workspaces.list()
    for workspace in response.data:
        print(f"{workspace.name}: {workspace.description}")
    ```

=== "CLI"

    ```bash
    nemo workspaces list
    ```

## Get a Workspace

To retrieve a specific workspace by its `name`:


=== "Python SDK"

    ```python
    import os
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )

    workspace = client.workspaces.retrieve("ml-team")
    ```

=== "CLI"

    ```bash
    nemo workspaces get ml-team
    ```

## Update a Workspace

To update a workspace, only the `description` field can be modified. The `name` cannot be changed after creation.


=== "Python SDK"

    ```python
    import os
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )

    workspace = client.workspaces.update(
        "ml-team", description="Updated: ML Team workspace for model development"
    )
    ```

=== "CLI"

    ```bash
    nemo workspaces update ml-team \
    --description "Updated: ML Team workspace for model development"
    ```

## Delete a Workspace

Deleting a workspace removes the workspace and all of its resources (jobs, deployments, filesets, role bindings, and other entities). The API returns immediately after revoking access, and an asynchronous cleanup controller handles deletion of the remaining resources in the background.

During cleanup, the workspace is no longer visible to users. If cleanup fails, the workspace enters a `FAILED` state that requires administrator attention.


=== "Python SDK"

    ```python
    import os
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )

    client.workspaces.delete("ml-team")
    ```

=== "CLI"

    ```bash
    nemo workspaces delete ml-team
    ```
