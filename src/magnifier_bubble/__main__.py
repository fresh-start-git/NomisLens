# Alternate entry: python -m magnifier_bubble
# NOTE: This entry does NOT set DPI awareness itself. Prefer `python main.py`
# (the root shim) which sets PMv2 before any magnifier_bubble import.
# This file exists so `python -m magnifier_bubble` still works after a
# `pip install -e .` in Phase 8.
from magnifier_bubble.app import main

raise SystemExit(main())
