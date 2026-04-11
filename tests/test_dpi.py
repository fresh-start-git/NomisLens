"""Unit tests for magnifier_bubble.dpi — DPI helper module.

Most tests require Windows (DPI APIs only exist on win32). The
`test_module_constants_exist` test runs on any platform because it
only inspects module-level constants.
"""
from __future__ import annotations

import sys

import pytest

from magnifier_bubble import dpi

# Shortcut — matches conftest.py `win_only` marker
win_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")


def test_module_constants_exist():
    assert dpi.DPI_AWARENESS_CONTEXT_UNAWARE == -1
    assert dpi.DPI_AWARENESS_CONTEXT_SYSTEM_AWARE == -2
    assert dpi.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE == -3
    assert dpi.DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == -4
    assert dpi.DPI_AWARENESS_CONTEXT_UNAWARE_GDISCALED == -5


def test_module_importable_without_side_effects():
    # Re-importing must not raise; module must be pure (no DPI init at import time).
    import importlib
    import magnifier_bubble.dpi as d2
    importlib.reload(d2)
    # If the module set DPI awareness at import time, reload would raise
    # ERROR_ACCESS_DENIED on the second call. Reaching here proves it's pure.


@win_only
def test_dpi_report_has_required_keys():
    r = dpi.report()
    for k in (
        "logical_w",
        "logical_h",
        "physical_w",
        "physical_h",
        "dpi",
        "scale_pct",
        "context_is_pmv2",
    ):
        assert k in r, f"missing key: {k}"


@win_only
def test_dpi_positive_dimensions():
    r = dpi.report()
    assert r["logical_w"] > 0
    assert r["logical_h"] > 0
    assert r["physical_w"] > 0
    assert r["physical_h"] > 0
    assert r["dpi"] >= 96


@win_only
def test_scale_pct_matches_dpi():
    r = dpi.report()
    assert r["scale_pct"] == r["dpi"] * 100 // 96


@win_only
def test_context_is_pmv2_returns_bool():
    r = dpi.report()
    assert isinstance(r["context_is_pmv2"], bool)


@win_only
def test_is_pmv2_active_returns_bool():
    assert isinstance(dpi.is_pmv2_active(), bool)


@win_only
def test_debug_print_writes_expected_format(capsys):
    dpi.debug_print()
    out = capsys.readouterr().out
    assert "[dpi]" in out
    assert "pmv2=" in out
    assert "dpi=" in out
    assert "scale=" in out
    assert "logical=" in out
    assert "physical=" in out
