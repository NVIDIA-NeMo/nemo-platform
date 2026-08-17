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

#: The time-series metrics every backend has in common: the loss family, the
#: learning rate, and the gradient norm. Written as patterns rather than literal
#: names so one entry covers both phases (``train_loss`` and ``val_loss``), the
#: algorithm-specific members of a family (``train_sft_loss``,
#: ``val_preference_loss``), and the dataset-qualified names NeMo-RL produces for
#: a second validation set (``val_heldout_loss``).
DIAGNOSTIC_TIME_SERIES = ("*_loss", "*_lr", "*_grad_norm")

#: Everything, spelled explicitly. This is what a user passes to opt out of a
#: backend's default and record a curve for every metric it emits; leaving the
#: field unset means "the backend's default" instead.
ALL_METRICS = ("*",)


class ProgressReportingConfig(BaseModel):
    """How much detail training progress is reported to the Jobs service with.

    Two knobs, and they multiply: the stored blob is
    ``time_series_metrics x max_points``. ``max_points`` bounds how finely each
    series is sampled; ``time_series_metrics`` bounds how many series there are.

    The split the second knob expresses is that a training run produces two kinds
    of metric. A few are worth a *history* -- the loss, the learning rate, the
    gradient norm -- because their shape over time is the whole point. The rest
    are throughput and accounting counters (``tps``, ``mem``, ``num_label_tokens``,
    ``global_valid_toks``) whose *current* value is all anyone reads. Both kinds
    are always reported; only the first kind is accumulated.

    There is no second list for the scalars, and deliberately: the set of metric
    names comes from the training framework at runtime, not from this config, so
    any pair of lists would leave a third category of names in neither. Naming
    the series and letting everything else be a scalar is the only partition that
    stays correct when a framework adds a metric.
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
    time_series_metrics: list[str] | None = Field(
        default=None,
        description=(
            "Which metrics are recorded as a time series, named exactly as they appear in the "
            "job's status details and so qualified by phase: 'train_loss', 'val_accuracy'. "
            "Glob patterns are accepted, so '*_loss' covers every loss on both phases and '*' "
            "records everything. Omit the field to take the backend's default, which keeps the "
            "loss, learning rate and gradient norm. "
            "Every metric the run produces is reported either way -- one not matched here is "
            "still sent as a current value on every report, it simply has no history, so a "
            "throughput counter like 'train_tps' costs one number rather than several hundred. "
            "The job log names what was matched and what was not."
        ),
    )
