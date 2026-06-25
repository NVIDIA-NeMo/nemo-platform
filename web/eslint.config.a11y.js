// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import tsEslintParser from '@typescript-eslint/parser';
import jsxA11yPlugin from 'eslint-plugin-jsx-a11y';
import globals from 'globals';

export default [
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      parser: tsEslintParser,
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    plugins: {
      'jsx-a11y': jsxA11yPlugin,
    },
    rules: {
      // All non-deprecated jsx-a11y rules as warnings.
      ...Object.fromEntries(
        Object.entries(jsxA11yPlugin.rules)
          .filter(([, rule]) => !rule.meta?.deprecated)
          .map(([rule]) => [`jsx-a11y/${rule}`, 'warn'])
      ),
    },
  },
];
