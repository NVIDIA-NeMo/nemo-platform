<a id="data-designer-execution-modes"></a>
# Execution Modes

After building Data Designer configurations with the library's `data_designer.config` APIs, you choose where the NeMo Data Designer plugin executes the workload.

The important distinction is not simply "local" versus "remote". There are two separate questions:

| Axis | Question | Examples |
|------|----------|----------|
| **Execution location** | Where does the Data Designer workload run? | In the local CLI process with `run`, or in NeMo Services with `submit` or the SDK. |
| **Resource backend** | What does the configuration depend on? | Local files, local provider settings, environment variables, or NeMo resources such as Filesets, Secrets, and Inference Gateway providers. |

`run` versus `submit` primarily controls where the plugin workload execution happens. It does not necessarily determine whether the workload uses NeMo Services APIs.

!!! note
    `nemo data-designer ... run` can be fully local, but it is not an offline-only mode. A local run can still use the Files API, Secrets API, and Inference Gateway API from a running NeMo Services cluster when the configuration references the corresponding resources.

## Terms

| Term | Meaning |
|------|---------|
| **Local execution** | The Data Designer workload runs in the CLI process. |
| **Local resources** | The configuration uses local files, local provider settings, environment variables, or other resources available to the CLI process. |
| **NeMo resources** | The configuration uses resources in NeMo Services, such as Filesets, Secrets, or Inference Gateway providers. |
| **NeMo Services execution** | The Data Designer workload runs through the Data Designer API or a Jobs worker. |
| **Local NeMo Services deployment** | NeMo Services are running on your machine. This is still NeMo Services execution when you use `submit` or the SDK. |

## Execution Surfaces

| Interface | Workload execution | NeMo Services required? | Resource behavior |
|-----------|--------------------|-------------------------|-------------------|
| `nemo data-designer preview run` | Local CLI process | Optional | Can use local resources and/or NeMo resources. |
| `nemo data-designer create run` | Local CLI process | Optional | Can use local resources and/or NeMo resources. |
| `nemo data-designer preview submit` | Data Designer API | Yes | Uses resources supported by NeMo Services. |
| `nemo data-designer create submit` | Jobs worker | Yes | Uses resources supported by NeMo Services and job artifact storage. |
| `client.data_designer.preview/create` | Data Designer API or Jobs worker | Yes | Local SDK execution is planned but not available yet. |

## Resource Compatibility

Local CLI execution supports the broadest set of resource patterns because the workload runs in your Python environment.

| Resource type | CLI `run` | CLI `submit` / SDK today |
|---------------|-----------|--------------------------|
| Local seed files or DataFrames | Supported | Not supported; upload to Filesets first. |
| HuggingFace seed datasets | Supported | Supported. |
| Files API Filesets | Supported when NeMo Services access is configured | Supported. |
| Local provider settings | Supported | Not supported; use Inference Gateway providers. |
| Inference Gateway providers | Supported when NeMo Services access is configured | Supported. |
| Environment or plaintext secrets | Supported | Not supported; use Secrets API secrets. |
| Secrets API secrets | Supported when NeMo Services access is configured | Supported. |

## Choosing a Mode

Use CLI `run` when you want fast local iteration, direct access to local files, or library-equivalent workload behavior.

Use CLI `submit` when you want service-managed execution, job lifecycle tracking, shared artifacts, or the same execution environment other users and automation will use.

Use the SDK when you are writing application code that should call the Data Designer API programmatically. Today, the SDK path exclusively uses NeMo Services; use CLI `run` for local in-process execution.

If you run NeMo Services fully locally, `submit` and SDK calls can target that local deployment. The services are local, but the workload execution path still uses the Data Designer API and Jobs API.

## Local NeMo Services Execution

To use `submit` or the SDK against a local NeMo Services deployment, run the services locally:

```bash
nemo services run
```

Run this from an environment with the service components and the Data Designer plugin installed. In another terminal, run `nemo setup` or `nemo setup --auto` to register your provider, then use `preview submit`, `create submit`, or the SDK against `http://localhost:8080`.
