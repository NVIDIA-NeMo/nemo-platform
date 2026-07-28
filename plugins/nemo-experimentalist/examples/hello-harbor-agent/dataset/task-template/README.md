<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# task-template

The shape the Eval Author clones when it turns a production trace into a new
Harbor task (Mode 1, `--insight`). It is a complete, runnable task in its own
right — a copy of `train/greet-world` — so `nemo experimentalist doctor` can
validate it.

Mode 2 (`--no-insight`, what the debug launch configs use) never reads this
directory, but the profile schema still requires `task_template` to be set.

Note the name: `HarborDataset._find_task_dirs` skips a directory literally named
`task_template`, so a template nested inside a dataset is not picked up as a
task. This one lives outside `train/` and `validation/`, so either name works.
