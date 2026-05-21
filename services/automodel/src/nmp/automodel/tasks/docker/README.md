# File I/O Task Docker Testing

Scripts for running the file_io task container locally.

## Prerequisites

1. **Build the Docker image** from the repository root:
This will build `my-registry/nmp-cpu-tasks:local` image that will be used for this task.

   ```bash
   cd /path/to/nmp
   make docker/nmp-cpu-tasks
   ```

2. **Have NeMo Platform running** (files service) at `http://localhost:8080`

## Quick Start

### Run with Docker Compose

```bash
cd services/customizer/src/nmp/customizer/tasks/file_io/docker

# Run the task
docker compose up

# Run with custom image
FILE_IO_IMAGE=my-registry/nmp-cpu-tasks:dev docker compose up

# Run interactively
docker compose run --rm file-io run task --task nmp.customizer.tasks.file_io
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
| `FILE_IO_IMAGE` | Docker image to use | `my-registry/nmp-cpu-tasks:local` |

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
