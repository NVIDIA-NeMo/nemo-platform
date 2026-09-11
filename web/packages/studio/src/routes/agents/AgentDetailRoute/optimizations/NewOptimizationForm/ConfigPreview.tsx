// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CodeSnippet } from '@nvidia/foundations-react-core';
import { type FC } from 'react';

export interface ConfigPreviewProps {
  config: string;
}

/** The generated YAML, exactly as it will be staged into the study's fileset. Read-only: the form
 *  above owns every value in it, so an edit here would be overwritten on the next keystroke. */
export const ConfigPreview: FC<ConfigPreviewProps> = ({ config }) => (
  <div className="pt-density-md">
    <CodeSnippet value={config} language="yaml" kind="block" />
  </div>
);
