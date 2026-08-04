// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { TransformFileFormFields } from '@studio/components/FilesTable/TransformFileModal/types';
import { useTransformPreview } from '@studio/components/FilesTable/TransformFileModal/useTransformPreview';
import { PreviewOutputPanel } from '@studio/components/PreviewOutputPanel';
import { useMemo, type FC } from 'react';
import { useWatch, type Control } from 'react-hook-form';
import { useDebounce } from 'use-debounce';

const PREVIEW_DEBOUNCE_MS = 250;

interface Props {
  control: Control<TransformFileFormFields>;
  fileContent: string | undefined;
  fileType: string;
}

/**
 * Isolates the mapping subscription so typing in a mapping field only re-renders
 * (and re-runs the Handlebars templating for) the preview, not the whole modal.
 */
export const TransformPreview: FC<Props> = ({ control, fileContent, fileType }) => {
  const mappings = useWatch({ control, name: 'mappings' });
  const [debouncedMappings] = useDebounce(mappings, PREVIEW_DEBOUNCE_MS);

  const { currentRow, totalRows, sourceRow, afterRow, onRowChange } = useTransformPreview({
    fileContent,
    fileType,
    mappings: debouncedMappings ?? [],
  });

  const beforeValue = useMemo(() => JSON.stringify(sourceRow, null, 2), [sourceRow]);
  const afterValue = useMemo(
    () =>
      afterRow
        ? JSON.stringify(afterRow, null, 2)
        : '// Add mappings above to see the transformed output',
    [afterRow]
  );

  if (!sourceRow) return null;

  return (
    <PreviewOutputPanel
      beforeValue={beforeValue}
      afterValue={afterValue}
      currentRow={currentRow}
      totalRows={totalRows}
      onRowChange={onRowChange}
    />
  );
};
