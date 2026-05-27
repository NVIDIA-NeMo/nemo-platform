# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0


class NDDError(Exception):
    "Shared base for all data_designer_nemo errors."


class NDDInternalError(NDDError): ...


class NDDInvalidConfigError(NDDError): ...
