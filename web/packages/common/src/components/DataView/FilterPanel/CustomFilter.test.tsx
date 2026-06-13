// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CustomFilterControl } from '@nemo/common/src/components/DataView/FilterPanel/CustomFilter';
import { render, screen } from '@testing-library/react';

function makeColumn(renderFilter: ReturnType<typeof vi.fn>) {
  return {
    id: 'base_model',
    getCanFilter: () => true,
    getFilterValue: () => undefined,
    setFilterValue: vi.fn(),
    columnDef: {
      header: 'Base Model',
      meta: { filter: { type: 'custom' as const, renderFilter } },
    },
  };
}

describe('CustomFilterControl', () => {
  it('calls renderFilter and renders its output', () => {
    const renderFilter = vi.fn(() => <span data-testid="custom-content">Custom</span>);
    const col = makeColumn(renderFilter);

    render(<CustomFilterControl column={col as never} />);

    expect(renderFilter).toHaveBeenCalled();
    expect(screen.getByTestId('custom-content')).toBeInTheDocument();
  });
});
