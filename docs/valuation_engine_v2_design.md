# Valuation Engine V2 Technical Design

## 1. Purpose

Valuation Engine V2 is the proposed next generation valuation framework for
Fair Value Analyzer. The current application already supports Yahoo company
fundamentals, Treasury yield macro adjustment, EPS growth calculation, EPS
growth caps, Target PE calculation, PEG adjustment, automatic PER fair value,
BUY/HOLD/SELL thresholds, symbol-specific research valuation profiles, manually
reviewed research EPS and Target PE, optional DCF reference values, single-stock
reports, and batch reports.

V2 should evolve the system from one PER-centered fair-value number into a
multi-model framework. The intended valuation components are:

1. Automatic PER valuation
2. Research PER valuation
3. DCF valuation
4. Analyst consensus valuation
5. Relative peer valuation
6. Model agreement and confidence
7. Final valuation range
8. Explainability
9. Industry-specific policy
10. Recommendation policy

This document defines the design before implementation. It does not change
production code, existing formulas, YAML configuration, CLI behavior, or
dependencies.

## 2. Current Repository Shape

The current project is already separated into useful responsibility boundaries:

- `src/yahoo/`: Yahoo Finance adapters for company fundamentals and Treasury
  yield history.
- `src/config/`: strict YAML loading and validation for valuation, stock lists,
  and valuation profiles.
- `src/analysis/`: pure calculation modules for EPS growth, Target PE, macro
  adjustment, fair value, valuation decisions, stock valuation orchestration,
  and research valuation.
- `src/services/`: application orchestration that loads configuration, downloads
  data, runs analysis, and captures batch failures.
- `src/reports/`: deterministic plain-text report formatting.
- `src/main.py`: CLI parsing, lazy runtime imports, exit-code policy, and report
  printing.
- `tests/`: unit, service, report, CLI, and configuration tests with mocked
  Yahoo access.

V2 should keep these boundaries. Downloaders should not contain valuation
formulas. Report formatters should not calculate values. Configuration loaders
should validate and produce immutable configuration objects. Analysis modules
should remain pure and unit-testable.

## 3. Design Principles

- No single fair-value number is objectively correct.
- Every valuation model must remain independently inspectable.
- Raw source data, assumptions, and calculated outputs must be separated.
- Manually reviewed inputs must never be silently overwritten.
- Yahoo fields must not be assumed to refer to a fiscal year unless the fiscal
  period is explicitly known.
- Cyclical and structural-growth companies must use different policies.
- Missing optional models must not automatically fail the whole analysis.
- Confidence must reflect both model agreement and data quality.
- Reports must show a valuation range, not only a point estimate.
- Recommendation logic must be deterministic and explainable.
- All formulas must be pure and unit-testable.
- Downloaders, analysis logic, configuration, orchestration, and reporting must
  remain separated.
- No model may recalculate values inside a report formatter.
- Every result must indicate source, period, status, and assumptions.
- Technical timing references must remain separate from intrinsic valuation
  formulas and ranking scores unless an explicit future design defines a bridge.

## SOXX Buy/Sell Timing Engine V1

SOXX is the semiconductor-cycle timing benchmark for this application. The
SOXX Buy/Sell Timing Engine is a technical timing reference only; it is not
intrinsic value, automatic order execution, bottom detection, or future-price
prediction.

The engine uses completed daily SOXX price history and calculates MA5, MA10,
MA15, MA20, MA50, a rolling prior high, drawdown, and short moving-average
convergence. The price field preference is Adjusted Close first, then Close,
while preserving the actual field used in the result.

A crossover is an event:

```text
Bullish cross:
previous_ma5 <= previous_maN
and current_ma5 > current_maN

Bearish cross:
previous_ma5 >= previous_maN
and current_ma5 < current_maN
```

Persistent relative position is not a new crossover. If MA5 remains above MA10
after a prior cross, the UI should display the position as MA5 ABOVE MA10 or NO
NEW CROSS, not as a new BUY signal.

Graded buy signals:

- BUY: MA5 crosses above MA10.
- STRONG_BUY: MA5 crosses above MA15.
- VERY_STRONG_BUY: MA5 crosses above MA20.

Graded sell signals:

- SELL: MA5 crosses below MA10.
- STRONG_SELL: MA5 crosses below MA15.
- VERY_STRONG_SELL: MA5 crosses below MA20.

SELL_CAUTION is an active risk condition when SOXX is at least 10% below its
rolling prior high. Event history records the first threshold breach, not every
day spent below the threshold.

The deep-drawdown recovery rule activates when SOXX is at least 30% below its
rolling prior high, MA5/MA15/MA20 remain below MA50, and MA5 crosses above
MA15. If MA5 also crosses above MA20, the primary signal becomes
VERY_STRONG_BUY.

The convergence sell setup activates when MA5, MA10, MA15, and MA20 are within
the configured spread threshold above MA50, followed by MA5 crossing below
MA15. If MA5 also crosses below MA20, the primary signal becomes
VERY_STRONG_SELL.

Rolling prior high must avoid look-ahead bias:

```text
prior_high(t) = max(close during prior lookback window, excluding t)
```

The Streamlit dashboard presents SOXX Market Timing before ordinary
Multi-Stock Ranking. The CLI supports:

```bash
python -m src.main --soxx-timing --soxx-timing-only
```

SOXX timing has a separate CSV/JSON serialization and must not be mixed into
intrinsic valuation, Recommendation V2, Agreement Engine, Fair Value Range, or
Multi-Stock Ranking scores.

## 4. Current Problem Examples

The current automatic model uses Yahoo Forward EPS, calculated Target PE, and
the Treasury macro multiplier. That can work for some names and fail badly for
others.

Example: MU automatic valuation:

```text
Yahoo Forward EPS       : 150.77
Automatic Target PE     : 50.00
Automatic Fair Value    : approximately 7100
```

Example: MU research scenario:

```text
Research FY2026 EPS     : 73.39
Research Target PE      : 10.00
Research Adjusted Value : approximately 691
DCF Reference           : 618.10
```

Example: LITE automatic valuation:

```text
Yahoo Forward EPS       : 18.30
Automatic Target PE     : 50.00
Automatic Fair Value    : approximately 862
```

Example: LITE research scenario:

```text
Research FY2027 EPS     : 18.30
Research Target PE      : 40.00
Research Adjusted Value : approximately 689
```

The automatic model behaves more reasonably for LITE than for MU. MU is
cyclical, Yahoo Forward EPS may refer to a different period, one-year EPS
growth may reflect a recovery rather than sustainable growth, PEG can be
distorted by cycle trough-to-peak earnings, a universal Target PE cap is too
broad, and the current model has no normalized earnings or industry policy.

The research value is not guaranteed to be correct. It is a manually reviewed
scenario with explicit assumptions. V2 should make that distinction visible.

## 5. Target Architecture

```text
Market Data
  - Yahoo company fundamentals
  - Treasury yield snapshot
  - analyst targets
  - future estimate-period metadata

Research Inputs
  - valuation profiles
  - reviewed EPS and Target PE
  - source notes and future source documents
  - manually supplied DCF references

Industry Policy
  - valuation style
  - model eligibility
  - model weights
  - warnings and data-quality penalties

        |
        v

Valuation Model Layer
  - Automatic PER Model
  - Research PER Model
  - DCF Model
  - Analyst Consensus Model
  - Relative Peer Model

        |
        v

Valuation Aggregation Layer
  - Data Quality Assessment
  - Model Agreement
  - Confidence Score
  - Fair Value Range
  - Final Recommendation

        |
        v

Reports / CLI
```

Proposed future modules should follow current repository conventions:

```text
src/analysis/models/__init__.py
src/analysis/models/automatic_per.py
src/analysis/models/research_per.py
src/analysis/models/dcf.py
src/analysis/models/analyst_consensus.py
src/analysis/models/relative_valuation.py

src/analysis/valuation_aggregation.py
src/analysis/confidence.py
src/analysis/data_quality.py
src/analysis/industry_policy.py
src/analysis/final_recommendation.py

src/config/industry_policies.py
src/config/peer_groups.py
src/config/model_weights.py

src/services/valuation_engine_v2.py
src/reports/valuation_v2_text_report.py
src/reports/valuation_v2_batch_report.py
```

These filenames are proposed, not mandatory. The important rule is preserving
the existing separation of pure analysis, configuration loading, orchestration,
and reporting.

## 6. Common Model Contract

All model outputs should use one immutable interface so aggregation,
confidence, and reports can treat model results uniformly.

```python
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


class ValuationModelType(str, Enum):
    AUTOMATIC_PER = "AUTOMATIC_PER"
    RESEARCH_PER = "RESEARCH_PER"
    DCF = "DCF"
    ANALYST_CONSENSUS = "ANALYST_CONSENSUS"
    RELATIVE_PEER = "RELATIVE_PEER"


class ValuationModelStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True)
class CalculationStep:
    name: str
    input_values: Mapping[str, object]
    formula: str | None
    result: float | None
    explanation: str


@dataclass(frozen=True)
class ValuationModelResult:
    model_type: ValuationModelType
    status: ValuationModelStatus
    fair_value: float | None
    low_value: float | None
    high_value: float | None
    currency: str
    source: str | None
    valuation_period: str | None
    confidence_hint: float | None
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    calculation_steps: tuple[CalculationStep, ...]
```

Mandatory fields:

- `model_type`
- `status`
- `currency`
- `assumptions`
- `warnings`
- `calculation_steps`

Value fields may be `None` when the model is unavailable, not applicable, or
invalid. A model must not encode missing values as `0.0`. Zero is a real
valuation output and must remain distinguishable from missing data.

Currency handling:

- Each model result carries one output currency.
- Aggregation may include only values with compatible currencies.
- Future peer and international models must either convert currencies before
  producing `ValuationModelResult` or return `UNAVAILABLE` with a warning.
- Reports should display the currency from the result object, not infer it from
  the ticker.

Assumptions and warnings are immutable tuples so downstream code can preserve
explainability. The report formatter reads stored results; it must never
recalculate model values.

## 7. Automatic PER Model

The existing automatic model is:

```text
Yahoo Forward EPS
* calculated Target PE
* Treasury macro multiplier
```

Current calculation stages:

1. Extract trailing EPS and forward EPS from Yahoo company fundamentals.
2. Calculate EPS growth and classify the EPS transition.
3. If growth is usable, cap effective EPS growth according to config.
4. Calculate growth-based PE from effective growth and target PEG.
5. Apply PEG, sector/industry, and current Forward PE adjustments.
6. Apply minimum and maximum Target PE caps.
7. Calculate base fair value from Forward EPS and recommended Target PE.
8. Apply the Treasury macro multiplier.
9. Compare current price to buy/sell thresholds.

Limitations:

- Yahoo `forwardEps` fiscal period is unknown.
- GAAP versus non-GAAP basis is ambiguous.
- Cyclicality can make near-term EPS unrepresentative.
- Target PE can saturate at the configured maximum.
- Preferred-sector adjustment is broad.
- PEG can be distorted by cyclical recovery earnings.
- There is no normalized earnings input.
- There is no historical multiple context.

V2 should preserve this model as one independent valuation signal. It should not
be the single source of truth.

Proposed automatic-model metadata:

- EPS source field, such as `forwardEps`.
- EPS period, if known.
- source timestamp.
- actual EPS growth.
- effective capped EPS growth.
- whether EPS growth was capped.
- PEG adjustment and PEG source.
- industry policy applied.
- Target PE before and after caps.
- Treasury macro multiplier.
- warning flags such as `UNKNOWN_EPS_PERIOD`, `CYCLICAL_PEAK_EPS_RISK`,
  `TARGET_PE_CAPPED`, `PEG_DISTORTION_RISK`, and `SECTOR_POLICY_BROAD`.

## 8. Research PER Model

The existing research profile model is:

```text
Reviewed EPS
* Reviewed Target PE
* Treasury macro multiplier
```

V2 must preserve:

- manually selected fiscal year.
- manually selected valuation style.
- manually selected Target PE.
- optional DCF reference.
- source note.
- PEG metadata.

The research Target PE is not automatically modified. The research result is a
scenario, not an oracle. Source date and analyst rationale should eventually be
recorded. Stale profiles must be detectable.

Future profile fields:

```text
as_of_date
source_documents
rationale
review_status
expires_after_days
analyst_name or author label
normalized_eps_method
```

Suggested review status enum:

```python
class ResearchReviewStatus(str, Enum):
    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    STALE = "STALE"
    RETIRED = "RETIRED"
```

## 9. DCF Model

V2 should eventually calculate DCF independently. The current profile
`dcf_fair_value` remains only a manually supplied reference until that engine
exists.

Required conceptual inputs:

```python
@dataclass(frozen=True)
class DCFInputs:
    starting_free_cash_flow: float
    explicit_forecast_years: int
    yearly_growth_rates: tuple[float, ...]
    terminal_growth_rate: float
    discount_rate: float
    net_cash_or_net_debt: float
    diluted_share_count: float
    currency: str
    source_period: str
```

Formula stages:

1. Forecast annual free cash flow.
2. Discount each annual cash flow.
3. Calculate terminal value.
4. Discount terminal value.
5. Add net cash or subtract net debt.
6. Divide by diluted shares.

Conceptual formulas:

```text
fcf_year_n = fcf_year_n_minus_1 * (1 + growth_rate_n)
present_value_fcf_n = fcf_year_n / (1 + discount_rate) ** n
terminal_value = final_year_fcf * (1 + terminal_growth_rate) / (discount_rate - terminal_growth_rate)
present_value_terminal = terminal_value / (1 + discount_rate) ** explicit_forecast_years
equity_value = sum(present_value_fcfs) + present_value_terminal + net_cash_or_net_debt
fair_value_per_share = equity_value / diluted_share_count
```

Validation:

- `discount_rate > terminal_growth_rate`.
- finite numeric values only.
- positive diluted share count.
- explicit handling of negative FCF.
- terminal value unavailable when assumptions are invalid.
- explicit forecast years must match the number of growth rates.

DCF sensitivity outputs:

- base case.
- bear case.
- bull case.
- discount-rate sensitivity.
- terminal-growth sensitivity.

DCF status examples:

- `COMPLETE`: all required assumptions valid.
- `PARTIAL`: explicit forecast works, but terminal value unavailable.
- `NOT_APPLICABLE`: negative or unstable FCF makes standard DCF unsuitable.
- `INVALID_INPUT`: discount rate is not above terminal growth.

## 10. Analyst Consensus Model

The current `CompanyFundamentals` already includes analyst target mean, high,
and low. V2 can use those as an independent model while recognizing that
analyst targets are not intrinsically correct.

Potential inputs:

- analyst target mean.
- analyst target median, if available later.
- analyst target low.
- analyst target high.
- number of analysts, if available later.
- target update timestamp, if available later.

Possible output:

```text
fair_value = analyst target median when available, otherwise analyst target mean
low_value = analyst target low
high_value = analyst target high
```

Data-quality considerations:

- analyst count.
- target range dispersion.
- stale estimates.
- mixed publication dates.
- outlier high and low targets.
- whether targets were published before material company news.

Proposed reliability score inputs:

```text
analyst_count_score
dispersion_score
freshness_score
```

The model may return `PARTIAL` when mean exists but high/low or analyst count is
missing.

## 11. Relative Peer Valuation

V2 should use configured peer groups, not automatic peer discovery in the
initial scope.

Example peer groups:

```text
Memory semiconductors:
  - Samsung Electronics
  - SK hynix
  - Micron

Optical communications:
  - Coherent
  - Lumentum
  - Corning
```

Potential inputs:

- Forward PE.
- EV / EBITDA.
- Price / Sales.
- EPS growth.
- gross margin.
- operating margin.
- FCF margin.
- revenue growth.

Method A: peer median multiple:

```text
subject_normalized_metric * peer_median_multiple
```

Method B: growth-adjusted peer multiple:

```text
adjusted_multiple = peer_median_multiple * growth_or_margin_adjustment_factor
fair_value = subject_normalized_metric * adjusted_multiple
```

Cross-company accounting periods and GAAP/non-GAAP values must be normalized
before comparison. The model should return `UNAVAILABLE` or `PARTIAL` if peer
data is not comparable.

Peer-set configuration requirements:

```text
peer_group_id
members
primary_metric
fallback_metric
minimum_valid_peer_count
outlier_policy
source_date
```

## 12. Industry Policy

Industry policy must separate company economics from sector labels. The string
`Technology` is insufficient to pick one valuation policy.

Minimum valuation styles:

- `CYCLICAL`
- `GROWTH`
- `QUALITY_GROWTH`

Possible future styles:

- `MATURE`
- `TURNAROUND`
- `FINANCIAL`
- `REIT`
- `COMMODITY`
- `EARLY_STAGE`

Initial conceptual policies:

`CYCLICAL`:

- PEG adjustment disabled by default.
- lower Target PE ranges.
- normalized earnings required.
- automatic Forward EPS receives a data-quality penalty.
- DCF based on peak FCF receives a warning.
- cycle position and mid-cycle margins should matter.

`GROWTH`:

- PEG adjustment allowed.
- forward EPS can be more relevant.
- higher PE range.
- growth durability required.
- terminal assumptions tightly controlled.

`QUALITY_GROWTH`:

- moderate PEG use.
- premium based on margin stability and diversification.
- lower tolerance for extreme Forward PE.
- broader valuation range.

Examples:

```text
MU   -> CYCLICAL
LITE -> GROWTH
GLW  -> QUALITY_GROWTH
```

## 13. Normalized Earnings

Normalized earnings should be a later component, not a generic formula forced
onto every company.

Possible methods:

1. multi-year average EPS.
2. cycle-midpoint EPS.
3. normalized operating margin multiplied by normalized revenue.
4. analyst multi-year EPS blend.
5. weighted fiscal-year EPS.
6. peak-EPS haircut.

Example formulas:

```text
normalized_eps = weighted_average(FY2026_EPS, FY2027_EPS, FY2028_EPS)
```

```text
normalized_eps = normalized_revenue * normalized_net_margin / diluted_shares
```

For memory companies, normalized earnings should explicitly consider DRAM and
NAND pricing cycles, HBM mix, capex, supply additions, contract duration,
normalized margins, and peak earnings risk. The design must not hard-code
unsupported normalized EPS values.

## 14. Data Quality Assessment

Data quality should be a separate score from 0 to 100.

Potential dimensions:

- source completeness.
- period clarity.
- source freshness.
- accounting-basis consistency.
- estimate dispersion.
- cyclicality risk.
- manual-review status.
- peer sample size.
- missing assumptions.

Severity levels:

```python
class DataQualityLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    VERY_LOW = "VERY_LOW"
```

Example penalties:

- Forward EPS fiscal period unknown.
- analyst target date unavailable.
- DCF uses peak FCF.
- peer count below minimum.
- manually entered profile older than configured threshold.
- GAAP and non-GAAP metrics mixed.
- negative or unavailable normalized EPS.

Proposed initial weighting, configurable and subject to validation:

```text
source completeness          20%
period clarity               20%
source freshness             15%
accounting-basis consistency 15%
estimate dispersion          10%
cyclicality risk             10%
manual-review status          5%
peer sample size              5%
```

These weights are starting assumptions, not permanent truth.

## 15. Model Agreement and Confidence

Confidence must combine two distinct concepts:

1. data quality.
2. model agreement.

Suggested process:

1. Gather all `COMPLETE` model results.
2. Exclude `NOT_APPLICABLE`, `UNAVAILABLE`, and `INVALID_INPUT` results.
3. Calculate a central estimate.
4. Measure dispersion.
5. Combine dispersion with data-quality scores.
6. Apply industry-policy penalties.
7. Assign confidence level.

Weighted median should be preferred over simple mean because it is more robust
when one model produces an extreme value. In the MU example, automatic PER near
7100 should not dominate research PER near 691 and DCF near 618.

Possible dispersion metrics:

- median absolute deviation.
- interquartile range.
- max/min spread.
- coefficient of variation.

Conceptual result:

```python
class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    VERY_LOW = "VERY_LOW"


@dataclass(frozen=True)
class ValuationConfidenceResult:
    score: float
    level: ConfidenceLevel
    model_agreement_score: float
    data_quality_score: float
    valid_model_count: int
    excluded_models: tuple[ValuationModelType, ...]
    reasons: tuple[str, ...]
```

Required behavior:

- One available model: confidence cannot exceed `LOW` unless explicitly
  configured otherwise.
- Two models disagree strongly: agreement score falls even if data quality is
  high.
- Extreme outlier: include it in explanation and possibly exclude from weighted
  range construction.
- Research and DCF agree but analyst target disagrees: preserve all results,
  lower agreement, and explain the disagreement.
- Data quality low despite agreement: final confidence remains capped.

## 16. Fair Value Range

V2 final output must be a range:

```python
@dataclass(frozen=True)
class FairValueRangeResult:
    bear_value: float | None
    base_value: float | None
    bull_value: float | None
    minimum_model_value: float | None
    maximum_model_value: float | None
    included_model_values: tuple[float, ...]
    excluded_outliers: tuple[ValuationModelType, ...]
    explanation: str
```

Possible derivation:

- bear: lower weighted percentile or conservative model blend.
- base: weighted median.
- bull: upper weighted percentile or optimistic model blend.

Do not mechanically use raw minimum and maximum as official bear and bull
values. Outliers may dominate.

Example:

```text
MU:
  automatic PER       7100
  research PER         691
  DCF                  618
  analyst mean        1489
```

The automatic value should likely be identified as an outlier rather than
making the final range span 618 to 7100 without qualification.

## 17. Recommendation Policy

V2 recommendation logic must be deterministic and explainable.

Possible enum:

```python
class FinalRecommendation(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    WATCH = "WATCH"
    HOLD = "HOLD"
    REDUCE = "REDUCE"
    SELL = "SELL"
    NOT_APPLICABLE = "NOT_APPLICABLE"
```

Inputs:

- current price.
- bear/base/bull valuation range.
- confidence level.
- data quality.
- downside to bear case.
- upside to base case.
- valuation style.
- configured buy discount.
- configured sell premium.

Conceptual rules:

- `STRONG_BUY` requires meaningful discount and at least `MEDIUM` confidence.
- `BUY` requires discount to base value and tolerable bear-case downside.
- `WATCH` applies when price is near buy threshold but confidence is low.
- `HOLD` applies when price is within fair-value range.
- `REDUCE` applies when price is above base value but below sell threshold.
- `SELL` applies when price is materially above bull value or sell threshold.
- `NOT_APPLICABLE` applies when too few valid models exist.

Percentages should be configurable defaults, not permanent hard-coded truth. The
result must include the exact rule that fired.

## 18. Explainability

Every model should expose:

- source inputs.
- formulas.
- intermediate values.
- assumptions.
- warnings.
- final value.

Aggregation should expose:

- included models.
- excluded models and reasons.
- model weights.
- outlier handling.
- central-value calculation.
- confidence calculation.
- recommendation rule.

Example explanation:

```text
Automatic PER value was excluded as an outlier because it was more than the
configured dispersion threshold above the weighted median of other valid models.
```

Recommendations must not be opaque or AI-generated. Conclusions must be
reproducible from stored result objects.

## 19. Configuration Design

Potential files:

```text
config/valuation.yaml
config/valuation_profiles.yaml
config/industry_policies.yaml
config/peer_groups.yaml
config/model_weights.yaml
```

Option A: one consolidated YAML.

Advantages:

- one file to load.
- simpler CLI.
- easier for small projects.

Disadvantages:

- large file with mixed responsibilities.
- harder ownership boundaries.
- increased risk of unrelated config churn.

Option B: responsibility-specific YAML files.

Advantages:

- matches current strict loader style.
- clearer ownership and tests.
- easier to load optional V2 config only when needed.
- reduces accidental edits to unrelated rules.

Disadvantages:

- more paths to manage.
- service orchestration must load several files once.

Recommendation: use multiple responsibility-specific YAML files. The current
repository already has separate valuation, stocks, and profile loaders.

Proposed examples, not implemented:

```yaml
# config/industry_policies.yaml
policies:
  MU:
    valuation_style: cyclical
    target_pe_range:
      minimum: 6.0
      maximum: 15.0
    automatic_forward_eps_quality_penalty: medium
    require_normalized_eps: true
    default_model_weights:
      automatic_per: 0.10
      research_per: 0.35
      dcf: 0.35
      analyst_consensus: 0.15
      relative_peer: 0.05

  LITE:
    valuation_style: growth
    target_pe_range:
      minimum: 20.0
      maximum: 50.0
    peg_adjustment_allowed: true
    require_growth_durability_warning: true

  GLW:
    valuation_style: quality_growth
    target_pe_range:
      minimum: 18.0
      maximum: 45.0
    margin_stability_premium_allowed: true
```

```yaml
# config/peer_groups.yaml
peer_groups:
  memory_semiconductors:
    members:
      - MU
      - 005930.KS
      - 000660.KS
    primary_metric: forward_pe
    fallback_metric: ev_ebitda
    minimum_valid_peer_count: 2
    outlier_policy: winsorize_10_90
    source_date: "2026-07-18"

  optical_communications:
    members:
      - LITE
      - COHR
      - GLW
    primary_metric: forward_pe
    fallback_metric: price_sales
    minimum_valid_peer_count: 2
    outlier_policy: exclude_outside_2_mad
    source_date: "2026-07-18"
```

```yaml
# config/model_weights.yaml
model_weights:
  defaults:
    automatic_per: 0.25
    research_per: 0.25
    dcf: 0.20
    analyst_consensus: 0.20
    relative_peer: 0.10

confidence_thresholds:
  high: 80
  medium: 60
  low: 40
```

## 20. Service and Orchestration Design

Future service flow:

```text
load shared configuration once
load valuation profiles once
load industry policies once
load peer groups once
download Treasury once per batch
for each symbol:
  download company once
  inspect EPS source and periods
  run independent valuation models
  collect model results
  score data quality
  calculate model agreement
  aggregate valuation range
  calculate confidence
  generate final recommendation
  build immutable service result
render reports
```

Requirements:

- no repeated Treasury download per symbol in batch mode.
- no repeated profile loading in batch mode.
- no report-time calculation.
- no live network calls in unit tests.
- failed optional models do not fail successful models.
- model failures are captured as structured statuses.

Potential result shape:

```python
@dataclass(frozen=True)
class ValuationEngineV2Result:
    symbol: str
    company: CompanyFundamentals
    treasury: TreasuryYieldSnapshot
    industry_policy: object | None
    model_results: tuple[ValuationModelResult, ...]
    data_quality: object
    confidence: ValuationConfidenceResult
    fair_value_range: FairValueRangeResult
    recommendation: object
    warnings: tuple[str, ...]
```

## 21. CLI Design

Future examples:

```bash
python -m src.main MU
python -m src.main MU --profiles config/valuation_profiles.yaml
python -m src.main MU --valuation-v2
python -m src.main MU --valuation-v2 --explain
python -m src.main --stocks config/stocks.yaml --valuation-v2
python -m src.main MU --inspect-eps
```

V2 should initially be opt-in. V1 and V2 should be comparable side by side.
V2 should become default only after validation against regression scenarios and
user review. This task does not implement CLI changes.

## 22. Report Design

Future single-stock report sections:

```text
MARKET DATA
EARNINGS AND ESTIMATE PERIODS
INDUSTRY POLICY
MODEL RESULTS
FAIR VALUE RANGE
CONFIDENCE
RECOMMENDATION
RISKS
CALCULATION TRACE
```

Compact model table example:

```text
Model                Fair Value   Status       Weight
Automatic PER        7100.64      OUTLIER      0%
Research PER          691.27      COMPLETE    35%
DCF                   618.10      COMPLETE    35%
Analyst Consensus    1489.57      COMPLETE    20%
Relative Peer         760.00      COMPLETE    10%
```

The sample weights are illustrative only.

Readable batch report columns:

```text
Symbol
Price
Bear
Base
Bull
Upside to Base
Confidence
Recommendation
Primary Warning
```

Batch reports should keep the main table compact and put detailed calculation
traces in single-stock or explain mode output.

## 23. Implementation Phases

| Phase | Scope | Likely Files | Tests | Acceptance Criteria | Non-goals | Migration Risks |
|---|---|---|---|---|---|---|
| 0 | EPS Source Inspector | `src/yahoo/company.py`, `src/analysis/eps_source.py`, service wrapper | unit, service, no-network | exposes raw EPS fields, periods when available, source timestamp, ambiguity warnings | no valuation formula change | Yahoo data may be incomplete |
| 1 | Common model contract | `src/analysis/models/contract.py` | dataclass and enum tests | all model results share one immutable interface | no new model math | adapting old results may be noisy |
| 2 | Analyst consensus model | `src/analysis/models/analyst_consensus.py` | unit and report tests | mean/high/low produce model result and quality warnings | no analyst web scraping | Yahoo fields may lack freshness |
| 3 | Data quality assessment | `src/analysis/data_quality.py` | penalty and level tests | deterministic 0-100 score with reasons | no final recommendation | weights may need calibration |
| 4 | Model agreement and confidence | `src/analysis/confidence.py` | outlier and dispersion tests | confidence separates data quality and agreement | no price action advice | edge cases with few models |
| 5 | Final valuation range | `src/analysis/valuation_aggregation.py` | weighted median/range tests | bear/base/bull values and outlier reasons | no DCF engine | users may compare to old point value |
| 6 | Recommendation engine | `src/analysis/final_recommendation.py` | rule-boundary tests | deterministic recommendation and fired rule | no permanent hard-coded thresholds | threshold tuning |
| 7 | Configured peer valuation | `src/config/peer_groups.py`, `src/analysis/models/relative_valuation.py` | config and model tests | peer group valuation works with configured peers | no peer auto-discovery | accounting comparability |
| 8 | Full DCF engine | `src/analysis/models/dcf.py` | formula and sensitivity tests | base/bear/bull DCF with validation | no source document parsing | assumption sensitivity |
| 9 | Normalized earnings engine | `src/analysis/normalized_earnings.py` | scenario tests | supports style-specific methods | no unsupported hard-coded EPS | industry complexity |
| 10 | V2 batch reporting and validation | `src/services/valuation_engine_v2.py`, reports, CLI | CLI, batch caching, golden scenarios | V2 opt-in report works for MU/LITE/GLW | no V1 removal | output churn |

Recommended immediate next implementation: EPS Source Inspector.

Purpose:

- determine what Yahoo Forward EPS represents where possible.
- expose raw source field.
- expose trailing EPS and forward EPS.
- expose current-year estimate when available.
- expose next-year estimate when available.
- expose estimate dates or periods when available.
- warn about GAAP/non-GAAP ambiguity.
- expose source timestamp.

### Phase 1A Implementation Note: EPS Selection

Phase 0 inspection found that, in the observed yfinance data, MU `forwardEps`
approximately matched the `+1y` earnings estimate and LITE `forwardEps` also
approximately matched the `+1y` earnings estimate. This indicates that the
automatic model may be using next-fiscal-year EPS without an explicit policy.

Phase 1A introduces explicit EPS selection for the automatic fair-value EPS
input. The initial policies are `LEGACY_FORWARD`, `CURRENT_YEAR`, `NEXT_YEAR`,
`WEIGHTED_CURRENT_NEXT`, and `MANUAL`.

Known transitional limitation: selected EPS drives fair value, while legacy
Yahoo `forwardEps` still drives EPS growth and Target PE. This inconsistency is
intentional for the initial phase and must be reported when selected EPS differs
materially from Yahoo `forwardEps`.

### Phase 1B Implementation Note: Industry Valuation Policy

Phase 1A EPS Selection Engine has been implemented as an explicit fair-value
EPS policy layer. Phase 1B introduces an explicit Industry Valuation Policy
Engine for automatic Target PE usage.

The initial policy configuration maps MU to `CYCLICAL`, LITE to `GROWTH`, and
GLW to `QUALITY_GROWTH`. MU uses current-year EPS from EPS selection and a
cyclical fixed Target PE, so the automatic PER model can become approximately
aligned with the manually reviewed research PER model. The original automatic
Target PE remains calculated and inspectable, while fair value uses the applied
policy Target PE only when `--industry-policies` is supplied.

### Phase 1C Implementation Note: Unified Valuation Snapshot

Phase 1C introduces an immutable `ValuationSnapshot` contract and
`ValuationSnapshotCollection` as a read-only projection over existing valuation
results.

```text
Model-specific result
  -> Snapshot adapter
  -> ValuationSnapshotCollection
  -> Future Agreement Engine
```

The initial active adapters cover Automatic PER, Research PER, and externally
supplied DCF Reference values. Snapshots do not replace current model results,
do not change calculations, and do not affect BUY/HOLD/SELL recommendations.
They prepare future agreement and fair-value range engines to consume common
model output without depending directly on every model-specific result type.

### Phase 2A Implementation Note: Analyst Consensus Valuation

Phase 2A introduces an independent Analyst Consensus Valuation Model using
Yahoo analyst target mean, high, and low values from already downloaded company
fundamentals. The model calculates target midpoint, range dispersion,
dispersion classification, model-local confidence, and weighted mean/midpoint
fair value.

Analyst consensus remains diagnostic in this phase. It does not affect final
recommendation, automatic PER fair value, research PER fair value, DCF
reference values, EPS selection, industry policy, or aggregate fair value.
Unlike the earlier model-specific result shapes, Analyst Consensus V2 produces
a `ValuationSnapshot` directly.

### Phase 2B Implementation Note: Agreement Engine V1

Phase 2B introduces Agreement Engine V1 as a pure snapshot aggregation layer. It
consumes only `ValuationSnapshotCollection`; it does not depend on Yahoo data,
research profile objects, `FairValueResult`, or analyst raw fields, and it does
not recalculate or change any existing valuation model output.

The engine treats value types differently. `INTRINSIC_VALUE` snapshots form the
core agreement set. `REFERENCE_VALUE` snapshots, such as the supplied DCF
reference, can be included in an extended intrinsic cluster when configured.
`MARKET_EXPECTATION` snapshots, such as Analyst Consensus, are compared against
the intrinsic cluster median but do not affect overall intrinsic agreement by
default.

Pairwise model differences use symmetric percentage difference:

```text
abs(A - B) / ((A + B) / 2) * 100
```

Default agreement thresholds are configured in `config/agreement_engine.yaml`:
strong at 10%, moderate at 20%, and weak at 35%. Outlier detection compares a
model value to the relevant median with a one-sided percentage difference. The
default outlier thresholds are 50% for possible outliers and 80% for outliers.

The result exposes core intrinsic agreement, extended agreement, overall
agreement, intrinsic cluster statistics, pairwise relationships, model outliers,
market-expectation analysis, deterministic rationale, and warnings. CLI
integration is opt-in with `--agreement-config`; report display is separately
controlled by `--show-agreement`, preserving existing output by default.

### Phase 2C Implementation Note: RSI 50 Momentum Reference

Phase 2C introduces an optional RSI 50 Momentum Reference. It is deliberately
not a valuation model and does not create a `ValuationSnapshot`. The result is
a separate technical context object that answers where the current market price
stands relative to the latest RSI(14) neutral-line event.

The implementation uses daily Yahoo price history with defaults of `1y` and
`1d`, requiring at least 30 valid closing observations. Adjusted close is
preferred when a reliable adjusted-close series is available; otherwise close
is used consistently and reported. Rows are sorted by date, invalid closes are
ignored, and duplicate dates are normalized before RSI calculation.

RSI uses Wilder smoothing:

```text
initial average gain/loss = simple mean over the first 14 deltas
average_gain[t] = ((average_gain[t - 1] * 13) + gain[t]) / 14
average_loss[t] = ((average_loss[t - 1] * 13) + loss[t]) / 14
RSI = 100 - 100 / (1 + average_gain / average_loss)
```

Flat periods return RSI 50, zero-loss positive periods return 100, and
zero-gain negative periods return 0. Crossings are detected around the neutral
50 line, with consecutive exact-50 rows de-duplicated by looking back to the
nearest earlier non-50 RSI. If no crossing exists and configured fallback is
enabled, the nearest RSI-to-50 point is reported as `FALLBACK` /
`NEAREST_TO_50`; it is not called a crossing.

CLI integration is opt-in with `--momentum-config
config/momentum_reference.yaml`; report display is separately controlled by
`--show-momentum`. The result is descriptive momentum context only and does not
affect Automatic PER, Research PER, DCF Reference, Analyst Consensus, Agreement
Engine, or recommendation logic.

### Phase 2D Implementation Note: Fair Value Range Engine V1

Phase 2D introduces Fair Value Range Engine V1 as a pure aggregation layer over
existing outputs. It consumes `ValuationSnapshotCollection`, the existing
Agreement Engine result, current market price, and optionally the RSI momentum
reference. It does not reconstruct or recalculate underlying model values.

The engine keeps four concepts separate:

- intrinsic valuation range.
- market expectation.
- current market price.
- RSI 50 momentum reference.

Core intrinsic values are usable `INTRINSIC_VALUE` snapshots with positive
selected values and usable statuses. Supporting references are usable
`REFERENCE_VALUE` snapshots. Market expectations, including Analyst Consensus,
are displayed separately and do not widen the intrinsic range. RSI is displayed
only as momentum context and is never included in conservative, base,
optimistic, range-width, weighted-median, or agreement calculations.

Definitions:

- conservative value: lowest valid intrinsic or configured supporting reference
  after outlier filtering.
- base value: deterministic confidence-weighted median over intrinsic values
  only.
- optimistic intrinsic value: highest valid intrinsic value.
- intrinsic floor: lowest included intrinsic/supporting reference value.
- intrinsic ceiling: highest included intrinsic value.
- range width: ceiling minus floor; width percentage is width divided by base.

Default confidence weights are HIGH 1.00, MEDIUM 0.75, LOW 0.50, and UNKNOWN
0.25. Reference values additionally receive the configured reference multiplier
when used as support. Market position compares current price with base value
using the simplified boundaries: `<= -30%` deeply undervalued, `< -10%`
undervalued, `<= +10%` near fair value, `<= +20%` above fair value, and `> +20%`
significantly overvalued.

CLI integration is opt-in with `--range-config config/fair_value_range.yaml`;
report display is separately controlled by `--show-range`. Batch mode calculates
each symbol independently, tolerates missing optional history/research/DCF or
analyst values, and preserves existing per-symbol failure behavior. Existing
BUY/HOLD/SELL recommendation and buy/sell thresholds remain unchanged.

### Phase 2E Implementation Note: Recommendation Engine V2

Phase 2E introduces Recommendation Engine V2 as an additive deterministic
recommendation layer. It consumes existing per-symbol results:
`ValuationSnapshotCollection`, `AgreementResult`, `RsiMomentumReference`,
`FairValueRangeResult`, and the legacy recommendation. It does not redownload
market data, recalculate snapshots, rebuild agreement, recalculate RSI,
recalculate fair-value range, or reclassify analyst outliers.

The core principle is valuation first. V2 begins with current price versus base
intrinsic value and classifies that spread as deeply undervalued, undervalued,
slightly undervalued, near fair value, moderately overvalued, significantly
overvalued, extremely overvalued, or unavailable. Momentum uses current RSI and
price versus the RSI 50 reference only as a timing and urgency modifier. A
stock that is meaningfully overvalued cannot become attractive solely because
momentum is positive.

Evidence quality is derived from intrinsic model count, core intrinsic
agreement, fair-value range status, and intrinsic snapshot confidence. HIGH
evidence requires at least two intrinsic models, STRONG core agreement, at
least one HIGH-confidence intrinsic model, and a COMPLETE range. MEDIUM
evidence allows STRONG or MODERATE agreement with a COMPLETE or PARTIAL range.
LOW evidence covers usable but weaker support. INSUFFICIENT evidence blocks the
V2 recommendation.

The decision matrix is deterministic:

- deeply undervalued values can be `STRONG_BUY`, `BUY`, or `ACCUMULATE`
  depending on evidence and momentum.
- undervalued values can be `BUY`, `ACCUMULATE`, or `HOLD`.
- slightly undervalued values require HIGH evidence and positive momentum for
  `ACCUMULATE`; otherwise they are `HOLD`.
- near fair value is generally `HOLD`, with strong positive momentum allowing
  `ACCUMULATE` and strong negative momentum producing `REDUCE`.
- moderately overvalued values are `REDUCE` unless momentum is strongly
  positive.
- significantly and extremely overvalued values become `REDUCE` or `SELL`
  depending on evidence and momentum.

Conflicted core agreement caps bullish conclusions at `ACCUMULATE` and bearish
conclusions at `REDUCE`. Analyst Consensus remains contextual market
expectation only; low-confidence or outlier analyst targets are mentioned in
rationale but do not override the intrinsic conclusion. V2 also compares its
decision with the legacy recommendation and reports whether the two are
aligned, V2 is more bullish, V2 is more bearish, or the comparison is not
available.

CLI integration is opt-in with `--recommendation-v2-config
config/recommendation_v2.yaml`; report display is separately controlled by
`--show-recommendation-v2`. Batch mode attaches an independent V2 result to
each successful symbol when configured. Existing legacy BUY/HOLD/SELL logic,
valuation formulas, buy/sell thresholds, snapshots, agreement, momentum, and
fair-value range outputs remain unchanged.

### Phase 2F Implementation Note: Multi-Stock Ranking RSI 50 Reference Visibility

Multi-Stock Ranking V1 consumes completed per-symbol analysis results and does
not recalculate valuation, agreement, RSI, fair-value range, or Recommendation
V2. The ranking output now exposes the existing RSI 50 Momentum Reference as
market sentiment context.

The RSI 50 Reference Price is the stock price recorded at the latest neutral
RSI event: `CROSS_ABOVE`, `CROSS_BELOW`, or `NEAREST_TO_50` fallback when no
qualifying crossing is available. Reports call it a momentum neutral reference,
neutral-line transition price, technical reference level, or market sentiment
context. It must not be described as intrinsic value, fair value, guaranteed
support, actual investor average purchase price, or volume-weighted cost basis.

Ranking V1 classifies current price versus the RSI 50 reference using configured
display bands:

- `WELL_ABOVE_NEUTRAL_REFERENCE`: at or above +10%.
- `ABOVE_NEUTRAL_REFERENCE`: above +3% and below +10%.
- `NEAR_NEUTRAL_REFERENCE`: from -3% through +3%.
- `BELOW_NEUTRAL_REFERENCE`: above -10% and below -3%.
- `WELL_BELOW_NEUTRAL_REFERENCE`: at or below -10%.
- `UNAVAILABLE`: no finite current-versus-reference percentage.

The ranking entry exposes current RSI, reference date, reference price,
reference RSI, cross direction, current-versus-reference amount and percentage,
reference status, price field, trading days since reference, and sentiment
position. Text reports show these fields in the main ranking table, a focused
RSI 50 Momentum Reference table, and ranking details. CSV output includes stable
flat columns for those values. JSON output nests them under
`momentum_reference`.

This field is display-only in V1. `momentum_reference_display.affect_ranking_score`
must remain `false`; the sentiment position does not change ranking component
weights, total score, normalized score, category, eligibility, intrinsic value,
or Recommendation V2. RSI information is already reflected once through the
existing MomentumCondition ranking component.

## 24. Test Strategy

Required categories:

- unit tests for every model.
- configuration validation tests.
- orchestration tests.
- outlier tests.
- confidence tests.
- stable-string report tests.
- CLI tests.
- batch caching tests.
- no-network tests.
- V1 regression tests.
- golden-scenario tests for MU, LITE, and GLW.

Deterministic scenarios:

1. models closely agree.
2. one extreme high outlier.
3. one extreme low outlier.
4. only one valid model.
5. low data quality.
6. cyclical company with peak EPS.
7. growth company with strong agreement.
8. missing DCF.
9. missing research profile.
10. stale research profile.

No V2 unit test should require live prices or live Yahoo responses. Yahoo
downloaders should remain mocked in service and CLI tests.

## 25. Migration and Backward Compatibility

V1 behavior should remain intact during migration:

- V1 output remains available initially.
- existing dataclasses are not removed abruptly.
- V2 uses wrapper result objects where appropriate.
- existing CLI remains functional.
- V2 configuration is optional during migration.
- missing profile is not fatal.
- DCF absence is not fatal.
- analyst-target absence is not fatal.
- batch mode continues processing other symbols after one optional model fails.

Deprecation of V1 should be considered only after V2 has stable tests,
production validation, and user approval.

## 26. Risks and Open Questions

- What exactly does Yahoo `forwardEps` represent for each ticker?
- Can fiscal-year estimate periods be reliably obtained?
- How should GAAP and non-GAAP EPS be reconciled?
- Should macro adjustment apply equally to PER, DCF, analyst, and peer models?
- Should analyst targets be macro-adjusted at all?
- How should current-year and next-year EPS be blended?
- How should currency conversion work for international peers?
- How should share dilution be modeled?
- How should cyclicality be quantified?
- How should model weights be selected?
- Should research profiles expire automatically?
- How should outlier thresholds differ by valuation style?
- How should DCF handle negative or peak FCF?
- How should confidence be calibrated against historical outcomes?
- How should stale analyst consensus data be detected if Yahoo lacks dates?
- Should manually supplied DCF references be weighted, displayed only, or used
  as a separate model before full DCF exists?

## 27. Architecture Decision Record

### Decision 1: Multi-model Design Instead of One Universal Formula

Decision: V2 will combine independent valuation models rather than rely on one
PER formula.

Reason: MU shows that one automatic PER value can become an extreme outlier.

Consequences: More result objects, aggregation logic, and explanation are
required.

Alternatives considered: Keep the automatic model and tune caps. This is simpler
but still cannot represent DCF, analyst, peer, and research scenarios.

### Decision 2: Weighted Median Preferred Over Simple Mean

Decision: Use weighted median as the preferred central estimate.

Reason: Weighted median is robust when one model produces an extreme value.

Consequences: Aggregation must carry model weights and included/excluded model
sets.

Alternatives considered: Simple mean. It is easy to explain but too sensitive to
outliers.

### Decision 3: Data Quality Separated From Model Agreement

Decision: Confidence will keep data quality and model agreement as separate
subscores.

Reason: Models can agree on poor data, or disagree despite good data.

Consequences: Reports need to show both concepts.

Alternatives considered: One confidence score only. This hides why confidence is
high or low.

### Decision 4: Industry Policy Separated From Sector Labels

Decision: V2 will use explicit industry policy instead of deriving policy from
sector names alone.

Reason: `Technology` contains cyclical memory, optical components, software, and
hardware businesses with different economics.

Consequences: More configuration is required.

Alternatives considered: Continue using preferred sector strings. This is too
broad and caused policy ambiguity.

### Decision 5: V2 Initially Opt-in

Decision: V2 should start behind an opt-in CLI flag such as `--valuation-v2`.

Reason: V1 is already tested and useful. V2 needs validation before becoming
default.

Consequences: Services and reports may coexist for a while.

Alternatives considered: Replace V1 immediately. This creates unnecessary
migration risk.

### Decision 6: Research Inputs Preserved as Manually Reviewed Scenarios

Decision: Research profiles remain manually reviewed scenarios.

Reason: Manual assumptions should be traceable and not silently overwritten.

Consequences: Staleness, author, rationale, and source metadata become
important.

Alternatives considered: Automatically update research EPS from Yahoo. That
would erase the purpose of reviewed inputs.

### Decision 7: DCF References Preserved Until Full DCF Implementation

Decision: Existing profile DCF values remain references until a real DCF model
is implemented.

Reason: A supplied DCF number is not the same as a reproducible DCF engine.

Consequences: Reports should label manual DCF references clearly.

Alternatives considered: Treat profile DCF as a complete DCF model. That would
overstate traceability.

### Decision 8: Explainability Stored in Result Objects

Decision: Calculation steps, assumptions, and warnings live in immutable result
objects.

Reason: Reports should display results, not recalculate them.

Consequences: Model result objects are larger but auditable.

Alternatives considered: Build explanations in formatters. This risks duplicated
logic and hidden recalculation.

### Decision 9: EPS Source Inspection Is the Next Implementation Phase

Decision: The smallest next implementation should be EPS Source Inspector.

Reason: The largest current uncertainty is what Yahoo Forward EPS represents for
each ticker and fiscal period.

Consequences: V2 can improve data quality before changing valuation math.

Alternatives considered: Implement DCF first. DCF still needs reliable periods,
shares, cash flow, and assumptions, so it is a larger step.

## 28. Explicit Non-goals for This Design

- No production code implementation.
- No formula changes to V1 automatic valuation.
- No YAML configuration modifications.
- No CLI changes.
- No new dependencies.
- No live network requirement in tests.
- No full DCF engine in the current task.
- No automatic peer discovery in initial V2.
- No opaque AI-generated recommendation logic.
