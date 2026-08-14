---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

description: Resolves `reviewme_` tags in the @sdk/openapi.stainless.yaml file
argument-hint: [additional instructions (optional)]
---
Your task is to resolve any `reviewme_` tags in the @sdk/openapi.stainless.yaml file.

These tags are provided by the tool that maps the OpenAPI spec to Stainless config, and in some cases, it cannot determine the correct mapping automatically.
To resolve these tags, follow these steps:
1. Open the @sdk/openapi.stainless.yaml file and search for any instances of `reviewme_` tags.
2. For each `reviewme_` tag found, analyze the context and determine the appropriate value or configuration that should replace the tag.
3. Update the `reviewme_` tag with the correct value or configuration.
4. Save the changes to the @sdk/openapi.stainless.yaml file.
5. Verify that the changes are correct and that there are no remaining `reviewme_` tags in the file.

Here are crucial guidelines to follow while resolving the `reviewme_` tags:
- only update the method and model names.
- never update the API paths or API schemas, these need to match with the OpenAPI spec exactly.
- some subresources will have only a single method, in some of these cases we will want to bump that method to the parent resource instead, with name like "verb_noun" (e.g. "get_logs").
  - resources in this category include: logs, status.
- if unsure about how to resolve a specific `reviewme_` tag, ask the user for input before continuing further.

Once completed, present the user with a summary of changes. This summary may be useful to include in the commit message when committing the updated file.

$ARGUMENTS