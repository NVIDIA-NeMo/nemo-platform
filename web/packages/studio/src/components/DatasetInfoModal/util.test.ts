// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getHumanReadableFileSize } from '@studio/util/files';

const kb = 1024;
const mb = kb * 1024;
const gb = mb * 1024;
const tb = gb * 1024;
const pb = tb * 1024;

describe('getHumanReadableFileSize', () => {
  it('formats empty file correctly', () => {
    expect(getHumanReadableFileSize(0)).toEqual('empty file');
  });
  it('formats the happy paths correctly', () => {
    expect(getHumanReadableFileSize(kb)).toEqual('1kB');
    expect(getHumanReadableFileSize(kb + 100)).toEqual('1.1kB');
    expect(getHumanReadableFileSize(2 * mb + 5)).toEqual('2MB');
    expect(getHumanReadableFileSize(2.9 * gb)).toEqual('2.9GB');
    expect(getHumanReadableFileSize(3 * tb)).toEqual('3TB');
    expect(getHumanReadableFileSize(4 * pb)).toEqual('4PB');
  });
  it('formats sizes bigger than 1024 pb correctly', () => {
    expect(getHumanReadableFileSize(1500 * pb)).toEqual('1,500PB');
  });
});
