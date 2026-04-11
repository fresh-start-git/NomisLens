"""Shared pytest fixtures and platform markers for Ultimate Zoom tests.

Phase 1 adds the win32-only skip marker used by tests/test_dpi.py.
Later phases will add mocks for AppState, fake mss grabs, and HWND stubs.
"""
from __future__ import annotations

import sys

import pytest

# Platform skip marker: DPI APIs only exist on Windows.
# Usage in a test module:
#     pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
# or on a single test:
#     @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
win_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows-only")
