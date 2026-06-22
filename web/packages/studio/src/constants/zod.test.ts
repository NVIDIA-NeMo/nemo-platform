// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { projectNameInputSchema, URNSchema } from '@studio/constants/zod';

describe('zod constants schemas', () => {
  it.each([
    'test-project',
    'test_project',
    'test.project',
    'test-project-123',
    'test_project_123',
    'test.project.123',
  ])('should validate project name input schema', (name) => {
    const result = projectNameInputSchema.safeParse(name);
    expect(result.success).toBe(true);
  });
  it.each([
    ['missing forward slash', 'test-project', false],
    ['valid URN', 'test-project/test-project', true],
    ['missing namespace', 'test-project', false],
    ['missing name', 'test-project/', false],
    ['missing namespace and name', 'test-project/', false],
    ['invalid characters', 'test!project/test!project', false],
  ])('should validate URN schema for %s', (_label, name, shouldSucceed) => {
    const result = URNSchema.safeParse(name);
    expect(result.success).toBe(shouldSucceed);
  });
});
