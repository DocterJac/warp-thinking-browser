"""
test_shared_parity.py
─────────────────────
Verify that the shared functions across all three warp_thinking scripts
produce identical results. If someone patches the protobuf parser or a
shared helper in one script and forgets the others, these tests fail.

Run:  pytest tests/

Fixture:
    tests/fixtures/sample_task.bin  — a real task blob captured from the
    Warp database. Create it by running:
        python3 tests/capture_fixture.py
"""

import importlib.util
import os
import sys

import pytest

# ── Load the three scripts as modules ─────────────────────────────────────────

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _load(name, filename):
    path = os.path.join(ROOT, filename)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    # Prevent argparse from consuming pytest's args
    old_argv = sys.argv
    sys.argv = [filename]
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.argv = old_argv
    return mod

browse = _load("browse", "warp_thinking_browse.py")
watch  = _load("watch",  "warp_thinking_watch.py")
read   = _load("read",   "warp_thinking_read.py")

FIXTURE_PATH = os.path.join(ROOT, "tests", "fixtures", "sample_task.bin")
HAS_FIXTURE = os.path.exists(FIXTURE_PATH)

def _load_fixture():
    with open(FIXTURE_PATH, "rb") as f:
        return f.read()

# ── Parity: functions that must be identical across all three ─────────────────

class TestParseFieldsParity:
    """read_varint + parse_fields must behave identically in all scripts."""

    def test_empty_input(self):
        assert browse.parse_fields(b"") == watch.parse_fields(b"") == read.parse_fields(b"")

    def test_varint_parity(self):
        # A simple two-byte varint: 0x96 0x01 = 150
        data = bytes([0x96, 0x01])
        assert browse.read_varint(data, 0) == watch.read_varint(data, 0) == read.read_varint(data, 0)

    @pytest.mark.skipif(not HAS_FIXTURE, reason="No fixture blob — run tests/capture_fixture.py first")
    def test_real_blob(self):
        blob = _load_fixture()
        assert browse.parse_fields(blob) == watch.parse_fields(blob) == read.parse_fields(blob)


class TestDecodeStringParity:
    """decode_string must exist and behave identically in all scripts."""

    def test_valid_utf8(self):
        data = "hello world".encode("utf-8")
        assert browse.decode_string(data) == watch.decode_string(data) == read.decode_string(data) == "hello world"

    def test_invalid_bytes(self):
        data = bytes([0xff, 0xfe, 0x80])
        assert browse.decode_string(data) is None
        assert watch.decode_string(data) is None
        assert read.decode_string(data) is None


class TestTaskTitleParity:
    """task_title_from_blob must exist and behave identically in all scripts."""

    def test_empty_blob(self):
        assert browse.task_title_from_blob(b"") == watch.task_title_from_blob(b"") == read.task_title_from_blob(b"") == "(untitled)"

    @pytest.mark.skipif(not HAS_FIXTURE, reason="No fixture blob — run tests/capture_fixture.py first")
    def test_real_blob(self):
        blob = _load_fixture()
        assert browse.task_title_from_blob(blob) == watch.task_title_from_blob(blob) == read.task_title_from_blob(blob)


class TestDefaultDbPathParity:
    """default_db_path must return the same value in all scripts."""

    def test_parity(self):
        assert browse.default_db_path() == watch.default_db_path() == read.default_db_path()


class TestExtractQueryTextParity:
    """_extract_query_text must exist and behave identically in all scripts."""

    def test_none_input(self):
        assert browse._extract_query_text(None) == watch._extract_query_text(None) == read._extract_query_text(None) == "(no queries)"

    def test_plain_string(self):
        raw = "some plain text"
        assert browse._extract_query_text(raw) == watch._extract_query_text(raw) == read._extract_query_text(raw)

    def test_json_query(self):
        import json
        raw = json.dumps([{"Query": {"text": "hello world"}}])
        assert browse._extract_query_text(raw) == watch._extract_query_text(raw) == read._extract_query_text(raw) == "hello world"


# ── Parity: functions shared between browse + watch only ──────────────────────

class TestBrowseWatchParity:
    """blob_has_thinking and extract_thinking must match between browse and watch."""

    def test_empty_blob(self):
        assert browse.blob_has_thinking(b"") == watch.blob_has_thinking(b"") == False
        assert browse.extract_thinking(b"") == watch.extract_thinking(b"") == []

    @pytest.mark.skipif(not HAS_FIXTURE, reason="No fixture blob — run tests/capture_fixture.py first")
    def test_real_blob(self):
        blob = _load_fixture()
        assert browse.blob_has_thinking(blob) == watch.blob_has_thinking(blob)
        assert browse.extract_thinking(blob) == watch.extract_thinking(blob)
