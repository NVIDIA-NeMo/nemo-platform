// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CodeEditor } from '@nemo/common/src/components/CodeEditor';
import { ContentType } from '@nemo/common/src/components/CodeEditor/constants';
import { FileFormat, type FileFormatType } from '@nemo/common/src/types';
import { getFirstRow } from '@nemo/common/src/utils/file';
import {
  buildDatasetMetadata,
  canonicalJson,
  inferJsonSchema,
  isSchemaAssignableFile,
  parseAndValidate,
  type PerFileInferred,
} from '@nemo/common/src/utils/jsonSchema';
import {
  getFilesRetrieveFilesetQueryKey,
  useFilesUpdateFilesetMetadata,
} from '@nemo/sdk/generated/platform/api';
import type {
  DatasetMetadataContent,
  FilesetFileOutput,
  FilesetOutput,
} from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, Stack, TableToolbar, Text } from '@nvidia/foundations-react-core';
import { useDownloadFileHead } from '@studio/components/filesets/hooks/useDownloadFileHead';
import {
  DEFAULT_SCHEMA_VALUE,
  SchemaSelectControl,
  SHOW_ALL_VALUE,
} from '@studio/routes/FilesetDetailRoute/DatasetSchemaEditor/SchemaSelectControl';
import { SharedSchemaConfirmModal } from '@studio/routes/FilesetDetailRoute/DatasetSchemaEditor/SharedSchemaConfirmModal';
import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type FC } from 'react';

export interface DatasetSchemaEditorProps {
  workspace: string;
  datasetName: string;
  fileset: FilesetOutput;
  filesList: FilesetFileOutput[] | undefined;
  /** When set, dropdown auto-selects the file's mapped schema. When cleared,
   *  dropdown jumps back to "Show All". */
  selectedFilePath?: string;
}

const INFER_FROM_EXISTING_MAX_FILES = 10;

const FORMAT_BY_EXTENSION: Record<string, FileFormatType> = {
  json: FileFormat.JSON,
  jsonl: FileFormat.JSONL,
};

function detectFormatFromPath(path: string): FileFormatType | null {
  const ext = path.split('.').pop()?.toLowerCase() ?? '';
  return FORMAT_BY_EXTENSION[ext] ?? null;
}

/** Resolve the effective JSON Schema applied to a file path, given a metadata
 *  payload. Mirrors backend resolution: explicit `schemas_by_path` mapping wins
 *  (string ref → schema_defs entry, inline object → the object itself);
 *  otherwise fall back to root `schema` (ref → schema_defs entry, inline →
 *  the object). Returns undefined when no schema applies. */
function resolveSchemaForFile(metadata: DatasetMetadataContent | undefined, path: string): unknown {
  if (!metadata) return undefined;
  const mapped = metadata.schemas_by_path?.[path];
  if (typeof mapped === 'string') return metadata.schema_defs?.[mapped];
  if (mapped && typeof mapped === 'object') return mapped;
  const root = metadata.schema;
  if (root === undefined || root === null) return undefined;
  if (typeof root === 'string') return metadata.schema_defs?.[root];
  return root;
}

/** Look up the JSON Schema object that backs the given dropdown selection. */
function lookupSchemaForSelection(
  metadata: DatasetMetadataContent | undefined,
  selection: string
): Record<string, unknown> | undefined {
  if (!metadata) return undefined;
  if (selection === SHOW_ALL_VALUE) return undefined; // Show All is whole-payload, not a single schema.
  if (selection === DEFAULT_SCHEMA_VALUE) {
    const root = metadata.schema;
    if (root === undefined || root === null) return undefined;
    if (typeof root === 'string') return metadata.schema_defs?.[root];
    return root as Record<string, unknown>;
  }
  return metadata.schema_defs?.[selection];
}

/** True when a schema is an object-typed JSON Schema with a `properties` map.
 *  Those schemas are rendered "properties-only" in the editor; everything else
 *  is rendered as the whole schema object. */
function hasPropertiesMap(schema: Record<string, unknown> | undefined): boolean {
  if (!schema) return false;
  const props = schema.properties;
  return props !== null && typeof props === 'object' && !Array.isArray(props);
}

/** Resolve what the editor should display for a given dropdown selection.
 *  For single-schema selections, this returns just the `properties` value
 *  when present (so the user edits field definitions, not the surrounding
 *  $schema / type wrapper). */
function deriveSelectionText(
  metadata: DatasetMetadataContent | undefined,
  selection: string
): string {
  if (!metadata) return '';
  if (selection === SHOW_ALL_VALUE) return JSON.stringify(metadata, null, 2);
  const schema = lookupSchemaForSelection(metadata, selection);
  if (!schema) return '';
  if (hasPropertiesMap(schema)) {
    return JSON.stringify(schema.properties, null, 2);
  }
  return JSON.stringify(schema, null, 2);
}

/** Build the updated `metadata.dataset` payload for a single-schema edit.
 *  The `parsedEditorValue` is whatever the user typed in the editor — which
 *  is either the `properties` map (when the original schema had one) or the
 *  whole schema object. We look up the original schema to decide which case
 *  applies and rebuild the schema accordingly, preserving non-`properties`
 *  fields like `$schema`, `type`, `required`, etc. */
function applySingleSchemaEdit(
  metadata: DatasetMetadataContent | undefined,
  selection: string,
  parsedEditorValue: Record<string, unknown>
): DatasetMetadataContent | undefined {
  const base: DatasetMetadataContent = metadata
    ? {
        schema: metadata.schema,
        schema_defs: { ...(metadata.schema_defs ?? {}) },
        schemas_by_path: { ...(metadata.schemas_by_path ?? {}) },
      }
    : { schema_defs: {}, schemas_by_path: {} };

  const original = lookupSchemaForSelection(metadata, selection);
  // If the original had a `properties` map, the editor was showing just that
  // value — re-wrap into the original shell. Otherwise the editor was
  // showing the full schema and the parsed value IS the new schema.
  const newSchema: Record<string, unknown> = hasPropertiesMap(original)
    ? { ...(original as Record<string, unknown>), properties: parsedEditorValue }
    : parsedEditorValue;

  if (selection === DEFAULT_SCHEMA_VALUE) {
    const root = base.schema;
    if (typeof root === 'string') {
      // Root is a ref to a schema_def; update that def in place.
      base.schema_defs = { ...(base.schema_defs ?? {}), [root]: newSchema };
    } else {
      // Inline (or absent) → set inline.
      base.schema = newSchema;
    }
    return base;
  }

  // selection is a schema_defs key
  base.schema_defs = { ...(base.schema_defs ?? {}), [selection]: newSchema };
  return base;
}

/**
 * Dataset-specific schema editor orchestrator.
 *
 * Renders a dropdown ("Default" + each `schema_defs` key + "Show All
 * advanced"). The editor shows one JSON Schema at a time in single-schema
 * mode, or the full `metadata.dataset` payload when "Show All" is picked.
 *
 * User edits are preserved per-selection so switching schemas and back
 * doesn't lose work.
 */
export const DatasetSchemaEditor: FC<DatasetSchemaEditorProps> = ({
  workspace,
  datasetName,
  fileset,
  filesList,
  selectedFilePath,
}) => {
  const savedMetadata: DatasetMetadataContent | undefined = fileset.metadata?.dataset;

  const defKeys = useMemo(
    () => Object.keys(savedMetadata?.schema_defs ?? {}).sort(),
    [savedMetadata]
  );
  // Two flavors of root schema: inline object (shows separately as "Default")
  // vs string ref to a schema_defs key (that key shows with a "(default)"
  // marker, no separate entry).
  const rootSchema = savedMetadata?.schema;
  const defaultDefKey =
    typeof rootSchema === 'string' && defKeys.includes(rootSchema) ? rootSchema : undefined;
  const hasInlineDefault =
    rootSchema !== undefined && rootSchema !== null && typeof rootSchema !== 'string';

  const pickInitialSelection = useCallback((): string => {
    if (hasInlineDefault) return DEFAULT_SCHEMA_VALUE;
    if (defaultDefKey) return defaultDefKey;
    return defKeys[0] ?? SHOW_ALL_VALUE;
  }, [hasInlineDefault, defaultDefKey, defKeys]);

  // Lazy initializer so mount-with-file lands at the mapped schema directly
  // (no extra render). Subsequent file-path transitions are handled by the
  // useEffect below.
  const [selectedSchema, setSelectedSchema] = useState<string>(() => {
    if (selectedFilePath) {
      const mapped = savedMetadata?.schemas_by_path?.[selectedFilePath];
      if (typeof mapped === 'string' && defKeys.includes(mapped)) return mapped;
    }
    if (hasInlineDefault) return DEFAULT_SCHEMA_VALUE;
    if (defaultDefKey) return defaultDefKey;
    return defKeys[0] ?? SHOW_ALL_VALUE;
  });

  // When savedMetadata changes, drop the selected value if it no longer
  // corresponds to a real schema. Keep it stable otherwise.
  useEffect(() => {
    if (
      selectedSchema === SHOW_ALL_VALUE ||
      (selectedSchema === DEFAULT_SCHEMA_VALUE && hasInlineDefault) ||
      defKeys.includes(selectedSchema)
    ) {
      return;
    }
    setSelectedSchema(pickInitialSelection());
  }, [selectedSchema, hasInlineDefault, defKeys, pickInitialSelection]);

  // Handle file-path TRANSITIONS only (initial mount is handled by the lazy
  // useState initializer above). File preview opened: jump to file's mapped
  // schema. File preview closed: jump to Show All.
  const prevFilePathRef = useRef<string | undefined>(selectedFilePath);
  useEffect(() => {
    const prev = prevFilePathRef.current;
    const cur = selectedFilePath;
    if (prev === cur) return;
    prevFilePathRef.current = cur;
    if (!cur) {
      setSelectedSchema(SHOW_ALL_VALUE);
      return;
    }
    const mapped = savedMetadata?.schemas_by_path?.[cur];
    if (typeof mapped === 'string' && defKeys.includes(mapped)) {
      setSelectedSchema(mapped);
      return;
    }
    if (mapped && typeof mapped === 'object') {
      setSelectedSchema(SHOW_ALL_VALUE);
      return;
    }
    if (defaultDefKey) {
      setSelectedSchema(defaultDefKey);
      return;
    }
    if (hasInlineDefault) {
      setSelectedSchema(DEFAULT_SCHEMA_VALUE);
      return;
    }
    setSelectedSchema(SHOW_ALL_VALUE);
  }, [selectedFilePath, savedMetadata, defKeys, defaultDefKey, hasInlineDefault]);

  // Per-selection unsaved edits: switching selections preserves what the user
  // had been typing. Saving or Resetting clears the entry for that selection.
  const [editsBySelection, setEditsBySelection] = useState<Record<string, string>>({});

  const derivedText = useMemo(
    () => deriveSelectionText(savedMetadata, selectedSchema),
    [savedMetadata, selectedSchema]
  );
  const text = editsBySelection[selectedSchema] ?? derivedText;
  const userEdited = selectedSchema in editsBySelection;

  const handleEditorChange = useCallback(
    (next: string) => {
      setEditsBySelection((prev) => ({ ...prev, [selectedSchema]: next }));
    },
    [selectedSchema]
  );

  const handleReset = useCallback(() => {
    setEditsBySelection((prev) => {
      if (!(selectedSchema in prev)) return prev;
      const next = { ...prev };
      delete next[selectedSchema];
      return next;
    });
    setInferError(null);
  }, [selectedSchema]);

  // Inference state lives here too (used by "Infer from existing files").
  const [isInferring, setIsInferring] = useState(false);
  const [inferError, setInferError] = useState<string | null>(null);

  const downloadFileHead = useDownloadFileHead();

  const supportedExistingFiles = useMemo(
    () =>
      (filesList ?? [])
        .filter((f) => detectFormatFromPath(f.path) !== null)
        // Sort root-level files first, then deeper paths; alphabetical within
        // each depth. `buildDatasetMetadata` picks the first-encountered
        // canonical as the default on ties, so this makes the default come
        // from a top-level file (matching user expectation when both root
        // and nested files exist).
        .slice()
        .sort((a, b) => {
          const aDepth = a.path.split('/').length;
          const bDepth = b.path.split('/').length;
          if (aDepth !== bDepth) return aDepth - bDepth;
          return a.path.localeCompare(b.path);
        }),
    [filesList]
  );

  const handleInferFromExisting = useCallback(async () => {
    if (supportedExistingFiles.length === 0) return;
    setIsInferring(true);
    setInferError(null);
    try {
      const decoder = new TextDecoder('utf-8');
      const perFile: PerFileInferred[] = [];
      for (const file of supportedExistingFiles.slice(0, INFER_FROM_EXISTING_MAX_FILES)) {
        const format = detectFormatFromPath(file.path);
        if (!format) continue;
        const buffer = await downloadFileHead({ workspace, datasetName, path: file.path });
        if (!buffer) continue;
        const textContent = decoder.decode(buffer);
        const blob = new File([textContent], file.path);
        try {
          const row = await getFirstRow(blob, format);
          if (row && typeof row === 'object') {
            perFile.push({ path: file.path, schema: inferJsonSchema(row) });
          }
        } catch {
          // Skip unparseable files - the merged result still includes the rest.
        }
      }
      if (perFile.length === 0) {
        setInferError('Could not infer a schema from existing files.');
        return;
      }
      // "Infer from existing files" is a full re-inference: the resulting
      // metadata.dataset REPLACES the prior contents (no merging with
      // savedMetadata). Merging would mint new defs alongside outdated ones
      // whenever the inference algorithm improves, leaving orphan schemas.
      // Manual schemas added in Show All are also dropped here — the user
      // should use Show All if they want to layer custom defs on top.
      const inferred = buildDatasetMetadata(perFile);
      setEditsBySelection((prev) => ({
        ...prev,
        [SHOW_ALL_VALUE]: JSON.stringify(inferred, null, 2),
      }));
      setSelectedSchema(SHOW_ALL_VALUE);
    } finally {
      setIsInferring(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- workspace/datasetName captured inside downloadFileHead's own useCallback
  }, [supportedExistingFiles, downloadFileHead]);

  const { mutateAsync: updateMetadata, isPending: isSaving } = useFilesUpdateFilesetMetadata();
  const queryClient = useQueryClient();

  const validation = useMemo(() => {
    if (!text.trim()) return { valid: true as const, errors: [] };
    const result = parseAndValidate(text);
    return result.valid ? { valid: true as const, errors: [] } : result;
  }, [text]);

  // Count of files affected by saving the current edit.
  //   Single-schema view: iterate filesList, count files whose resolved
  //   schema is the selected one (explicit ref OR implicit default).
  //   Show All view: diff parsed metadata against `savedMetadata` and count
  //   files whose RESOLVED schema would change.
  const sharedReferrerCount = useMemo(() => {
    // Only data files (`.json` / `.jsonl`) carry a schema in this UI. Non-data
    // files inflated the "Schema is used by N files" count on external
    // datasets where READMEs, images, and other artifacts dominate the tree.
    const files = (filesList ?? []).filter((f) => isSchemaAssignableFile(f.path));
    if (selectedSchema === SHOW_ALL_VALUE) {
      const parsed = parseAndValidate(text);
      if (!parsed.valid) return 0;
      const newMetadata = parsed.value as DatasetMetadataContent;
      let affected = 0;
      for (const f of files) {
        const before = resolveSchemaForFile(savedMetadata, f.path);
        const after = resolveSchemaForFile(newMetadata, f.path);
        if (canonicalJson(before) !== canonicalJson(after)) affected += 1;
      }
      return affected;
    }
    const byPath = savedMetadata?.schemas_by_path ?? {};
    const isDefault = selectedSchema === DEFAULT_SCHEMA_VALUE || selectedSchema === defaultDefKey;
    let count = 0;
    for (const f of files) {
      const mapped = byPath[f.path];
      if (typeof mapped === 'string') {
        if (mapped === selectedSchema) count += 1;
        continue;
      }
      if (mapped && typeof mapped === 'object') continue;
      if (isDefault) count += 1;
    }
    return count;
  }, [selectedSchema, savedMetadata, defaultDefKey, filesList, text]);

  const [pendingShareConfirm, setPendingShareConfirm] = useState(false);

  const performSave = useCallback(async () => {
    if (!validation.valid) return;

    const trimmed = text.trim();
    const isClearing = trimmed === '' && selectedSchema === SHOW_ALL_VALUE;

    // Clearing only makes sense in the Show All view (wipes the whole
    // metadata.dataset payload). For single-schema selections, empty text
    // is ambiguous and isn't supported here - the user can switch to
    // Show All to clear, or edit the field they want to remove.
    if (trimmed === '' && !isClearing) return;

    let newDataset: DatasetMetadataContent | null;
    if (isClearing) {
      newDataset = null;
    } else {
      const parsed = parseAndValidate(text);
      if (!parsed.valid) return;
      if (selectedSchema === SHOW_ALL_VALUE) {
        newDataset = parsed.value as DatasetMetadataContent;
      } else {
        const result = applySingleSchemaEdit(
          savedMetadata,
          selectedSchema,
          parsed.value as Record<string, unknown>
        );
        if (!result) return;
        newDataset = result;
      }
    }

    await updateMetadata({
      workspace,
      name: datasetName,
      // `dataset: null` clears the field on the backend (matches the
      // pydantic `DatasetMetadataContent | None` default).
      data: { metadata: { dataset: newDataset as DatasetMetadataContent } },
    });
    await queryClient.invalidateQueries({
      queryKey: getFilesRetrieveFilesetQueryKey(workspace, datasetName),
    });
    setEditsBySelection((prev) => {
      if (!(selectedSchema in prev)) return prev;
      const next = { ...prev };
      delete next[selectedSchema];
      return next;
    });
  }, [
    validation.valid,
    text,
    selectedSchema,
    savedMetadata,
    updateMetadata,
    workspace,
    datasetName,
    queryClient,
  ]);

  const handleSave = useCallback(async () => {
    if (sharedReferrerCount > 1) {
      setPendingShareConfirm(true);
      return;
    }
    await performSave();
  }, [sharedReferrerCount, performSave]);

  const handleConfirmShared = useCallback(async () => {
    await performSave();
    setPendingShareConfirm(false);
  }, [performSave]);

  const handleSetDefault = useCallback(async () => {
    // Only valid for a schema_defs key that isn't already the default.
    if (
      selectedSchema === SHOW_ALL_VALUE ||
      selectedSchema === DEFAULT_SCHEMA_VALUE ||
      !savedMetadata?.schema_defs?.[selectedSchema]
    ) {
      return;
    }
    const newMetadata: DatasetMetadataContent = {
      ...savedMetadata,
      schema: selectedSchema,
      schema_defs: { ...(savedMetadata.schema_defs ?? {}) },
      schemas_by_path: { ...(savedMetadata.schemas_by_path ?? {}) },
    };
    await updateMetadata({
      workspace,
      name: datasetName,
      data: { metadata: { dataset: newMetadata } },
    });
    await queryClient.invalidateQueries({
      queryKey: getFilesRetrieveFilesetQueryKey(workspace, datasetName),
    });
  }, [selectedSchema, savedMetadata, updateMetadata, workspace, datasetName, queryClient]);

  const canInferFromExisting = supportedExistingFiles.length > 0 && !isInferring;
  const canSave = userEdited && validation.valid && !isSaving;
  // "Set Default" is meaningful only when a real schema_defs entry is
  // selected AND it isn't already the default.
  const canSetDefault =
    selectedSchema !== SHOW_ALL_VALUE &&
    selectedSchema !== DEFAULT_SCHEMA_VALUE &&
    !!savedMetadata?.schema_defs?.[selectedSchema] &&
    selectedSchema !== defaultDefKey &&
    !isSaving;
  const isEmpty = !savedMetadata && !userEdited;

  if (isEmpty) {
    return (
      <Stack
        gap="density-md"
        align="center"
        className="w-full py-density-2xl px-density-md text-center"
        data-testid="dataset-schema-editor-empty"
      >
        <Text kind="title/sm">No schema yet</Text>
        <Text kind="body/regular/sm">
          This dataset doesn&apos;t have a schema set. A schema helps downstream tools (training,
          evaluation) validate your file shapes.
        </Text>
        <Button
          kind="primary"
          onClick={handleInferFromExisting}
          disabled={!canInferFromExisting}
          data-testid="dataset-schema-infer-button"
        >
          {isInferring ? 'Generating…' : 'Generate'}
        </Button>
        {supportedExistingFiles.length === 0 && (
          <Text kind="body/regular/sm">
            Upload a .json or .jsonl file to enable auto-inference.
          </Text>
        )}
        {inferError && (
          <Text kind="body/regular/sm" data-testid="dataset-schema-infer-error">
            {inferError}
          </Text>
        )}
      </Stack>
    );
  }

  return (
    <Stack gap="density-md" className="w-full h-full min-h-0" data-testid="dataset-schema-editor">
      <TableToolbar aria-label="Dataset schema toolbar" className="min-w-0 shrink-0">
        <Flex direction="row" gap="density-md" className="min-w-0 w-full">
          <Flex align="center" className="flex-1 min-w-0">
            <Text kind="title/sm">Dataset Schema</Text>
          </Flex>
          <Button
            kind="secondary"
            onClick={handleInferFromExisting}
            disabled={!canInferFromExisting}
            data-testid="dataset-schema-infer-button"
          >
            {isInferring ? 'Generating…' : 'Generate'}
          </Button>
        </Flex>
      </TableToolbar>

      <Flex
        gap="density-sm"
        align="center"
        className="shrink-0"
        data-testid="dataset-schema-select-row"
      >
        <div className="flex-1 min-w-0">
          <SchemaSelectControl
            defKeys={defKeys}
            hasInlineDefault={hasInlineDefault}
            defaultDefKey={defaultDefKey}
            value={selectedSchema}
            onChange={setSelectedSchema}
          />
        </div>
        <Button
          kind="secondary"
          onClick={handleSetDefault}
          disabled={!canSetDefault}
          data-testid="dataset-schema-set-default-button"
        >
          Set Default
        </Button>
      </Flex>

      <CodeEditor
        content={text}
        contentType={ContentType.JSON}
        onChange={handleEditorChange}
        className="flex-1 min-h-0 overflow-hidden"
        hideCopyButton
      />

      {!validation.valid && validation.errors.length > 0 && (
        <Stack gap="density-xs" className="shrink-0" data-testid="dataset-schema-editor-errors">
          {validation.errors.map((err, i) => (
            <Text key={i} kind="body/regular/sm">
              {err}
            </Text>
          ))}
        </Stack>
      )}

      {inferError && (
        <Text kind="body/regular/sm" className="shrink-0" data-testid="dataset-schema-infer-error">
          {inferError}
        </Text>
      )}

      <Flex gap="density-md" justify="end" className="shrink-0">
        <Button
          kind="secondary"
          onClick={handleReset}
          disabled={!userEdited}
          data-testid="dataset-schema-reset-button"
        >
          Reset
        </Button>
        <Button
          kind="primary"
          color="brand"
          onClick={handleSave}
          disabled={!canSave}
          data-testid="dataset-schema-save-button"
        >
          {isSaving ? 'Saving…' : 'Save schema'}
        </Button>
      </Flex>

      <SharedSchemaConfirmModal
        open={pendingShareConfirm}
        referrerCount={sharedReferrerCount}
        isPending={isSaving}
        onConfirm={handleConfirmShared}
        onCancel={() => setPendingShareConfirm(false)}
      />
    </Stack>
  );
};
