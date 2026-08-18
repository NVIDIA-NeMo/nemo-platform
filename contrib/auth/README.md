<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Identity Provider References

This directory contains NeMo Platform identity-provider reference bundles.

Each provider bundle defines one contract for local validation and production
adaptation:

- expose OIDC discovery metadata
- include a gateway layer that strips inbound `X-NMP-Principal-*` headers
- define one human identity and one machine identity for shared auth testing
- treat external machine identities as ordinary OIDC principals authorized by
  group binding, not as internal `service:*` principals
- document provider-specific setup in a local `README.md`

Open-source providers with `mode: compose-ci` are intended for the shared auth
matrix. Reference-only providers stay documented and manifest-driven but are
excluded from the local Compose-backed matrix.
