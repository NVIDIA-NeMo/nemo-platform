// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { DatasetMetadataContent } from '@nemo/sdk/generated/platform/schema';
import { useEffect, useMemo, useState } from 'react';

import { FileFormat, type FileFormatType } from '../../types';
import { getFirstRow } from '../../utils/file';
import {
  buildDatasetMetadata,
  inferJsonSchema,
  parseAndValidate,
  type PerFileInferred,
} from '../../utils/jsonSchema';

/**
 * Composes the @nemo/common JSON Schema utilities with file IO to produce a
 * `metadata.dataset` payload from the user's staged files and any existing
 * fileset metadata.
 *
 * - `metadata`: the structured payload (or null if nothing has been inferred yet).
 * - `text`: serialized JSON the user edits in the editor. Starts from `metadata`;
 *   once the user edits, the hook stops overriding `text` on each re-inference
 *   until `reset()` is called.
 * - `validation`: live JSON Schema validation result for the current `text`.
 * - `isInferring`: true while the async row-read + inference is running.
 * - `reset()`: discard user edits and resume sync with inferred metadata.
 */

export interface UseInferredDatasetSchemaResult {
  metadata: DatasetMetadataContent | null;
  text: string;
  setText: (next: string) => void;
  validation: { valid: boolean; errors: string[] };
  isInferring: boolean;
  reset: () => void;
}

const SUPPORTED_FORMAT_BY_EXTENSION: Record<string, FileFormatType> = {
  json: FileFormat.JSON,
  jsonl: FileFormat.JSONL,
  csv: FileFormat.CSV,
  parquet: FileFormat.PARQUET,
};

function detectFormat(file: File): FileFormatType | null {
  const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
  return SUPPORTED_FORMAT_BY_EXTENSION[ext] ?? null;
}

export function useInferredDatasetSchema(
  files: File[],
  existing?: DatasetMetadataContent
): UseInferredDatasetSchemaResult {
  const [inferredMetadata, setInferredMetadata] = useState<DatasetMetadataContent | null>(null);
  const [text, setTextState] = useState('');
  const [userEdited, setUserEdited] = useState(false);
  const [isInferring, setIsInferring] = useState(false);

  // Stable signature so prop-identity churn (caller didn't memoize) doesn't
  // re-run the effect when the actual inputs haven't changed.
  const inputSignature = useMemo(() => {
    const fileSig = files.map((f) => `${f.name}:${f.size}:${f.lastModified}`).join('|');
    const existingSig = existing ? JSON.stringify(existing) : 'none';
    return `${fileSig}::${existingSig}`;
  }, [files, existing]);

  useEffect(() => {
    if (userEdited) {
      // No inference work to do; make sure a previously-interrupted run doesn't
      // leave the loading flag stuck on.
      setIsInferring(false);
      return;
    }

    const supportedFiles = files.filter((f) => detectFormat(f) !== null);
    if (supportedFiles.length === 0 && !existing) {
      setInferredMetadata(null);
      setTextState('');
      setIsInferring(false);
      return;
    }

    let cancelled = false;
    setIsInferring(true);

    (async () => {
      const perFile: PerFileInferred[] = [];
      for (const file of supportedFiles) {
        const format = detectFormat(file);
        if (!format) continue;
        try {
          const row = await getFirstRow(file, format);
          if (row && typeof row === 'object') {
            perFile.push({ path: file.name, schema: inferJsonSchema(row) });
          }
        } catch {
          // Unparseable file: skip silently. The UI surfaces an empty file list
          // separately; we don't want one bad file to drop the whole result.
        }
      }
      // Intentionally do NOT clear isInferring here on cancel: the next effect
      // run executed synchronously before this microtask and has already set
      // the flag to the new authoritative value. Touching it here would race.
      if (cancelled) return;
      const metadata = buildDatasetMetadata(perFile, existing);
      setInferredMetadata(metadata);
      setTextState(JSON.stringify(metadata, null, 2));
      setIsInferring(false);
    })();

    return () => {
      cancelled = true;
      // Cleanup runs synchronously before the next effect callback, so it is
      // safe to clear the loading flag here. The next run will set it back to
      // the correct value (true if it kicks off new inference, false otherwise).
      setIsInferring(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- inputSignature is the canonical key
  }, [inputSignature, userEdited]);

  const validation = useMemo<{ valid: boolean; errors: string[] }>(() => {
    if (!text) return { valid: true, errors: [] };
    const result = parseAndValidate(text);
    return result.valid ? { valid: true, errors: [] } : { valid: false, errors: result.errors };
  }, [text]);

  return {
    metadata: inferredMetadata,
    text,
    setText: (next: string) => {
      setTextState(next);
      setUserEdited(true);
    },
    validation,
    isInferring,
    reset: () => {
      setUserEdited(false);
    },
  };
}
