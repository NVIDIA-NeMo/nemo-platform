<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# FileQuickActions

Router-agnostic quick actions menu for dataset files.

## Features

- Download file
- Rename file
- Delete file
- Create split
- Transform file
- View JSON (optional, only shown if callback provided)

## Usage

### With View Callback

```typescript
import { FileQuickActions } from '@studio/components/FilesTable/FileQuickActions';

<FileQuickActions
  datasetId="default/my-dataset"
  file={fileObject}
  currentFolder="training"
  onViewFile={(filePath) => {
    // Handle file view (navigate or open panel)
    console.log('View file:', filePath);
  }}
/>
```

### Without View Callback

```typescript
// "View JSON" action will not be shown
<FileQuickActions
  datasetId="default/my-dataset"
  file={fileObject}
  currentFolder="training"
/>
```

## Props

| Prop            | Type                         | Required | Description                           |
| --------------- | ---------------------------- | -------- | ------------------------------------- |
| `datasetId`     | `string`                     | No       | Dataset ID (namespace/name)           |
| `file`          | `FileSystemFile`             | Yes      | File to perform actions on            |
| `currentFolder` | `string \| undefined`        | No       | Current folder path                   |
| `onViewFile`    | `(filePath: string) => void` | No       | Callback when user wants to view file |

## Router Independence

This component has **no router dependencies**:

- **No** `useNavigate()`
- **No** `useWorkspaceFromPath()`
- **No** `useQueryParams()`

All navigation is handled via the optional `onViewFile` callback.

## Actions

| Action       | Always Shown | Requires                          |
| ------------ | ------------ | --------------------------------- |
| Download     | Yes          | -                                 |
| Rename       | Yes          | -                                 |
| Delete       | Yes          | -                                 |
| Create Split | Yes          | -                                 |
| Transform    | Yes          | -                                 |
| View JSON    | No           | `onViewFile` callback + JSON file |

The "View JSON" action only appears when:

1. The `onViewFile` callback is provided
2. The file is a JSON file (`.json` or `.jsonl`)
