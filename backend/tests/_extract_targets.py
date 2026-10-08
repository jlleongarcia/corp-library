"""Extraction stand-ins run inside the child process by test_extract_process.py (must be importable there)."""

import os
import time

from app.services.extract import Extracted, OcrUnavailable, extract


def crash_on_boom(extension: str, data: bytes) -> Extracted:
    if data == b"boom":
        os._exit(3)  # like a segfault in pdfium: no exception, the process is just gone
    return extract(extension, data)


def hang_on_boom(extension: str, data: bytes) -> Extracted:
    if data == b"boom":
        time.sleep(120)
    return extract(extension, data)


def no_ocr(extension: str, data: bytes) -> Extracted:
    raise OcrUnavailable("scanned PDF, OCR not available")


def allocate(extension: str, data: bytes) -> Extracted:
    blob = bytearray(int(data))  # more than the memory limit
    return Extracted(str(len(blob)), "text")
