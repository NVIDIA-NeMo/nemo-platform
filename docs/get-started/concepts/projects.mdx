<a id="entities-projects-overview"></a>
# Projects

Projects are optional organizational tags within a workspace. They let you group related resources—such as datasets, customization jobs, and evaluation results—without creating separate access boundaries. Anyone with access to the workspace can see all its projects.

Use projects when you need to organize related work within a team. For example, group everything related to a fine-tuning experiment (`llama-3-customer-support-v2`) or an evaluation campaign (`quarterly-eval-2025q1`). For access isolation between teams or environments, use separate workspaces instead.

## Project vs. Workspace

| Need | Solution |
|------|----------|
| Separate teams or users | Different workspaces |
| Separate environments (dev/prod) | Different workspaces |
| Group related work | Project within a workspace |
| Quick one-off task | Workspace only, no project |

Think of workspaces as filing cabinets (separate, locked) and projects as labels you can apply to documents within a cabinet.

## Create a Project

To create a project, provide a `name` and optionally a `description`. The `name` must be unique within the workspace.

--8<-- "_snippets/naming-rules.md"

Once created, a project cannot be renamed.


=== "Python SDK"

    ```python
    import os
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )

    project = client.projects.create(
        workspace="ml-team",
        name="llama-finetune-v2",
        description="Fine-tuning experiment for customer support",
    )
    ```

=== "CLI"

    ```bash
    nemo projects create \
        --workspace ml-team \
        --name llama-finetune-v2 \
        --description "Fine-tuning experiment for customer support"
    ```

## List Projects

To list projects in a workspace, call the list endpoint. The response includes pagination metadata.


=== "Python SDK"

    ```python
    import os
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )

    response = client.projects.list(workspace="ml-team")
    for project in response.data:
        print(f"{project.name}: {project.description}")
    ```

=== "CLI"

    ```bash
    nemo projects list --workspace ml-team
    ```

## Get a Project

To retrieve a specific project by its `name`:


=== "Python SDK"

    ```python
    import os
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )

    project = client.projects.retrieve("llama-finetune-v2", workspace="ml-team")
    ```

=== "CLI"

    ```bash
    nemo projects get llama-finetune-v2 --workspace ml-team
    ```

## Update a Project

To update a project, only the `description` field can be modified. The `name` cannot be changed after creation.


=== "Python SDK"

    ```python
    import os
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )

    project = client.projects.update(
        "llama-finetune-v2",
        workspace="ml-team",
        description="Updated: Fine-tuning experiment for customer support chatbot",
    )
    ```

=== "CLI"

    ```bash
    nemo projects update llama-finetune-v2 \
        --workspace ml-team \
        --description "Updated: Fine-tuning experiment for customer support chatbot"
    ```

## Delete a Project

To delete a project:


=== "Python SDK"

    ```python
    import os
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )

    client.projects.delete("llama-finetune-v2", workspace="ml-team")
    ```

=== "CLI"

    ```bash
    nemo projects delete llama-finetune-v2 --workspace ml-team
    ```
