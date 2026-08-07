# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Guards the lazy (PEP 562) public surface of ``nemo_evaluator_sdk/__init__.py``.

Importing any submodule runs the package ``__init__`` first, so a single convenience
``from nemo_evaluator_sdk.… import …`` added at module scope silently re-drags the whole
backend/benchmark/metric stack into every consumer that only wanted ``agent_eval`` — the
regression these tests exist to catch (AALGO-429).
"""

import json
import subprocess
import sys

import pytest

# Imported out-of-process on purpose: by the time this module runs under pytest, sibling suites
# have already pulled the execution stack into sys.modules, so an in-process check proves nothing.
_PROBE = """
import json, sys
from nemo_evaluator_sdk.agent_eval.runtimes.harbor_runtime import HarborAgentTaskRunner
assert HarborAgentTaskRunner is not None
print(json.dumps(sorted(sys.modules)))
"""


def test_agent_eval_import_does_not_pull_the_execution_stack() -> None:
    """The optimizer imports only ``agent_eval``; it must not pay for backends and benchmarks.

    Beyond start-up cost, every module loaded here is a package whose import failure becomes an
    SDK-path failure at evaluation time. Keeping the boundary tight is what lets the consumer's
    deferred SDK import actually contain a broken install.
    """
    proc = subprocess.run([sys.executable, "-c", _PROBE], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr

    # Last line only: the child inherits the environment, so a sitecustomize banner or an
    # import-time print() would otherwise turn this into an opaque JSONDecodeError.
    modules = set(json.loads(proc.stdout.strip().splitlines()[-1]))

    leaked = sorted(name for name in modules if name.startswith("nemo_evaluator_sdk.execution"))
    assert leaked == [], f"the package __init__ re-drags the execution stack: {leaked}"

    # Exactly the packages the eager __init__ used to drag in; each one goes red if it returns.
    # rouge_score is deliberately absent: metrics/rouge.py already defers it into a
    # cached_property, so it was never on this path and asserting it would prove nothing.
    heavy = {"openai", "sacrebleu", "zstandard"} & modules
    assert heavy == set(), f"heavy metric-stack dependencies pulled in: {sorted(heavy)}"

    # A canary, not a spec: measured at 483 modules when this landed, down from 1416. Raise the
    # bound if a genuine agent_eval dependency lands; a jump of >100 means something re-drags a
    # barrel module and should be investigated rather than accommodated.
    assert len(modules) < 700, f"agent_eval import surface grew to {len(modules)} modules"


def test_every_public_name_resolves() -> None:
    """``__all__`` and ``_LAZY_ATTRS`` must not drift apart.

    A typo in the lazy table is invisible until a consumer hits that one attribute, so resolve
    the whole surface in one pass.
    """
    import nemo_evaluator_sdk

    for name in nemo_evaluator_sdk.__all__:
        assert getattr(nemo_evaluator_sdk, name) is not None, name

    assert set(nemo_evaluator_sdk.__all__) <= set(dir(nemo_evaluator_sdk))


def test_unknown_attribute_raises_attribute_error() -> None:
    """``from pkg import submodule`` and ``hasattr`` both rely on ``AttributeError`` here."""
    import nemo_evaluator_sdk

    with pytest.raises(AttributeError):
        nemo_evaluator_sdk.NoSuchName  # noqa: B018

    # The submodule fallback that AttributeError enables.
    from nemo_evaluator_sdk import values

    assert values.__name__ == "nemo_evaluator_sdk.values"
