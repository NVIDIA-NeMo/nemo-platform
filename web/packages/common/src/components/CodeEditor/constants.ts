// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { BasicSetupOptions } from '@uiw/react-codemirror';

export enum ContentType {
  JSON = 'json',
  JSONL = 'jsonl',
  JAVASCRIPT = 'javascript',
  PYTHON = 'python',
  YAML = 'yaml',
  TEXT = 'text',
}

export const BASIC_SETUP: BasicSetupOptions = {
  lineNumbers: false, // Line numbers are toggled by props
  highlightActiveLineGutter: true,
  foldGutter: false, // Fold gutter is toggled by props
  dropCursor: true,
  allowMultipleSelections: true,
  indentOnInput: true,
  bracketMatching: true,
  closeBrackets: true,
  autocompletion: false,
  rectangularSelection: true,
  crosshairCursor: true,
  highlightActiveLine: true,
  highlightSelectionMatches: true,
  closeBracketsKeymap: true,
  searchKeymap: true,
  foldKeymap: true,
  completionKeymap: true,
  lintKeymap: true,
  tabSize: 2,
};
