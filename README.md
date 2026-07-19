# Fair Value Analyzer

Open-source stock valuation and momentum analysis platform built with Python
and Streamlit.

![Python 3.11](https://img.shields.io/badge/Python-3.11-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-Dashboard-ff4b4b)
![License: MIT](https://img.shields.io/badge/License-MIT-green)
![Status: Beta](https://img.shields.io/badge/Status-Beta-orange)

Fair Value Analyzer helps compare stocks through intrinsic valuation,
fair-value ranges, Recommendation V2, RSI50 momentum reference, SOXX market
timing, and multi-stock ranking. It keeps valuation models, analyst targets,
technical momentum, semiconductor-cycle timing, and ranking evidence visible as
separate signals instead of collapsing everything into one opaque score.

## Why this project?

Most stock screeners blend many valuation sources into a single number. Fair
Value Analyzer intentionally keeps different viewpoints separate:

- **Intrinsic Value**: model-based value estimates from PER and research inputs.
- **Market Expectation**: analyst target data from Yahoo Finance.
- **Technical Momentum**: RSI50 neutral-line reference and sentiment context.
- **Relative Ranking**: comparison of eligible stocks in the current batch.

These perspectives can disagree for valid reasons. The project shows the
disagreement instead of averaging it away.

## Features

- Intrinsic Valuation
- Fair Value Range
- Recommendation V2
- Agreement Engine
- RSI50 Momentum Reference
- SOXX Buy/Sell Timing Engine
- Multi-Stock Ranking
- Streamlit Dashboard
- CSV / JSON Export

| Area | Description |
| --- | --- |
| Automatic PER Valuation | Calculates fair value from EPS, target PER, and macro adjustment settings. |
| Research PER Valuation | Supports manually reviewed EPS and target PER assumptions by ticker. |
| DCF Reference Valuation | Displays configured DCF reference values as supporting valuation context. |
| Analyst Consensus Comparison | Compares Yahoo analyst target mean/high/low as market-expectation context. |
| Fair Value Range | Produces conservative, base, and optimistic intrinsic value references. |
| Recommendation Engine V2 | Generates deterministic valuation-aware recommendation output with rationale. |
| Agreement Engine | Evaluates consistency across valuation snapshots and highlights outliers. |
| RSI50 Momentum Reference | Reports the latest RSI 50 neutral-line reference as technical momentum context. |
| SOXX Buy/Sell Timing Engine | Tracks SOXX MA5 crossovers, drawdown, convergence, and semiconductor-cycle timing signals. |
| Multi-stock Ranking | Ranks analyzed symbols while preserving eligibility and insufficient-data states. |
| Streamlit Dashboard | Provides an interactive web dashboard for ranking, details, charts, and warnings. |
| CSV / JSON Export | Exports ranking results using stable CSV and JSON formats. |

## Screenshots

Screenshots can be added after local capture. The paths below are placeholders
for repository screenshots.

![Dashboard](docs/images/dashboard.png)

![Ranking](docs/images/ranking.png)

![Stock Detail](docs/images/detail.png)

![Valuation Comparison](docs/images/valuation.png)

![RSI50 Momentum](docs/images/rsi50.png)

## Project Architecture

The application keeps data access, configuration, analysis, reporting, and UI
responsibilities separate.

```text
+-----------------------------+
|        Yahoo Finance        |
+-------------+---------------+
              |
              v
+-----------------------------+
|      Valuation Models       |
+-------------+---------------+
              |
              v
+-----------------------------+
|       Agreement Engine      |
+-------------+---------------+
              |
              v
+-----------------------------+
|       Fair Value Range      |
+-------------+---------------+
              |
              v
+-----------------------------+
|      Recommendation V2      |
+-------------+---------------+
              |
              v
+-----------------------------+
|  RSI50 Momentum Reference   |
+-------------+---------------+
              |
              v
+-----------------------------+
|       Ranking Engine        |
+-------------+---------------+
              |
              v
+-----------------------------+
|     Streamlit Dashboard     |
+-----------------------------+
```

Repository layout:

| Path | Responsibility |
| --- | --- |
| `src/yahoo/` | Yahoo Finance adapters for fundamentals, Treasury yield, and price history. |
| `src/config/` | YAML configuration loaders and validation. |
| `src/analysis/` | Pure valuation, agreement, momentum, recommendation, and ranking logic. |
| `src/services/` | Application orchestration for single-stock and batch analysis. |
| `src/reports/` | Deterministic CLI text, CSV, and JSON formatting. |
| `src/web/` | Streamlit dashboard presentation and interaction helpers. |
| `tests/` | Unit, service, report, CLI, and web presentation tests. |

## Web Dashboard

The interactive UI is built with Streamlit and reuses the same service layer as
the command line interface.

Dashboard views include:

- SOXX Market Timing
- Top Eligible Opportunity
- Multi-stock Ranking Table
- Valuation Comparison
- Recommendation V2 details
- RSI50 Momentum Reference
- Model Evidence and Warnings
- Download Ranking CSV / JSON

## Installation

Requires Python 3.11 or newer.

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Linux

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Command Line Interface

Every dashboard analysis can also be reproduced from the CLI. This is useful
for repeatable research, automation, and exporting deterministic ranking
results.

Run a single stock with the default valuation configuration:

```bash
python -m src.main LITE
```

Run a single stock with research profiles, EPS selection, industry policy,
analyst consensus, agreement, RSI50 momentum, fair-value range, and
Recommendation V2:

```bash
python -m src.main MU \
  --profiles config/valuation_profiles.yaml \
  --eps-selection config/eps_selection.yaml \
  --industry-policies config/industry_policies.yaml \
  --analyst-consensus config/analyst_consensus.yaml \
  --agreement-config config/agreement_engine.yaml \
  --momentum-config config/momentum_reference.yaml \
  --range-config config/fair_value_range.yaml \
  --recommendation-v2-config config/recommendation_v2.yaml \
  --show-snapshots \
  --show-agreement \
  --show-momentum \
  --show-range \
  --show-recommendation-v2
```

Run a multi-stock ranking:

```bash
python -m src.main MU NVDA AMAT LITE COHR \
  --profiles config/valuation_profiles.yaml \
  --eps-selection config/eps_selection.yaml \
  --industry-policies config/industry_policies.yaml \
  --analyst-consensus config/analyst_consensus.yaml \
  --agreement-config config/agreement_engine.yaml \
  --momentum-config config/momentum_reference.yaml \
  --range-config config/fair_value_range.yaml \
  --recommendation-v2-config config/recommendation_v2.yaml \
  --ranking-config config/ranking_engine.yaml \
  --show-ranking
```

Export ranking output:

```bash
python -m src.main MU NVDA AMAT LITE COHR \
  --profiles config/valuation_profiles.yaml \
  --eps-selection config/eps_selection.yaml \
  --industry-policies config/industry_policies.yaml \
  --analyst-consensus config/analyst_consensus.yaml \
  --agreement-config config/agreement_engine.yaml \
  --momentum-config config/momentum_reference.yaml \
  --range-config config/fair_value_range.yaml \
  --recommendation-v2-config config/recommendation_v2.yaml \
  --ranking-config config/ranking_engine.yaml \
  --ranking-only \
  --ranking-format json
```

Inspect Yahoo EPS source data:

```bash
python -m src.main MU --inspect-eps
```

Run SOXX timing only:

```bash
python -m src.main \
  --soxx-timing \
  --soxx-timing-config config/soxx_timing.yaml \
  --soxx-timing-only
```

Append SOXX timing before ordinary ranking output:

```bash
python -m src.main MU NVDA AMAT \
  --soxx-timing \
  --ranking-config config/ranking_engine.yaml \
  --recommendation-v2-config config/recommendation_v2.yaml \
  --show-ranking
```

## Running Web Dashboard

Start the Streamlit app:

```bash
streamlit run app.py
```

Then open:

```text
http://localhost:8501
```

The dashboard supports comma, space, or newline separated ticker input. It
stores the latest successful analysis in Streamlit session state, so changing
filters, selected symbols, table sorting, or tabs does not rerun the analysis.

## Configuration

Configuration lives in `config/`. Each YAML file is validated before use.
Nearly every valuation policy can be adjusted through YAML without changing
source code.

This includes EPS selection, industry policy, analyst consensus weighting,
agreement thresholds, fair-value range construction, Recommendation V2
thresholds, RSI50 momentum settings, and ranking weights.

| File | Purpose |
| --- | --- |
| `config/valuation.yaml` | Core automatic valuation, macro adjustment, and buy/sell threshold settings. |
| `config/stocks.yaml` | Default batch symbol list. |
| `config/valuation_profiles.yaml` | Research PER assumptions, source notes, and DCF reference values. |
| `config/eps_selection.yaml` | EPS selection policy for fair-value EPS. |
| `config/industry_policies.yaml` | Industry-specific valuation style and target PER policy. |
| `config/analyst_consensus.yaml` | Analyst target weighting, dispersion, and confidence settings. |
| `config/agreement_engine.yaml` | Agreement thresholds and outlier settings. |
| `config/fair_value_range.yaml` | Fair-value range construction and confidence weights. |
| `config/momentum_reference.yaml` | RSI50 momentum reference lookback and calculation settings. |
| `config/soxx_timing.yaml` | SOXX buy/sell timing settings for MA crossovers, drawdown, convergence, and display. |
| `config/recommendation_v2.yaml` | Recommendation V2 thresholds and decision constraints. |
| `config/ranking_engine.yaml` | Multi-stock ranking weights, eligibility, and RSI50 display bands. |

## Interpretation

Fair Value Analyzer separates model concepts intentionally. The labels below
are important when reading either the CLI output or the dashboard.

### Intrinsic Value

Intrinsic value refers to model-based valuation output from sources such as
Automatic PER and Research PER. The Fair Value Range combines available
intrinsic signals into conservative, base, and optimistic references. These
values depend on assumptions and source data quality.

### Market Expectation

Analyst Consensus is treated as a market-expectation measure. It uses Yahoo
analyst target data when available, but it is not relabeled as intrinsic value
and does not automatically override intrinsic valuation output.

### Technical Momentum

The RSI50 reference is the price associated with the latest RSI 50 neutral-line
transition or configured fallback. It is a technical momentum and sentiment
reference, not intrinsic value, guaranteed support, or investor average cost.

### SOXX Market Timing

SOXX timing is a semiconductor-cycle technical reference. It uses completed
daily SOXX price history, MA5, MA10, MA15, MA20, MA50, rolling prior high, and
short moving-average convergence. A crossover is an event, not a persistent
position: MA5 must move from at-or-below to above a slower moving average for a
buy signal, or from at-or-above to below for a sell signal.

Signals are graded as BUY, STRONG_BUY, VERY_STRONG_BUY, SELL, STRONG_SELL,
VERY_STRONG_SELL, and SELL_CAUTION. SELL_CAUTION appears when SOXX is at least
10% below its rolling prior high. A deep-drawdown recovery condition is tracked
when SOXX is at least 30% below its prior high and MA5 crosses above MA15 while
MA5, MA15, and MA20 remain below MA50. Convergence tracks whether MA5, MA10,
MA15, and MA20 are tightly clustered before a sell setup. Rolling prior high
uses prior observations only, avoiding look-ahead bias.

SOXX timing is not intrinsic value and is not mixed into ranking scores,
Recommendation V2, analyst consensus, or fair-value calculations. It is a
separate timing reference with text labels and graded color keys for display.

### Recommendation V2

Recommendation V2 is a deterministic decision layer that considers valuation
condition, momentum condition, evidence quality, model agreement, and legacy
recommendation alignment. It is designed to be explainable, not predictive.

### Intrinsic Value vs. Analyst Target

Intrinsic value is produced from valuation assumptions and model rules.
Analyst targets represent market expectations from external analysts. The two
can diverge meaningfully, especially when analyst target ranges are wide or
when intrinsic models identify limited evidence.

## Current Status

Current Version: **v1.0.0-beta**

Completed:

- Intrinsic Valuation
- Recommendation V2
- Agreement Engine
- Fair Value Range
- RSI50 Momentum
- SOXX Buy/Sell Timing Engine
- Ranking Engine
- Streamlit Dashboard

In Progress:

- Portfolio Dashboard
- Historical Backtesting
- Sector Analysis
- Valuation History
- Watchlist

## Disclaimer

Fair Value Analyzer is an analytical reference tool, not investment advice. It
does not recommend buying or selling securities and does not guarantee future
performance. Results depend on assumptions, configuration, and source data
quality.

## Future Roadmap

| Feature | Status | Priority |
| --- | --- | --- |
| Intrinsic Valuation | Completed | High |
| Recommendation V2 | Completed | High |
| Agreement Engine | Completed | High |
| Fair Value Range | Completed | High |
| RSI50 Momentum Reference | Completed | Medium |
| SOXX Buy/Sell Timing Engine | Completed | Medium |
| Multi-stock Ranking | Completed | High |
| Streamlit Dashboard | Completed | High |
| Portfolio Dashboard | In Progress | High |
| Historical Backtesting | In Progress | Medium |
| Sector Comparison | Planned | Medium |
| Risk Dashboard | Planned | Medium |
| Valuation History | In Progress | Medium |
| Watchlist | In Progress | Medium |
| Email Alerts | Planned | Low |

## Contributing

Pull requests and issue reports are welcome. Contributions that preserve
deterministic behavior, clear separation of calculation and presentation logic,
and strong test coverage are especially helpful.

## License

MIT
