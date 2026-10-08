"""Extraction in a child process (BUG-024): a file that crashes or hangs it fails alone."""

import sys

import pytest

from app.services.extract import ExtractionError, OcrUnavailable
from app.services.extract_process import ChildProcessExtractor

from . import _extract_targets as targets


@pytest.fixture
def child():
    extractors = []

    def make(target, **kwargs):
        e = ChildProcessExtractor(target=target, **{"timeout": 30, "memory_mb": 0, **kwargs})
        extractors.append(e)
        return e

    yield make
    for e in extractors:
        e.close()


def test_text_comes_back_from_the_child(child):
    e = child(targets.crash_on_boom)
    assert e.extract("txt", "información".encode()).text == "información"


def test_a_crash_fails_that_file_and_the_next_one_works(child):
    e = child(targets.crash_on_boom)
    with pytest.raises(ExtractionError, match="crashed"):
        e.extract("txt", b"boom")
    assert e.extract("txt", b"still alive").text == "still alive"  # a fresh child took over


def test_a_hang_is_cut_off_by_the_timeout(child):
    e = child(targets.hang_on_boom, timeout=2)
    with pytest.raises(ExtractionError, match="more than 2 s"):
        e.extract("txt", b"boom")
    assert e.extract("txt", b"next file").text == "next file"


def test_errors_keep_their_kind(child):
    with pytest.raises(OcrUnavailable):
        child(targets.no_ocr).extract("pdf", b"%PDF")
    with pytest.raises(ExtractionError, match="not a valid Office file"):
        child(targets.crash_on_boom).extract("docx", b"not a zip")


@pytest.mark.skipif(sys.platform == "win32", reason="memory limits are Linux-only (the server)")
def test_memory_limit_fails_the_file_not_the_server(child):
    e = child(targets.allocate, memory_mb=256)
    with pytest.raises(ExtractionError, match="memory|crashed"):
        e.extract("txt", str(1024 * 1024 * 1024).encode())
