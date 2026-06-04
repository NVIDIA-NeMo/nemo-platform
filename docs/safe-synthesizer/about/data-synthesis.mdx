<a id="about-data-synthesis"></a>
# Data Synthesis

The synthesizer component is the main component of the {{nss_short_name}} product. It uses LLM-based fine-tuning to generate realistic synthetic data that maintains the utility of your original dataset while providing privacy protection.

## How It Works

{{nss_short_name}} employs a novel approach to synthetic data generation:

1. **Tabular Fine-Tuning**: Fine-tunes a language model on your tabular data to learn patterns, correlations, and statistical properties
2. **Generation**: Uses the fine-tuned model to generate new synthetic records that maintain data utility
3. **Privacy Protection**: Optionally applies differential privacy during training for mathematical privacy guarantees

Creating synthetic versions of private data allows you to unlock insights without compromising privacy, enabling downstream use cases like AI model training and analytics.

## Key Features

### LLM-Based Fine-Tuning

{{nss_short_name}} adapts language models to understand and generate tabular data:

- Converts tabular data into text sequences suitable for LLM training
- Fine-tunes on your dataset to capture patterns and correlations
- Generates new records that maintain statistical properties with no one-to-one mapping to original records
- Supports various model sizes and architectures

### Supported Data Types

{{nss_short_name}} supports diverse tabular data:

- **Numeric**: Continuous and discrete numerical values
- **Categorical**: Text labels and categories
- **Text**: Free-form text fields
- **Temporal**: Event sequences and time series

### Differential Privacy

A high level of privacy protection is achieved simply through the process of generating synthetic data, and is often a sufficient balance between privacy and utility. For use cases that require maximum privacy, you can fine-tune with differential privacy.

Differential privacy (DP) is the gold standard for privacy protection, providing mathematical guarantees that individual records cannot be identified. When you enable DP, {{nss_short_name}} introduces calibrated noise during model training to ensure that the synthetic data generation process is provably private.

#### Mathematical Guarantee

DP ensures that the output of an algorithm is nearly identical whether or not any single record is included in the training data:

```output
P[M(D1) ∈ S] ≤ exp(ε) × P[M(D2) ∈ S] + δ
```

Where:

- `M` is the mechanism (trained model)
- `D1` and `D2` are datasets differing by one record
- `ε` (epsilon) controls privacy loss - lower values provide stronger privacy
- `δ` (delta) is the failure probability
- `S` is any subset of possible outputs

#### DP-SGD Implementation

{{nss_short_name}} uses Differentially Private Stochastic Gradient Descent (DP-SGD) to add privacy guarantees during model training:

1. **Per-sample gradient computation** - Calculate gradients for each training example individually
2. **Gradient clipping** - Clip L2 norm to `per_sample_max_grad_norm` to bound sensitivity
3. **Noise injection** - Add calibrated Gaussian noise to gradients based on privacy budget
4. **Privacy accounting** - Track cumulative privacy loss using Rényi Differential Privacy (RDP)

By default, *record-level* differential privacy is used. When `group_training_examples_by` is set, *group-level* privacy applies, meaning guarantees cover entire groups of records rather than individual records.

#### Privacy vs Utility Trade-off

Enabling DP provides strong privacy guarantees but affects synthetic data quality:

- **Lower epsilon** = stronger privacy, but more noise and potentially lower utility
- **Training speed** - DP training is usually 2-4x slower due to per-sample gradient computation
- **Data requirements** - DP works best with larger datasets (10,000+ records recommended, compared to 1,000+ records without DP)
- **Quality impact** - Added noise may reduce statistical fidelity of synthetic data

#### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dp_enabled` | bool | `false` | Enable differential privacy |
| `epsilon` | float | `8.0` | Privacy budget (lower = more private, typical range: 4-12) |
| `delta` | float/auto | `"auto"` | Failure probability (auto = 1/n^1.2 based on dataset size) |
| `per_sample_max_grad_norm` | float | `1.0` | Gradient clipping threshold |

#### Guidelines

**Starting point:** Begin with ε ∈ [8, 12] and reduce as needed based on privacy requirements and acceptable quality trade-offs.

**Delta calculation:** Use `"auto"` (recommended), which sets δ = 1/n^1.2 based on dataset size n. Manual values are typically between 1e-6 and 1e-4.

**Data size:** DP performs best with 10,000+ training records. Smaller datasets may experience significant quality degradation due to the noise required for privacy guarantees.

For hands-on guidance, refer to [differential-privacy](../tutorials/differential-privacy.md). For complete parameter documentation, refer to [reference](reference.md).

## Configuration

Synthesis behavior is controlled through configuration parameters:

- **Training**: Model selection, training parameters, sequence configuration
- **Generation**: Number of records, temperature, sampling strategies
- **Privacy**: Differential privacy parameters (epsilon, delta, clipping)

For a complete list of all available parameters and their defaults, refer to [reference](reference.md).

## Related Topics

- [reference](reference.md): Complete parameter reference
- [differential-privacy](../tutorials/differential-privacy.md): Learn about differential privacy in practice
- [index](../tutorials/index.md): More tutorials
