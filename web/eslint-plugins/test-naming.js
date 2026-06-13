// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** @type {import('eslint').Rule.RuleModule} */
const noSpecSuffix = {
  meta: {
    type: 'suggestion',
    docs: { description: 'Enforce .test. suffix; disallow .spec.' },
  },
  create(context) {
    const filename = context.filename ?? context.getFilename?.();
    if (/\.spec\.[jt]sx?$/.test(filename)) {
      return {
        Program(node) {
          context.report({
            node,
            message: 'Use .test. suffix instead of .spec. (rename to *.test.ts / *.test.tsx).',
          });
        },
      };
    }
    return {};
  },
};

/** @type {import('eslint').ESLint.Plugin} */
export default {
  rules: {
    'no-spec-suffix': noSpecSuffix,
  },
};
