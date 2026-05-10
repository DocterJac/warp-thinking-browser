# Changelog

## 2026-05-10
- Renamed scripts to consistent `warp_thinking_<verb>.py` pattern:
  `browse`, `watch`, `read`
- Added section markers with `(shared)` tags to all three scripts
  so shared code is visually identified and sync-testable
- Extracted `decode_string()`, `task_title_from_blob()`, and
  `_extract_query_text()` as shared standalone functions in all scripts
- Replaced inline `.decode("utf-8")` calls with `decode_string()` in
  browse and watch for consistency with read
- Simplified `fetch_task()` and `list_recent_tasks()` in read to use
  the shared helpers instead of inline parsing
- Added parity test suite (`tests/test_shared_parity.py`) that verifies
  shared functions produce identical results across all three scripts
- Added `tests/capture_fixture.py` to snapshot a real task blob for tests
- Created this CHANGELOG
