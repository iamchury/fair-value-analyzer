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

Run the local web dashboard:

```bash
streamlit run app.py
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

Show snapshot model agreement diagnostics:

```bash
python -m src.main MU --profiles config/valuation_profiles.yaml --eps-selection config/eps_selection.yaml --industry-policies config/industry_policies.yaml --analyst-consensus config/analyst_consensus.yaml --agreement-config config/agreement_engine.yaml --show-agreement
```

Show RSI 50 momentum reference and fair-value range diagnostics:

```bash
python -m src.main MU --profiles config/valuation_profiles.yaml --eps-selection config/eps_selection.yaml --industry-policies config/industry_policies.yaml --analyst-consensus config/analyst_consensus.yaml --agreement-config config/agreement_engine.yaml --momentum-config config/momentum_reference.yaml --range-config config/fair_value_range.yaml --show-momentum --show-range
```

Show Recommendation V2 diagnostics:

```bash
python -m src.main MU --profiles config/valuation_profiles.yaml --eps-selection config/eps_selection.yaml --industry-policies config/industry_policies.yaml --analyst-consensus config/analyst_consensus.yaml --agreement-config config/agreement_engine.yaml --momentum-config config/momentum_reference.yaml --range-config config/fair_value_range.yaml --recommendation-v2-config config/recommendation_v2.yaml --show-recommendation-v2
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

The model uses Yahoo analyst target mean, high, and low from the already
downloaded company data. It produces a `ValuationSnapshot` directly, with
`ANALYST_CONSENSUS` as the model type and `MARKET_EXPECTATION` as the value
type. The midpoint is the high/low midpoint, not a true median. Wide target
dispersion reduces model-local confidence.

Treasury adjustment is disabled by default because analyst targets may already
include market-rate assumptions. Analyst targets are market expectations, not
objective intrinsic value.

## RSI 50 Momentum Reference

The optional RSI momentum reference is enabled with `--momentum-config
config/momentum_reference.yaml` and displayed with `--show-momentum`. It uses
daily price history, prefers adjusted close when available, calculates Wilder
RSI(14), and reports the price at the most recent RSI 50 neutral-line event.

An upward event moves from below 50 to 50 or above. A downward event moves from
above 50 to 50 or below. Consecutive exact-50 rows are de-duplicated using the
nearest earlier non-50 RSI. If no crossing exists and fallback is enabled, the
result is labeled `FALLBACK` and uses the most recent RSI point nearest to 50;
that fallback is not described as a crossing.

The RSI reference is technical market-momentum context only. It is not
intrinsic value, not a trading signal, and not part of BUY/HOLD/SELL
recommendation logic.

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

## Agreement Engine

Agreement Engine V1 is enabled with `--agreement-config
config/agreement_engine.yaml` and displayed with `--show-agreement`. It consumes
only `ValuationSnapshotCollection`; it does not download Yahoo data, recalculate
valuation models, or change BUY/HOLD/SELL recommendations.

The engine separates intrinsic values from supporting references and market
expectations. `INTRINSIC_VALUE` snapshots form the core agreement set.
`REFERENCE_VALUE` snapshots can be included in an extended intrinsic cluster,
while `MARKET_EXPECTATION` snapshots such as analyst consensus are compared
against the intrinsic median without controlling intrinsic agreement by default.

Pairwise model differences use the symmetric formula:

```text
abs(A - B) / ((A + B) / 2) * 100
```

Outliers use a one-sided comparison to the relevant median. The default
thresholds are configured in `config/agreement_engine.yaml`: strong/moderate/weak
pairwise agreement at 10%, 20%, and 35%, and possible/extreme outliers at 50%
and 80%. Analyst consensus can therefore be shown as a market-expectation
outlier without weakening strong agreement between the core intrinsic models.

## Fair Value Range

The optional Fair Value Range Engine is enabled with `--range-config
config/fair_value_range.yaml` and displayed with `--show-range`. It consumes
the existing snapshot collection, the existing Agreement Engine result when
supplied, current market price, and optionally the RSI momentum reference. It
does not recalculate Automatic PER, Research PER, DCF Reference, or Analyst
Consensus.

The conservative value uses the lowest valid intrinsic or supporting reference
value after configured outlier filtering. The base value is a deterministic
confidence-weighted median over intrinsic valuation snapshots only. The
optimistic intrinsic value is the highest valid intrinsic snapshot. DCF can
support the floor, but Analyst Consensus remains a separate market expectation
and does not widen the intrinsic range. RSI is shown separately and is never
mixed into intrinsic valuation math.

Default confidence weights are HIGH 1.00, MEDIUM 0.75, LOW 0.50, and UNKNOWN
0.25. Market position compares current price with the base value:
`<= -30%` deeply undervalued, `< -10%` undervalued, `<= +10%` near fair value,
`<= +20%` above fair value, and above that significantly overvalued. This
classification is descriptive and does not replace the existing recommendation.

In batch mode, each symbol gets its own optional RSI and range result. Missing
optional history, research, DCF, analyst data, or range inputs are tolerated per
symbol so one failure does not stop the batch.

## Recommendation V2

Recommendation V2 is enabled with `--recommendation-v2-config
config/recommendation_v2.yaml` and displayed with
`--show-recommendation-v2`. It is additive: the legacy BUY/HOLD/SELL decision
is still calculated and reported, and V2 compares itself with that legacy
recommendation.

V2 is valuation-first. It classifies current price versus base intrinsic value
as deeply undervalued, undervalued, slightly undervalued, near fair value,
moderately overvalued, significantly overvalued, or extremely overvalued.
Momentum is a timing modifier using current RSI and price versus the latest RSI
50 reference. Evidence quality comes from intrinsic model count, core
agreement, range status, and intrinsic snapshot confidence.

The decision matrix is deterministic. Undervalued names with strong evidence
can become `BUY` or `STRONG_BUY`; weak momentum can reduce urgency to
`ACCUMULATE`. Overvalued names become `REDUCE` or `SELL` depending on valuation,
evidence, and momentum. Conflicted core agreement caps bullish decisions at
`ACCUMULATE` and bearish decisions at `REDUCE`. Insufficient intrinsic evidence
returns `INSUFFICIENT_DATA`.

Analyst Consensus is context only. A low-confidence or outlier analyst target
is displayed in the V2 rationale but does not override intrinsic valuation. In
batch mode, each successful symbol gets its own Recommendation V2 result when
the optional config is supplied, while failed symbols remain isolated by the
existing batch failure handling.

## Multi-Stock Ranking RSI 50 Reference

Multi-stock ranking is enabled with `--ranking-config config/ranking_engine.yaml`
and displayed with `--show-ranking`. Ranking consumes completed per-symbol
analysis results, including Recommendation V2 and the existing RSI 50 Momentum
Reference; it does not download price history again.

The RSI 50 Reference Price is the price recorded at the latest RSI neutral-line
event: `CROSS_ABOVE`, `CROSS_BELOW`, or the `NEAREST_TO_50` fallback when no
qualifying crossing exists. Ranking reports it as a momentum neutral reference
and market sentiment context. It is not intrinsic value, fair value, guaranteed
support, actual investor average purchase price, or volume-weighted cost basis.

Ranking V1 classifies current price versus the RSI 50 reference into
`WELL_ABOVE_NEUTRAL_REFERENCE`, `ABOVE_NEUTRAL_REFERENCE`,
`NEAR_NEUTRAL_REFERENCE`, `BELOW_NEUTRAL_REFERENCE`, or
`WELL_BELOW_NEUTRAL_REFERENCE`. The default bands are +10%, above +3%, between
-3% and +3%, below -3%, and -10% or worse. These fields appear in the main
ranking table, the RSI 50 Momentum Reference table, `--show-ranking-details`,
CSV, and JSON output.

This sentiment position is display-only in V1. `affect_ranking_score` must
remain `false`, so it does not add another ranking component, alter intrinsic
valuation, change Recommendation V2, or double-count RSI beyond the existing
MomentumCondition score.

Example:

```bash
python -m src.main MU NVDA AMAT LITE COHR --profiles config/valuation_profiles.yaml --eps-selection config/eps_selection.yaml --industry-policies config/industry_policies.yaml --analyst-consensus config/analyst_consensus.yaml --agreement-config config/agreement_engine.yaml --momentum-config config/momentum_reference.yaml --range-config config/fair_value_range.yaml --recommendation-v2-config config/recommendation_v2.yaml --ranking-config config/ranking_engine.yaml --show-ranking --show-ranking-details --ranking-only
```

## Streamlit Web Dashboard

The Streamlit dashboard in `app.py` reuses the existing batch service layer
directly. It does not shell out to the CLI and does not duplicate valuation,
Recommendation V2, RSI, or ranking calculations.

Features:

- Batch ticker input with comma, space, or newline separation.
- Ranking table with display-only filters for eligibility, category,
  Recommendation V2, and RSI50 sentiment.
- Top summary metrics for eligible opportunities, insufficient symbols, and
  RSI50 sentiment distribution.
- Selected-symbol value comparison across current price, intrinsic range,
  analyst market expectation, and RSI50 reference price.
- Dedicated RSI 50 Momentum Reference section using the existing deterministic
  interpretation text.
- Stock detail tabs for overview, valuation snapshots, Recommendation V2,
  RSI50 momentum, model evidence, and warnings.
- Ranking CSV and JSON downloads using the existing ranking serialization.

Default dashboard configuration files:

- `config/valuation_profiles.yaml`
- `config/eps_selection.yaml`
- `config/industry_policies.yaml`
- `config/analyst_consensus.yaml`
- `config/agreement_engine.yaml`
- `config/momentum_reference.yaml`
- `config/fair_value_range.yaml`
- `config/recommendation_v2.yaml`
- `config/ranking_engine.yaml`

The default dashboard ticker list is `MU, NVDA, AMAT, LITE, COHR`. The app
stores the latest successful result in Streamlit session state and only runs a
new analysis after clicking Analyze.

Screenshots: add local screenshots here after running the dashboard.

Deployment:

```bash
pip install -r requirements.txt
streamlit run app.py
```
