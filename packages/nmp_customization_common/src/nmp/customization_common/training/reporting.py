# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""How much detail training progress is reported with.

One fragment, embedded in every backend's schedule section under one field name,
so the docs, the SDK and Studio can treat the knob uniformly rather than learning
three spellings of it. Deliberately *not* a
:class:`~nmp.customization_common.schema.NamespacedModel`: that base exists to
keep two backends' same-named-but-different models from colliding in the merged
``/apis/customization`` spec, and this is the opposite case -- one model, shared
on purpose, which should emit one component.

Kept in its own module rather than beside the callback that consumes it so the
API layer can import the schema without pulling in the platform SDK that
:mod:`nmp.customization_common.training.progress` needs.
"""

from pydantic import BaseModel, Field

#: Points kept on each metric curve, per reporting path. Roughly the number a
#: chart a few hundred pixels wide can draw distinctly, and past which the extra
#: points cost more than they show.
#:
#: It is also what bounds the cost of reporting, which is why it is a ceiling and
#: not a target -- see the payload note in
#: :mod:`nmp.customization_common.training.callbacks`.
DEFAULT_MAX_POINTS = 200


class ProgressReportingConfig(BaseModel):
    """How much detail training progress is reported to the Jobs service with.

    Two knobs, and they multiply: the stored blob is ``curves x max_points``.
    ``max_points`` bounds how finely each curve is sampled, ``curves`` bounds how
    many curves there are.
    """

    max_points: int = Field(
        default=DEFAULT_MAX_POINTS,
        gt=0,
        description=(
            "Maximum points recorded on each metric curve, applied independently to the training "
            "and validation curves. Lower values reduce reporting overhead on long runs; higher "
            "values give a finer chart at proportionally more cost, including a little more time "
            "spent reporting rather than training. This can only thin what the training framework "
            "produces, never add to it: a run that logs 40 times reports 40 points whatever this "
            "is set to."
        ),
    )
    curves: list[str] | None = Field(
        default=None,
        description=(
            "Metric names to record as charted curves, given unqualified by phase -- 'loss' "
            "covers both the training and validation curves. Omit for every metric the backend "
            "produces, which is the most detail and the most cost. A metric left out is still "
            "reported as a current value on every report; only its history is dropped, so a "
            "throughput counter like 'tps' costs one number rather than several hundred. Which "
            "names a backend produces is listed in the job log the first time one is excluded."
        ),
    )
