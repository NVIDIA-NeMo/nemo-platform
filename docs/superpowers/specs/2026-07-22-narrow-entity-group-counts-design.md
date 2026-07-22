# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Narrow Entity Group Counts

## Goal

Count child entities for several parents in one request without fetching every
matching entity. Current uses are Experiment Groups by `insight_id` and
Evaluations by `experiment_group_id`.

## API

Keep grouped counts as optional metadata on the existing entity-list endpoint:

```text
GET .../entities/{entity_type}?count_by=data.{field}&filter=...
```

When `count_by` is absent, list behavior is unchanged. When present,
`group_counts` maps each observed string value to its matching entity count.
Missing values are not returned.

Expose the narrow client method:

```python
await entity_client.count_by(
    entity_type,
    field,
    workspace=workspace,
    filter_obj=filter_obj,
)
```

The client accepts one direct entity data field and adds the `data.` prefix.
It does not accept base fields, nested paths, filter strings, or filter
operation objects.

## Repository

Reuse existing workspace authorization and filter application. Accept only a
`data.<field>` path with exactly one segment below `data`, and include only
string values. Ignore missing, JSON-null, boolean, numeric, array, and object
values. Keep the 1,000-group bound. The endpoint returns HTTP 400 for an
unsupported field or bound overflow.

The list-endpoint integration intentionally retains its normal page and total
queries. A dedicated count endpoint is excluded because it increases API and
SDK surface beyond the current need.

## Scope Control

Remove support and tests for base-column grouping, nested JSON paths, boolean
and numeric normalization, and expanded client base-field mappings. Avoid
refactoring existing list/filter behavior solely to share code with
`count_by`.

Test only the client request mapping, filtered direct-string grouping,
unsupported group fields, cardinality overflow, and endpoint response wiring.
