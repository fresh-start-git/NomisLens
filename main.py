import ctypes
ctypes.windll.user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)  # PMv2
except (AttributeError, OSError):
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor V1 (Win 8.1+)
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()  # System-aware (legacy)

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from magnifier_bubble.app import main

raise SystemExit(main())
