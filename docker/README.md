# Docker Builds

Dockerfiles and Docker build support files live under this directory. The
canonical Buildx Bake file is `docker-bake.hcl`.

Examples:

```bash
docker buildx bake --print docker-cpu
docker buildx bake --print nmp-automodel
docker buildx bake --print nmp-unsloth
```
