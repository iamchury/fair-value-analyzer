from types import SimpleNamespace

import pytest

from src.web import dashboard
from src.yahoo.treasury import TreasuryDataStatus
from tests.test_web_presentation import entry, result


class FakeProgress:
    def __init__(self) -> None:
        self.values = []

    def progress(self, value, text=None):
        self.values.append((value, text))

    def empty(self):
        self.values.append(("empty", None))


class FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeStreamlit:
    def __init__(self) -> None:
        self.session_state = {}
        self.errors = []
        self.exceptions = []
        self.metrics = []
        self.warnings = []
        self.infos = []
        self.selected_symbol = None
        self.selected_filters = {}

    def progress(self, value, text=None):
        progress = FakeProgress()
        progress.progress(value, text)
        return progress

    def error(self, value):
        self.errors.append(value)

    def exception(self, value):
        self.exceptions.append(value)

    def expander(self, _label):
        return FakeContext()

    def columns(self, count):
        return [self for _ in range(count)]

    def metric(self, *args, **_kwargs):
        self.metrics.append(args)
        return None

    def subheader(self, *_args, **_kwargs):
        return None

    def dataframe(self, *_args, **_kwargs):
        return None

    def download_button(self, *_args, **_kwargs):
        return None

    def bar_chart(self, *_args, **_kwargs):
        return None

    def table(self, *_args, **_kwargs):
        return None

    def warning(self, *args, **_kwargs):
        self.warnings.append(args)
        return None

    def success(self, *_args, **_kwargs):
        return None

    def info(self, *args, **_kwargs):
        self.infos.append(args)
        return None

    def caption(self, *_args, **_kwargs):
        return None

    def write(self, *_args, **_kwargs):
        return None

    def selectbox(self, label, options, index=0):
        if label == "Selected Symbol" and self.selected_symbol in options:
            return self.selected_symbol
        return self.selected_filters.get(label, options[index])

    def tabs(self, labels):
        return [FakeContext() for _ in labels]


def test_dashboard_analysis_function_is_not_cache_data_decorated() -> None:
    function = dashboard.analyze_symbols_for_dashboard

    assert getattr(function, "__wrapped__", None) is None
    assert not hasattr(function, "clear")


def test_run_analysis_stores_batch_result_in_session_state(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeStreamlit()
    batch = result([entry("MU", 1, 70)])

    monkeypatch.setattr(dashboard, "analyze_symbols_for_dashboard", lambda symbols: batch)

    dashboard._run_analysis(fake, "mu")

    assert fake.session_state["analysis_result"] is batch
    assert fake.session_state["analysis_symbols"] == ("MU",)
    assert fake.session_state["analysis_error"] is None
    assert "analysis_generated_at" in fake.session_state


def test_analyze_invokes_service_once_and_second_click_invokes_again(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeStreamlit()
    calls = []

    def analyze(symbols):
        calls.append(symbols)
        return result([entry("MU", 1, 70)])

    monkeypatch.setattr(dashboard, "analyze_symbols_for_dashboard", analyze)

    dashboard._run_analysis(fake, "MU")
    dashboard._run_analysis(fake, "MU")

    assert calls == [("MU",), ("MU",)]


def test_result_remains_available_across_render_only_ui_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeStreamlit()
    batch = result([entry("LITE", 1, 70), entry("MU", 2, 50)])
    fake.session_state["analysis_result"] = batch
    calls = []
    monkeypatch.setattr(dashboard, "analyze_symbols_for_dashboard", lambda symbols: calls.append(symbols))

    fake.selected_symbol = "MU"
    fake.selected_filters = {"Eligibility": "Eligible"}
    dashboard._render_dashboard(fake, fake.session_state["analysis_result"])

    fake.selected_symbol = "LITE"
    fake.selected_filters = {"Eligibility": "All", "Category": "ATTRACTIVE"}
    dashboard._render_dashboard(fake, fake.session_state["analysis_result"])

    assert fake.session_state["analysis_result"] is batch
    assert calls == []


def test_analysis_failure_sets_error_and_preserves_previous_result(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeStreamlit()
    previous = result([entry("MU", 1, 70)])
    fake.session_state["analysis_result"] = previous

    def fail(_symbols):
        raise RuntimeError("service exploded")

    monkeypatch.setattr(dashboard, "analyze_symbols_for_dashboard", fail)

    dashboard._run_analysis(fake, "MU")

    assert fake.session_state["analysis_result"] is previous
    assert fake.session_state["analysis_error"] == "service exploded"
    assert fake.errors


def test_dashboard_config_cache_resource_returns_config() -> None:
    config = dashboard.get_dashboard_config()

    assert config.ranking_config_path == "config/ranking_engine.yaml"
    assert config.recommendation_v2_config_path == "config/recommendation_v2.yaml"


def test_macro_status_propagates_to_dashboard() -> None:
    fake = FakeStreamlit()
    batch = result([entry("MU", 1, 70)])
    batch.treasury_status = TreasuryDataStatus.CONFIG_FALLBACK
    batch.treasury_yield_percent = 4.3
    batch.treasury_source_name = "Configured Fallback"
    batch.treasury_source_date = "2026-07-19"
    batch.treasury_trend = "NEUTRAL"
    batch.treasury_warning = (
        "Treasury yield download failed. Using configured fallback yield of 4.30%."
    )
    batch.treasury_used_fallback = True

    dashboard._macro_status(fake, batch)

    assert ("US 10Y Yield", "4.30%") in fake.metrics
    assert ("Source", "Configured Fallback") in fake.metrics
    assert ("Data Status", "Config Fallback") in fake.metrics
    assert ("Fallback Used", "Yes") in fake.metrics
    assert len(fake.warnings) == 1


def test_macro_status_displays_live_alternative_source_as_info() -> None:
    fake = FakeStreamlit()
    batch = result([entry("MU", 1, 70)])
    batch.treasury_status = TreasuryDataStatus.LIVE
    batch.treasury_yield_percent = 4.57
    batch.treasury_source_name = "FRED DGS10"
    batch.treasury_source_date = "2026-07-17"
    batch.treasury_trend = "RISING"
    batch.treasury_message = "Yahoo ^TNX was unavailable. Treasury data was loaded from FRED DGS10."
    batch.treasury_used_fallback = False

    dashboard._macro_status(fake, batch)

    assert ("Source", "FRED DGS10") in fake.metrics
    assert ("Fallback Used", "No") in fake.metrics
    assert len(fake.warnings) == 0
    assert len(fake.infos) == 1


def test_cli_entry_point_module_still_exposes_main() -> None:
    from src import main

    assert callable(main.main)
