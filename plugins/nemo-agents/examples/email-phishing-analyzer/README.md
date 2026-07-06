# Email Phishing Analyzer

The NeMo Platform first-mile example agent. A ReAct agent that classifies an email
body as **phishing** or **benign** using an LLM-backed `email_phishing_analyzer`
tool. Ported from
[NeMo-Agent-Toolkit](https://github.com/NVIDIA/NeMo-Agent-Toolkit/tree/develop/examples/evaluation_and_profiling/email_phishing_analyzer)
and wired for the platform (traffic routes through the Inference Gateway — no
`base_url`/`api_key` in config).

This example is what `nemo setup` deploys as the default demo agent.

## What ships here

| File | Purpose |
| --- | --- |
| `src/email_phishing_analyzer/register.py` | Registers the `email_phishing_analyzer` tool and imports the classification evaluator. |
| `src/email_phishing_analyzer/classification_evaluator.py` | `email_phishing_classification` evaluator: binary recall/precision/accuracy/F1 from a confusion matrix. |
| `src/email_phishing_analyzer/email-phishing-agent.yml` | The ReAct agent workflow. |
| `src/email_phishing_analyzer/email-phishing-eval.yml` | Classification benchmark (recall headline + precision/accuracy/F1, plus profiler token/latency). |
| `src/email_phishing_analyzer/email-phishing-optimize.yml` | Optuna hyperparameter tuning to maximize recall. |
| `src/email_phishing_analyzer/email-phishing-eval-data.csv` | 400-row balanced (200/200) labeled dataset. |
| `scripts/generate_dataset.py` | Deterministic generator that (re)produces the dataset. |

## Install

```bash
uv pip install -e plugins/nemo-agents/examples/email-phishing-analyzer
```

This registers the `nat.components` entry point so `_type: email_phishing_analyzer`
(tool) and `_type: email_phishing_classification` (evaluator) resolve.

## Deploy and invoke

```bash
nemo agents create --name email-phishing-analyzer \
  --agent-config plugins/nemo-agents/examples/email-phishing-analyzer/src/email_phishing_analyzer/email-phishing-agent.yml
nemo agents deploy --agent email-phishing-analyzer
nemo agents invoke --agent email-phishing-analyzer \
  --input "Dear customer, verify your account at http://verify-example.com or it will be suspended."
```

## Evaluate (classification benchmark)

```bash
nemo agents evaluate run \
  --eval-config plugins/nemo-agents/examples/email-phishing-analyzer/src/email_phishing_analyzer/email-phishing-eval.yml \
  --agent email-phishing-analyzer
```

The scorecard reports **recall** (fraction of real phishing emails caught — the
headline metric), precision, accuracy, and F1. Recall drops visibly if a swapped
model starts missing phishing, which is the intended "caught regression" signal.

## Regenerate the dataset

```bash
python plugins/nemo-agents/examples/email-phishing-analyzer/scripts/generate_dataset.py
```

The content is synthetic (no real PII) and stands in for a Data Designer + Safe
Synthesizer pipeline.
