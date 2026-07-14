# File I/O Task Docker Testing

Scripts for running the file_io task container locally.

## Prerequisites

1. **Build the Docker image** from the repository root:

   ```bash
   cd /path/to/nemo-platform
   docker buildx bake -f docker-bake.hcl nmp-customizer-tasks
   ```

2. **Have NeMo Platform running** (files service) at `http://localhost:8080`

## Quick Start

### Run with Docker Compose

```bash
cd services/automodel/src/nmp/automodel/tasks/docker

# Run the task
docker compose up

# Run with custom image
FILE_IO_IMAGE=my-registry/nemo-platform-dev/nmp-customizer-tasks:dev docker compose up

# Run interactively
docker compose run --rm file-io -m nmp.customization_common.tasks.file_io --service-source automodel --service-name customizer
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NMP_BASE_URL` | Base URL for NeMo Platform | `http://host.docker.internal:8000` |
| `NMP_FILES_URL` | Files service URL | `http://host.docker.internal:8000` |
| `NMP_JOBS_URL` | Jobs service URL (for progress) | `http://host.docker.internal:8000` |
| `NEMO_JOB_ID` | Job identifier | `test-file-io-job` |
| `NEMO_JOB_STEP` | Step name | `FileIO` |
| `NEMO_JOB_TASK` | Task identifier | `file-io-task` |
| `NEMO_JOB_WORKSPACE` | Workspace name | `default` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `FILE_IO_IMAGE` | Docker image to use | `my-registry/nemo-platform-dev/nmp-customizer-tasks:local` |

### Config File Format

The `sample_config.json` defines what files to upload/download:

```json
{
    "upload": [
        {
            "src": "local_folder",
            "dest": "workspace/fileset-name"
        }
    ],
    "download": [
        {
            "src": "workspace/fileset-name", 
            "dest": "local_folder"
        }
    ]
}
```

- `upload[].src`: Path relative to job storage defined by NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH (mounted at `/var/run/scratch`)
- `upload[].dest`: Target FileSet in format `workspace/fileset-name`
- `download[].src`: Source FileSet in format `workspace/fileset-name`
- `download[].dest`: Path relative to job storage defined by NEMO_JOB_PERSISTENT_JOB_STORAGE_PATH

## Next Steps

- **[`nmp-customizer-tasks` image build & runtime](../../../../../../../docker/automodel/README.md)** — bake targets, workspace slice, and smoke commands for the shared CPU image.
- **[Automodel job compiler](../../app/jobs/compiler.py)** — how download / upload / model-entity steps are compiled onto `nmp-customizer-tasks` with `--service-source automodel --service-name customizer`.
- **[Shared customization task runners](../../../../../../../packages/nmp_customization_common/README.md)** — `nmp.customization_common.tasks.file_io` and `model_entity` (used by automodel, unsloth, and rl).
- **[`nmp-automodel` service overview](../../../../../README.md)** — package layout, training image, and plugin integration.
- **[Customizer docs](../../../../../../../docs/customizer/index.mdx)** — published container images and the end-to-end fine-tuning workflow on the platform.

