## Problem Statement

NeMo Platform needs a distribution strategy for large public OSS container images. The core problem is that the preferred distribution path should allow community users to pull images with minimal friction, while still supporting image sizes that are common for AI workloads.

This document compares candidate registries and distribution models against the constraints that matter for public OSS distribution:

- Support for large images and layers
- Anonymous or low-friction public pulls
- Public pull rate limits and throttling risk
- Operational overhead for publishing and maintenance
- Fit for NVIDIA-owned versus community-oriented distribution

One important clarification up front: **GitHub Container Registry (`ghcr.io`) does not impose a 10 GB total image size limit for public OSS images.** The practical constraint is a **10 GB per-layer limit**, plus upload timeout behavior. That means GHCR remains viable if the image can be structured into multiple smaller layers.

The sections below outline the main options and the tradeoffs each one introduces.

---

## 1. Optimize GitHub Container Registry (GHCR)

If your total image is over 10 GB, but no *single* layer is over 10 GB, **GHCR is free and unlimited for public open-source projects.** The trick to working around the 10 GB layer cap and the 10-minute timeout is to modify your `Dockerfile` structure to force multi-layer chunking:

- **Avoid single-layer giants:** Don't do `RUN wget <huge-model> && pip install <everything> && apt install <everything>` in one command.
- **Break up heavy copy/run operations:** Group your dependencies, weights, or datasets into separate `RUN` or `COPY` steps so Docker naturally creates smaller individual layers.
- **Rate-limit profile:** GitHub's public documentation for `ghcr.io` does not prominently document a Docker Hub-style anonymous pull cap for public container pulls. The practical constraints called out in the reviewed docs are cost/bandwidth policy for public packages and the 10 GB per-layer limit, rather than a published public pull quota.

---

## 2. Docker Hub (Public / Open Source Program)

Docker Hub is still the default for most developers. It allows **anonymous, keyless public pulls**, meaning your users just type `docker pull your-org/image` and it works out of the box.

- **Size Limits:** There is no hard cap on overall image size, though a single layer is typically capped around 10 GB (similar to GitHub).
- **Rate-limit profile:** Docker Hub is the clearest case where public pull rate limits matter. Anonymous users are rate-limited, which can become a real problem for shared NATs, CI fleets, classrooms, and enterprise users pulling from the same egress IP range. The **Docker Open Source Program** materially improves this story by reducing that friction for OSS consumers.

---

## 3. Hugging Face Spaces / Registry

Hugging Face has become the definitive home for open-source AI, and they fully support custom Docker containers.

- **How it works:** Instead of standard OCI registries, you can use Hugging Face **Docker Spaces**. You provide a `Dockerfile`, and Hugging Face handles the building and hosting.
- **The AI Advantage:** If your image is massive because it contains model weights, Hugging Face lets you easily decouple the container logic from the data. You can keep the Docker image small and use the `huggingface_hub` cache to pull weights from an HF Model Repo seamlessly at runtime. It completely eliminates key requirements for end-users.
- **Rate-limit profile:** Hugging Face does enforce documented Hub rate limits, including anonymous-user limits, but it also distinguishes between request classes and gives much higher limits to optimized file-resolution traffic than to general API usage. For model and artifact delivery this is generally more AI-friendly than Docker Hub's anonymous pull throttling, but it is still an explicit quota system.

---

## 4. Quay.io (By Red Hat)

Quay is highly resilient, supports incredibly large images, and is a popular alternative to Docker Hub for large enterprise open-source projects (like many CNCF projects).

- **Pros:** Public repositories are completely free, unmetered, and allow anonymous public pulling without any keys.
- **Cons:** The UI feels a bit dated compared to GitHub or Hugging Face, but its backend handles massive OCI images flawlessly.
- **Rate-limit profile:** Quay is attractive partly because it is commonly used as a public OSS registry without the same well-known anonymous pull caps that shape Docker Hub decisions. For this document, the key point is that Quay is generally positioned as the lower-friction option when rate-limit sensitivity is a concern.

## 5. NVCR / NGC

NVCR is the most natural NVIDIA-native option, but it really splits into two different distribution models:

- **Private NVCR registry:** This works well if you are distributing images to known internal or partner users, but it requires consumers to authenticate with an NGC API key. That makes it a poor fit for frictionless public OSS distribution, because every user has to clear the NGC account + key setup hurdle before they can even pull the image.
- **NVIDIA public registry path:** NVIDIA can publish public images without requiring end users to bring a key, but getting there means going through NVIDIA's public publishing process. In practice, that process is much more extensive than pushing to GHCR, Docker Hub, or Quay, so it adds significant operational overhead for a community-facing OSS image.
- **Rate-limit profile:** Rate limiting is less central than access model here. The private path is already gated behind NGC authentication, while the public path is governed more by NVIDIA's publishing workflow and policy overhead than by a community-friendly self-serve pull model.

---

## Summary: Which should you choose?


| Registry                     | Max Image Size                   | Needs Pull Key?            | Public Pull Rate Limits                                  | Best For...                                                                                              |
| ---------------------------- | -------------------------------- | -------------------------- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| **GHCR (GitHub)**            | Unlimited (Max 10GB *per layer*) | **No** (for public images) | No prominently documented anonymous pull cap reviewed    | Keeping code and containers in the exact same GitHub Org.                                                |
| **Docker Hub**               | Unlimited                        | **No**                     | Significant for anonymous users                          | Maximum community discoverability, if you can tolerate or mitigate anonymous pull throttling.            |
| **Hugging Face**             | High / Flexible                  | **No**                     | Yes, explicit Hub quotas; more favorable for file fetches | AI-native workflows where you want to split infrastructure from model weights.                           |
| **Quay.io**                  | Unlimited for OSS                | **No**                     | Lower-friction OSS posture; no comparable cap highlighted | Heavy-duty, keyless enterprise open-source hosting.                                                      |
| **NVCR (Private)**           | Unlimited                        | **Yes** (NGC API key)      | Less relevant than auth gating                           | NVIDIA-internal or controlled distribution where authenticated pulls are acceptable.                     |
| **NVCR (Public Publishing)** | Unlimited                        | **No** (for end users)     | Not the primary issue; process overhead dominates        | NVIDIA-managed public distribution, if you are willing to go through the full public publishing process. |


### The Recommendation

NeMo Platform should use **GitHub Container Registry (`ghcr.io`) as the primary public distribution path** for OSS images.

This is the strongest default choice for the current stage of the project because:

- NeMo Platform is already hosted on GitHub, so GHCR keeps source and container distribution in the same ecosystem.
- It provides the most straightforward public OSS user experience: users can discover the project on GitHub and pull the corresponding images without additional NVIDIA-specific account setup.
- It meets the key technical criteria outlined in this document, including image-size viability and an acceptable public rate-limit profile for OSS distribution.
- It avoids the additional publishing-process friction associated with NVIDIA's public NVCR path.

This recommendation does **not** rule out also publishing through **NVCR public** in the future. That path may still be useful if there is a strategic reason to maintain a public NVIDIA-native distribution channel. However, at the initial stage, NeMo Platform should avoid taking on the additional operational overhead of the NVCR public publishing process when GHCR already satisfies the project’s functional and distribution requirements.
