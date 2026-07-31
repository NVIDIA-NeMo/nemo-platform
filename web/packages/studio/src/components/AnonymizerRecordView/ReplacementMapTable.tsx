// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { Tag, Text } from '@nvidia/foundations-react-core';
import type { EntityReplacement } from '@studio/components/AnonymizerRecordView/types';
import { entityTagColor } from '@studio/routes/AnonymizerBuilderRoute/constants';
import { ArrowRight } from 'lucide-react';
import { memo, useCallback, useMemo, type ComponentProps, type FC } from 'react';

const REPLACEMENTS_PAGE_SIZE = 20;
const ARROW_COLUMN_SIZE = 48;

interface ReplacementMapTableProps {
  readonly replacements: readonly EntityReplacement[];
}

export const ReplacementMapTable: FC<ReplacementMapTableProps> = memo(({ replacements }) => {
  const dataViewState = useStudioDataViewState({ defaultPageSize: REPLACEMENTS_PAGE_SIZE });

  const { pageIndex: requestedPage, pageSize } = dataViewState.pagination.state;
  // `page` is a shared URL param, so it survives paging the record pager to a shorter map —
  // without clamping, the slice falls off the end and the table reads as empty.
  const pageIndex = Math.min(
    requestedPage,
    Math.max(Math.ceil(replacements.length / pageSize) - 1, 0)
  );
  const pageRows = useMemo(
    () => replacements.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize),
    [replacements, pageIndex, pageSize]
  );

  const makeColumns = useCallback<
    ComponentProps<typeof StudioDataView<EntityReplacement>>['makeColumns']
  >(
    (col) => [
      col.display({
        id: 'label',
        header: 'Label',
        cell: ({ row }) => (
          <Tag color={entityTagColor(row.original.label)} kind="outline" readOnly>
            {row.original.label}
          </Tag>
        ),
      }),
      col.display({
        id: 'original',
        header: 'Original',
        cell: ({ row }) => <Text kind="body/regular/sm">{row.original.original}</Text>,
      }),
      col.display({
        id: 'arrow',
        header: '',
        size: ARROW_COLUMN_SIZE,
        cell: () => <ArrowRight aria-hidden size={14} />,
      }),
      col.display({
        id: 'synthetic',
        header: 'Replacement',
        cell: ({ row }) => <Text kind="body/regular/sm">{row.original.synthetic}</Text>,
      }),
    ],
    []
  );

  return (
    <StudioDataView<EntityReplacement>
      dataViewState={dataViewState}
      makeColumns={makeColumns}
      maxTwoLines={false}
      attributes={{
        DataViewRoot: { data: pageRows, totalCount: replacements.length },
        // A record's map is short; the pager only appears when it overflows a page.
        DataViewPagination: { showWhileEmpty: false, showWhileLessThanPageSize: false },
      }}
    />
  );
});

ReplacementMapTable.displayName = 'ReplacementMapTable';
