<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# DatasetFileManagementSidePanel

Router-independent component for managing dataset files.

## Features

- Browse files and folders
- Upload files with drag-and-drop
- Search across all files
- Bulk operations (select all, delete)
- Folder navigation with breadcrumbs

## Usage

```typescript
import { DatasetFileManagementSidePanel } from '@studio/components/DatasetFileManagementSidePanel';

const MyComponent = () => {
  const [open, setOpen] = useState(true);
  const [folder, setFolder] = useState<string | null>(null);
  return (
    <DatasetFileManagementSidePanel
      open={open}
      namespace="default"
      datasetName="my-dataset"
      datasetId="default/my-dataset"
      currentFolder={folder}
      filesList={filesList}
      isLoading={isLoading}
      isFilesFetching={isFetching}
      onFolderChange={setFolder}
      onFileSelect={(filePath) => console.log('Selected:', filePath)}
      onClose={() => setOpen(false)}
      onOpenChange={(isOpen) => {
        if (!isOpen) {
          console.log('Panel closed');
        }
      }}
    />
  );
};
```

## Props

| Prop              | Type                           | Required | Description                                 |
| ----------------- | ------------------------------ | -------- | ------------------------------------------- |
| `open`            | `boolean`                      | Yes      | Whether the panel is open                   |
| `namespace`       | `string`                       | Yes      | Dataset namespace                           |
| `datasetName`     | `string`                       | Yes      | Dataset name                                |
| `datasetId`       | `string`                       | Yes      | Full dataset ID (namespace/name)            |
| `currentFolder`   | `string \| undefined`          | No       | Current folder path (or undefined for root) |
| `filesList`       | `FileSystemNode[]`             | No       | All files in dataset                        |
| `isLoading`       | `boolean`                      | Yes      | Whether data is loading                     |
| `isFilesFetching` | `boolean`                      | Yes      | Whether files are being fetched             |
| `onFolderChange`  | `(folderPath: string) => void` | Yes      | Called when user navigates to folder        |
| `onFileSelect`    | `(filePath: string) => void`   | Yes      | Called when user selects a file             |
| `onClose`         | `() => void`                   | Yes      | Called when user closes panel               |
| `onOpenChange`    | `(open: boolean) => void`      | No       | Called when animation completes             |

## Router Independence

This component has **no router dependencies**. All navigation is handled via callbacks:

- **Folder navigation**: `onFolderChange(folderPath)`
- **File selection**: `onFileSelect(filePath)`
- **Panel close**: `onClose()`

The parent component is responsible for updating the URL or application state.
