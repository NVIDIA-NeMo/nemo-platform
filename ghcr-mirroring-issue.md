# Mirror all public NeMo Platform images from NVCR to GHCR

We already publish NeMo Platform images to `nvcr.io`. We should mirror all current public images to `ghcr.io` so GitHub becomes the primary public distribution path for OSS consumers.

## Context

- NeMo Platform is already hosted on GitHub, so GHCR provides the most straightforward OSS distribution experience.
- GHCR meets our current requirements for public distribution, including image size and acceptable rate-limit characteristics.
- GHCR avoids the extra operational and publishing-process friction associated with NVIDIA public NVCR distribution.
- This work does not replace NVCR. It adds GHCR as a mirrored public distribution path.
- NVCR public may still be useful later, but we want to avoid taking on additional process overhead at the initial stage.

## Scope

- Identify all currently public NeMo Platform images published to `nvcr.io`
- Mirror those images to `ghcr.io`
- Preserve tags and digests where possible
- Evaluate and choose an implementation approach using either `skopeo` or `regsync`
- Document the mirroring workflow and the source-of-truth image list
- Validate that mirrored images can be pulled anonymously from GHCR

## Out of scope

- Replacing NVCR as an existing publish target
- Reworking image contents or build pipelines beyond what is needed to support mirroring
- Adding NVIDIA public-registry publishing workflow changes

## Acceptance criteria

- All currently public NeMo Platform images available in `nvcr.io` are also available in `ghcr.io`
- Tags are mirrored correctly
- Anonymous pull from GHCR works for all mirrored images
- The mirroring approach is documented, including how new images/tags should be synchronized going forward
- A clear decision is recorded on whether `skopeo` or `regsync` is the long-term sync mechanism

## Suggested priority

High
