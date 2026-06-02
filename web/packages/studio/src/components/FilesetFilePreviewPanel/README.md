# FilesetFilePreviewPanel

Fileset file preview side panel with automatic content rendering, data fetching, and breadcrumb navigation. Works for any fileset purpose (dataset, model, generic).

## Features

- **Automatic breadcrumb generation** from fileset name and file path
- Automatic data fetching (with optional pre-fetched data support)
- JSON / JSONL rendering with CodeEditor
- **Preformatted text fallback for non-JSON files**
- Loading and error states
- All file actions (download, rename, delete, split)
- Router-agnostic (all navigation via callbacks)

## Usage

### Basic Example (Internal Data Fetching)

```typescript
import { FilesetFilePreviewPanel } from '@studio/components/FilesetFilePreviewPanel';

const MyComponent = () => {
  return (
    <FilesetFilePreviewPanel
      open={true}
      workspace="default"
      filesetName="my-dataset"
      filePath="data/train.txt"
      onFilesetClick={() => navigate('/filesets/my-dataset')}
      onFolderClick={(folderPath) => navigate(`/filesets/my-dataset/files/${folderPath}`)}
      onCloseClick={() => navigateToPreviousView()}
      onOutsideClick={() => navigateToList()} // Optional: different behavior for outside clicks
      onDeleteSuccess={() => handleFileDeleted()}
      onRenameSuccess={(newPath) => navigateToFile(newPath)}
      // Component fetches data and generates breadcrumbs automatically!
      // Breadcrumbs: "my-dataset" > "data" > "train.txt"
      // Both fileset and folder breadcrumbs are clickable!
    />
  );
};
```

### With Pre-Fetched Data

```typescript
const { data: fileContent, isLoading, error } = useDatasetFileContent({
  workspace: 'default',
  name: 'my-dataset',
  path: 'data.txt',
});

return (
  <FilesetFilePreviewPanel
    open={true}
    workspace="default"
    filesetName="my-dataset"
    filePath="data.txt"
    fileContent={fileContent}
    isLoading={isLoading}
    error={error}
    onCloseClick={() => navigateToPreviousView()}
    onOutsideClick={() => navigateToList()}
  />
);
```

## File Type Handling

The component automatically detects file type and renders appropriately:

- **JSON files** (`.json`, `.jsonl`): Rendered with CodeEditor
- **Markdown** (`.md`, `.markdown`): Rendered with MarkdownContent
- **CSV** (`.csv`): Rendered with a virtualized table
- **All other files**: Rendered as plain text in the CodeEditor

## Props

| Prop              | Type                           | Required | Description                                                                                     |
| ----------------- | ------------------------------ | -------- | ----------------------------------------------------------------------------------------------- |
| `open`            | `boolean`                      | Yes      | Whether the panel is open                                                                       |
| `onCloseClick`    | `() => void`                   | Yes      | Called when close button clicked (or when closing via other means if onOpenChange not provided) |
| `onOutsideClick`  | `() => void`                   | No       | Called when clicking outside or pressing ESC. If not provided, falls back to onCloseClick.      |
| `workspace`       | `string`                       | Yes      | Fileset workspace                                                                               |
| `filesetName`     | `string`                       | Yes      | Fileset name (used in breadcrumbs)                                                              |
| `filePath`        | `string`                       | Yes      | Path to file in fileset (used in breadcrumbs)                                                   |
| `onFilesetClick`  | `() => void`                   | No       | Called when the fileset breadcrumb is clicked                                                   |
| `onFolderClick`   | `(folderPath: string) => void` | No       | Called when folder breadcrumb is clicked with the folder path                                   |
| `onDeleteSuccess` | `() => void`                   | No       | Called after successful file deletion                                                           |
| `onRenameSuccess` | `(newPath: string) => void`    | No       | Called after successful file rename                                                             |
| `file`            | `FileSystemFile`               | No       | Pre-fetched file metadata                                                                       |
| `fileContent`     | `string`                       | No       | Pre-fetched file content                                                                        |
| `isLoading`       | `boolean`                      | No       | Loading state (if pre-fetched)                                                                  |
| `error`           | `Error`                        | No       | Error state (if pre-fetched)                                                                    |

## Breadcrumb Generation & Navigation

Breadcrumbs are automatically generated from `filesetName` and `filePath`:

```typescript
// Given:
filesetName = 'my-dataset';
filePath = 'data/subfolder/train.jsonl';

// Generates breadcrumbs:
// "my-dataset" > "data" > "subfolder" > "train.jsonl"
```

### Breadcrumb Behavior:

- **Fileset breadcrumb** (first): Clickable if `onFilesetClick` provided
- **Folder breadcrumbs** (middle): Clickable if `onFolderClick` provided
  - Clicking passes the full path to that folder (e.g., `"data"`, `"data/subfolder"`)
- **File breadcrumb** (last): Always non-clickable (current file)

### Navigation Example:

```typescript
<FilesetFilePreviewPanel
  workspace="default"
  filesetName="my-dataset"
  filePath="data/subfolder/train.jsonl"
  onFilesetClick={() => {
    // Navigate to fileset root
    navigate('/filesets/my-dataset');
  }}
  onFolderClick={(folderPath) => {
    // Navigate to folder view
    // folderPath will be: "data" or "data/subfolder"
    navigate(`/filesets/my-dataset/files/${folderPath}`);
  }}
/>
```

## When to Use

Use `FilesetFilePreviewPanel` when you need a side-panel file preview for any fileset (dataset, model, generic) with:

- Automatic breadcrumb navigation
- Automatic content rendering
- Built-in file actions
- Automatic or manual data fetching

Use `FilesetFilePreviewContent` (the no-chrome sibling) when you want to embed the same viewer inline on a tab rather than in a side panel.
