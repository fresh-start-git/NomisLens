---
date: "2026-04-13 14:05"
promoted: false
---

Best practice: add a Windows named mutex (CreateMutexW) for single-instance enforcement. Second launch should detect the mutex, optionally bring the first window to front, and exit cleanly. Current behavior: second instance runs with no hotkey (graceful but confusing). Raised during Phase 6 CHECK 5 review.
