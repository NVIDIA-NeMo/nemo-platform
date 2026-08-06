# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from nemo_evaluator_sdk.agent_eval.runtimes.fabric.hook_loading import (
    FabricTaskHookLoadError,
    load_fabric_task_hook,
)
from nemo_evaluator_sdk.agent_eval.runtimes.fabric.hooks import FabricTaskRunSession


class _DemoHook:
    def __init__(self, label: str = "default") -> None:
        self.label = label

    def prepare(self, **kwargs: Any) -> Any:
        return kwargs.get("config")

    def after_success(self, **kwargs: Any) -> dict[str, Any] | None:
        return {"label": self.label}

    def cleanup(self, **kwargs: Any) -> None:
        return None


def test_load_fabric_task_hook_none() -> None:
    assert load_fabric_task_hook(None) is None


def test_load_fabric_task_hook_from_path(tmp_path: Path) -> None:
    module_path = tmp_path / "my_hook.py"
    module_path.write_text(
        """
class MyHook:
    def __init__(self, tag="x"):
        self.tag = tag
    def prepare(self, **kwargs):
        return kwargs["config"]
    def after_success(self, **kwargs):
        return {"tag": self.tag}
    def cleanup(self, **kwargs):
        pass
""",
        encoding="utf-8",
    )
    hook = load_fabric_task_hook({"path": str(module_path), "attr": "MyHook", "tag": "from-file"})
    assert hook is not None
    assert hook.after_success(task=MagicMock(), result=None, session=FabricTaskRunSession()) == {
        "tag": "from-file"
    }


def test_load_fabric_task_hook_from_ref_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Put a tiny package on sys.path so ref works without platform deps.
    pkg = tmp_path / "author_hooks"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "hook.py").write_text(
        """
class AuthorHook:
    def __init__(self, n=1):
        self.n = n
    def prepare(self, **kwargs):
        return kwargs["config"]
    def after_success(self, **kwargs):
        return {"n": self.n}
    def cleanup(self, **kwargs):
        pass
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    hook = load_fabric_task_hook({"ref": "author_hooks.hook:AuthorHook", "n": 7})
    assert hook is not None
    assert hook.after_success(task=MagicMock(), result=None, session=FabricTaskRunSession()) == {"n": 7}


def test_load_fabric_task_hook_from_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    class _EP:
        name = "demo"

        def load(self) -> type[_DemoHook]:
            return _DemoHook

    monkeypatch.setattr(
        "nemo_evaluator_sdk.agent_eval.runtimes.fabric.hook_loading.importlib.metadata.entry_points",
        lambda group: [_EP()] if group == "nemo.fabric.task_hooks" else [],
    )
    hook = load_fabric_task_hook({"type": "demo", "label": "via-ep"})
    assert isinstance(hook, _DemoHook)
    assert hook.label == "via-ep"


def test_load_fabric_task_hook_rejects_multiple_modes(tmp_path: Path) -> None:
    path = tmp_path / "h.py"
    path.write_text("class H:\n    pass\n", encoding="utf-8")
    with pytest.raises(FabricTaskHookLoadError, match="only one"):
        load_fabric_task_hook({"ref": "x:Y", "path": str(path), "attr": "H"})


def test_load_fabric_task_hook_missing_entry_point() -> None:
    with pytest.raises(FabricTaskHookLoadError, match="No entry point"):
        load_fabric_task_hook({"entry_point": "does-not-exist-zzzz"})
