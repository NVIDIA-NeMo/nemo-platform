// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Text } from '@nvidia/foundations-react-core';
import cn from 'classnames';
import { ComponentProps, FC } from 'react';

interface LeftTruncatedTextProps extends ComponentProps<typeof Text> {
  /** The string to render with left-side truncation (ellipsis at the start). */
  children: string;
}

/**
 * Renders text that truncates from the left, keeping the end of the string
 * (e.g. the file name at the tail of a long path) visible. The `<bdi>` wrapper
 * preserves the string's natural character order despite the RTL flip that
 * moves the ellipsis to the start.
 *
 * Defaults to `kind="inherit"` so it adopts the surrounding text style; pass
 * `kind` (or any other Text prop) to override.
 */
export const LeftTruncatedText: FC<LeftTruncatedTextProps> = ({
  children,
  className,
  kind = 'inherit',
  ...props
}) => (
  <Text {...props} kind={kind} dir="rtl" className={cn('block truncate text-left', className)}>
    <bdi>{children}</bdi>
  </Text>
);
