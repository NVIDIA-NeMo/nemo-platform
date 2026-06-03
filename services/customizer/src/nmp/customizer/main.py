# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Customizer service entry point."""

from nmp.customizer.service import CustomizerService

# Global service instance for platform integration
service = CustomizerService()
