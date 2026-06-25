// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Anchor, CodeSnippet, Stack } from '@nvidia/foundations-react-core';
import { type FC, useMemo, useState } from 'react';

interface RawJsonDebugProps {
  /** Any JSON-serializable value (e.g. a span or trace) to reveal for debugging. */
  value: unknown;
  /** Trailing label for the toggle, e.g. "raw JSON" → "Show raw JSON". */
  label?: string;
  /** Extra classes on the container (e.g. to match surrounding inset). */
  className?: string;
}

/**
 * A debug affordance: a subtle link that toggles a read-only JSON dump of
 * `value`. Collapsed by default so it stays unobtrusive.
 */
export const RawJsonDebug: FC<RawJsonDebugProps> = ({ value, label = 'Raw JSON', className }) => {
  const [open, setOpen] = useState(false);
  const json = useMemo(() => {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      // Circular references or BigInt make JSON.stringify throw; degrade
      // gracefully so the surrounding detail view still renders.
      return '[unserializable value]';
    }
  }, [value]);

  return (
    <Stack gap="density-md" className={`min-w-0 ${className ?? ''}`}>
      <Anchor asChild>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="self-start text-xs"
        >
          {open ? `Hide ${label}` : `${label}`}
        </button>
      </Anchor>
      {open ? (
        <CodeSnippet
          value={json}
          language="json"
          kind="block"
          attributes={{
            CodeSnippetCode: {
              className:
                'max-h-[480px] [&_code]:whitespace-pre-wrap [&_code]:break-words [&_pre]:whitespace-pre-wrap',
            },
          }}
        />
      ) : null}
    </Stack>
  );
};
