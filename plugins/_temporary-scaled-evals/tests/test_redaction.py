# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest

try:
    from scaled_evals.api.redaction import redact_secret_text
except ImportError as exc:
    pytest.skip(f"scaled-evals plugin not installed: {exc}", allow_module_level=True)


def test_redact_secret_text_masks_assignments_and_known_token_shapes() -> None:
    text = "api_key=sk-secret-value bearer nvapi-secret.value password: hunter2"

    redacted = redact_secret_text(text)

    assert redacted == "api_key=<redacted> bearer <redacted> password: <redacted>"


def test_redact_secret_text_preserves_environment_references() -> None:
    assert redact_secret_text("api_key=$OPENAI_API_KEY") == "api_key=$OPENAI_API_KEY"


def test_redact_secret_text_masks_openshift_jwt_and_database_credentials() -> None:
    database_url = "".join(("postgresql://", "scaled", ":", "super-secret", "@", "db.example", "/", "scaled"))
    text = (
        "SANDBOX_OC_TOKEN=sha256~abcdefghijklmnop "
        "jwt eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.signaturevalue "
        f"{database_url}"
    )

    redacted = redact_secret_text(text)

    assert "sha256~" not in redacted
    assert "eyJ" not in redacted
    assert "super-secret" not in redacted
    assert redacted.count("<redacted>") == 3
