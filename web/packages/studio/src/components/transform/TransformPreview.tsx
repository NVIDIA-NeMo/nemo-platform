// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Stack, Text } from '@nvidia/foundations-react-core';
import { PreviewOutputPanel } from '@studio/components/PreviewOutputPanel';
import { useTransformPreview } from '@studio/components/transform/useTransformPreview';
import { useMemo, type FC } from 'react';
import { useDebounce } from 'use-debounce';

const PREVIEW_DEBOUNCE_MS = 250;

interface Props {
  fileContent: string | undefined;
  fileType: string;
  template: Record<string, unknown>;
  /** Column the transform generates rather than reads, e.g. a per-row identifier. */
  generatedIdColumn?: string;
}

/**
 * Before/after view of a single source row. The template is debounced so typing
 * a raw template re-renders the preview rather than the whole modal on every
 * keystroke.
 */
export const TransformPreview: FC<Props> = ({
  fileContent,
  fileType,
  template,
  generatedIdColumn,
}) => {
  const [debouncedTemplate] = useDebounce(template, PREVIEW_DEBOUNCE_MS);

  const { currentRow, totalRows, sourceRow, afterRow, approximated, onRowChange } =
    useTransformPreview({
      fileContent,
      fileType,
      template: debouncedTemplate,
      generatedIdColumn,
    });

  const beforeValue = useMemo(() => JSON.stringify(sourceRow, null, 2), [sourceRow]);
  const afterValue = useMemo(
    () =>
      afterRow
        ? JSON.stringify(afterRow, null, 2)
        : '// Map a field above to see the transformed output',
    [afterRow]
  );

  if (!sourceRow) return null;

  return (
    <Stack gap="density-sm">
      <PreviewOutputPanel
        beforeValue={beforeValue}
        afterValue={afterValue}
        currentRow={currentRow}
        totalRows={totalRows}
        onRowChange={onRowChange}
      />
      {approximated && (
        <Text kind="body/regular/xs" className="text-muted">
          This preview ignores template filters — the transform applies them when it runs.
        </Text>
      )}
    </Stack>
  );
};
