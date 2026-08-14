---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
description: Run pre-commit hooks
---
Run all pre-commit hooks in repository to lint

* Do so with `uv run pre-commit run -a`
* Do this to both lint and fix formatting of files
* A clean run means nothing was updated.
* Ty checks may have to be fixed manually
