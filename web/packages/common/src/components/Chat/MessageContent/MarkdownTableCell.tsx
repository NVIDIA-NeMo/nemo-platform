// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getNodeText } from '@nemo/common/src/components/Chat/MessageContent/helpers';
import type { MarkdownTableCellProps } from '@nemo/common/src/components/Chat/MessageContent/types';

export const MarkdownTableCell = ({
  children,
  expanded,
  expandable,
  onToggle,
}: MarkdownTableCellProps) => {
  if (!expandable) {
    return <span className="block whitespace-normal break-words">{children}</span>;
  }

  const text = getNodeText(children);

  return (
    <button
      aria-label={text || undefined}
      aria-expanded={expanded}
      className="block w-full min-w-0 max-w-full cursor-pointer appearance-none overflow-hidden border-0 bg-transparent p-0 text-left font-inherit text-inherit"
      onClick={(event) => {
        event.stopPropagation();
        onToggle();
      }}
      type="button"
    >
      <span
        className={`min-w-0 max-w-full whitespace-normal break-words [&_span]:whitespace-normal ${
          expanded ? 'block' : 'line-clamp-2'
        }`}
        data-collapsed={!expanded || undefined}
      >
        {children}
      </span>
    </button>
  );
};
