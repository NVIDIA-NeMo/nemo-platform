# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Notebook display helpers for Anonymizer SDK result objects."""

from __future__ import annotations

import pandas as pd
from anonymizer.interface.display import render_record_html

ORIGINAL_TEXT_COLUMN_ATTR = "original_text_column"
DEFAULT_TEXT_COLUMN = "text"


class DisplayRecordMixin:
    """Match upstream Anonymizer result ``display_record`` behavior."""

    _display_cycle_index: int

    def _display_trace_dataframe(self) -> pd.DataFrame:
        raise NotImplementedError

    def display_record(self, index: int | None = None) -> None:
        """Render a record with entity highlights and replacement map in a notebook."""
        trace_dataframe = self._display_trace_dataframe()
        i = index if index is not None else self._display_cycle_index
        if i < 0 or i >= len(trace_dataframe):
            raise IndexError(f"Record index {i} is out of bounds for {len(trace_dataframe)} records.")

        row = trace_dataframe.iloc[i]
        html_str = render_record_html(
            row,
            record_index=i,
            resolved_text_column=get_original_text_column(trace_dataframe),
        )

        try:
            from IPython.display import HTML, display

            display(HTML(html_str))
        except ImportError:
            print(html_str)

        if index is None:
            self._display_cycle_index = (self._display_cycle_index + 1) % len(trace_dataframe)


def set_original_text_column(df: pd.DataFrame, text_column: str | None) -> pd.DataFrame:
    if text_column:
        df.attrs[ORIGINAL_TEXT_COLUMN_ATTR] = text_column
    return df


def get_original_text_column(df: pd.DataFrame) -> str:
    value = df.attrs.get(ORIGINAL_TEXT_COLUMN_ATTR)
    if isinstance(value, str) and value:
        return value
    return DEFAULT_TEXT_COLUMN
