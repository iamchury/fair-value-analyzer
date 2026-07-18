# Fair Value Analyzer

Fair Value Analyzer estimates stock fair value from Yahoo Finance fundamentals,
EPS growth, Target PE, Treasury-yield macro adjustments, and buy/sell thresholds.

## Features

- Download current stock fundamentals from Yahoo Finance.
- Calculate EPS growth from trailing EPS and forward EPS.
- Recommend Target PE with configurable growth, PEG, sector, and current-PE rules.
- Apply the US 10-year Treasury yield macro adjustment.
- Calculate base fair value, adjusted fair value, buy price, sell price, discount,
  upside, and recommendation.
- Run a single symbol or a configured batch of symbols.
- Optionally compare the automatic fair value with symbol-specific research
  valuation profiles.

## Default Symbols

The default batch configuration lives in `config/stocks.yaml`.

## Basic Formula

```text
base_fair_value = forward_eps * recommended_target_pe
adjusted_fair_value = base_fair_value * macro_adjustment_multiplier
```

## Usage

Run one stock:

```bash
python -m src.main LITE
```

Inspect Yahoo EPS source fields for one stock:

```bash
python -m src.main MU --inspect-eps
```

Run the configured batch:

```bash
python -m src.main --stocks config/stocks.yaml
```

Use a custom valuation configuration:

```bash
python -m src.main LITE --config config/valuation.yaml
```

Use explicit EPS selection for fair value:

```bash
python -m src.main MU --eps-selection config/eps_selection.yaml
```

Use explicit EPS selection and industry valuation policy:

```bash
python -m src.main MU --eps-selection config/eps_selection.yaml --industry-policies config/industry_policies.yaml
```

Use all current independent diagnostic model options:

```bash
python -m src.main MU --profiles config/valuation_profiles.yaml --eps-selection config/eps_selection.yaml --industry-policies config/industry_policies.yaml --analyst-consensus config/analyst_consensus.yaml
```

Show unified valuation snapshots for diagnostics:

```bash
python -m src.main MU --profiles config/valuation_profiles.yaml --eps-selection config/eps_selection.yaml --industry-policies config/industry_policies.yaml --show-snapshots
```

Use research profiles and EPS selection together:

```bash
python -m src.main MU --profiles config/valuation_profiles.yaml --eps-selection config/eps_selection.yaml
```

## Valuation Profiles

Optional symbol-specific research profiles can be loaded with
`config/valuation_profiles.yaml`.

Run a single symbol with profiles:

```bash
python -m src.main LITE --profiles config/valuation_profiles.yaml
```

Run the configured batch with profiles:

```bash
python -m src.main --stocks config/stocks.yaml --profiles config/valuation_profiles.yaml
```

The profile file contains configured research assumptions such as valuation
style, valuation EPS, EPS fiscal year, research Target PE, PEG metadata, optional
DCF fair-value reference, and source note.

Research fair value uses the existing Treasury macro multiplier:

```text
research_base_fair_value = valuation_eps * target_pe
research_adjusted_fair_value = research_base_fair_value * macro_adjustment_multiplier
```

`use_peg_adjustment` is currently metadata only. It is displayed in reports but
does not alter the research Target PE calculation.

## EPS Source Inspector

The EPS source inspector is a diagnostic command. It shows raw Yahoo EPS fields
and available annual or quarterly estimate rows when yfinance exposes them.

Period inference is conservative. `UNKNOWN` means the application cannot
reliably identify the fiscal period for Yahoo `forwardEps`. The inspector does
not alter the automatic valuation calculation, and it is not a valuation
recommendation. Yahoo may not expose enough metadata to distinguish GAAP,
non-GAAP, or adjusted EPS.

## EPS Selection

Inspection of recent MU and LITE data showed Yahoo `forwardEps` behaving like a
next-fiscal-year estimate for those tickers. That must not be assumed
universally.

EPS selection explicitly chooses the EPS used for fair value. The default
behavior remains legacy Yahoo `forwardEps`, so existing commands produce the
same automatic valuation unless `--eps-selection` is supplied.

Supported methods:

- `LEGACY_FORWARD`
- `CURRENT_YEAR`
- `NEXT_YEAR`
- `WEIGHTED_CURRENT_NEXT`
- `MANUAL`

In this phase, EPS growth and Target PE still use legacy Yahoo `forwardEps`.
The selected EPS affects fair value only. When selected EPS materially differs
from Yahoo `forwardEps`, the report shows a warning. EPS selection is a
valuation assumption, not a guarantee of accuracy.

## Industry Valuation Policies

Industry valuation policies explicitly choose how the automatic Target PE is
used for fair value. Omitting `--industry-policies` preserves legacy behavior.

Initial styles are:

- `CYCLICAL`
- `GROWTH`
- `QUALITY_GROWTH`

CYCLICAL policies may use a fixed conservative Target PE. GROWTH and
QUALITY_GROWTH policies may retain calculated Target PE components while
clipping the result to narrower policy-specific ranges. Yahoo sector labels
alone do not determine the policy; symbol mappings are explicit assumptions in
`config/industry_policies.yaml`.

In this phase, the original Target PE engine is still calculated and reported.
When a policy applies, fair value uses the policy Target PE, while the report
shows both the original Target PE and the policy Target PE.

## Analyst Consensus

Analyst consensus is an independent valuation model enabled with
`--analyst-consensus config/analyst_consensus.yaml`. It does not affect
BUY/HOLD/SELL, automatic PER fair value, research fair value, EPS selection,
Target PE, or industry policy in this phase.

The model uses Yahoo analyst target mean, high, and low. The midpoint is the
high/low midpoint, not a true median. Wide target dispersion reduces consensus
quality, and Yahoo may not provide a reliable target publication date.

Treasury adjustment is disabled by default because analyst targets may already
include market-rate assumptions. Analyst targets are market expectations, not
objective intrinsic value.

## Unified Valuation Snapshots

`ValuationSnapshot` is a common read-only result contract for valuation model
outputs. Existing model-specific result classes remain authoritative, and
snapshot adapters only copy already calculated values into a common shape.

The current snapshot adapters cover Automatic PER, Research PER, and externally
supplied DCF Reference values. DCF Reference is not calculated by the
application. Model-local confidence is descriptive metadata only; it is not a
final investment confidence score.

Omitting `--show-snapshots` preserves existing output. Snapshots prepare the
repository for future analyst, agreement, and fair-value range engines without
changing current valuation formulas or recommendations.
