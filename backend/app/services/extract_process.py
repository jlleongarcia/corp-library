"""
Text extraction in a child process (BUG-024).

pdfium is native code: a malformed PDF can crash it, which would take the worker
down with it, or make it spin forever. Here the worker sends the file's bytes to
a long-lived child process and waits for the text. If the child dies, or takes
longer than EXTRACT_TIMEOUT_SECONDS, it is killed and replaced, and only that
file fails. On Linux the child also gets a memory limit (EXTRACT_MEMORY_MB), so
one decompression bomb can't use up the server's memory.

The child only ever sees bytes: reading the share stays in the worker.
"""

import logging
import multiprocessing
from typing import Callable, Optional, Protocol

from ..config import settings
from .extract import Extracted, ExtractionError, OcrUnavailable, extract

logger = logging.getLogger(__name__)


class Extractor(Protocol):
    def extract(self, extension: str, data: bytes) -> Extracted: ...

    def close(self) -> None: ...


class InProcessExtractor:
    """Extraction in the worker itself (EXTRACT_IN_CHILD=false, and most tests)."""

    def extract(self, extension: str, data: bytes) -> Extracted:
        return extract(extension, data)

    def close(self) -> None:
        pass


def _limit_memory(megabytes: int) -> None:
    try:
        import resource  # Unix only
    except ImportError:
        return
    limit = megabytes * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))


def _serve(conn, memory_mb: int, target: Callable[[str, bytes], Extracted]) -> None:
    """The child: extract whatever arrives on the pipe until it closes."""
    if memory_mb > 0:
        _limit_memory(memory_mb)
    while True:
        try:
            extension, data = conn.recv()
        except (EOFError, OSError):
            return
        try:
            reply = ("ok", target(extension, data))
        except OcrUnavailable as exc:
            reply = ("ocr_unavailable", str(exc))
        except ExtractionError as exc:
            reply = ("error", str(exc))
        except MemoryError:
            reply = ("error", f"needs more than {memory_mb} MB of memory to read")
        except Exception as exc:  # a library bug on a strange file
            reply = ("error", f"{type(exc).__name__}: {exc}")
        conn.send(reply)


class ChildProcessExtractor:
    def __init__(self, timeout: Optional[float] = None, memory_mb: Optional[int] = None,
                 target: Callable[[str, bytes], Extracted] = extract):
        self.timeout = settings.extract_timeout_seconds if timeout is None else timeout
        self.memory_mb = settings.extract_memory_mb if memory_mb is None else memory_mb
        self.target = target  # replaced by the tests with functions that crash or hang
        # "spawn" everywhere: the same behaviour on Windows (dev) and Linux, and no
        # copy of the worker's database connections in the child.
        self._ctx = multiprocessing.get_context("spawn")
        self._proc = None
        self._conn = None

    def _start(self) -> None:
        parent, child = self._ctx.Pipe()
        self._proc = self._ctx.Process(
            target=_serve, args=(child, self.memory_mb, self.target), name="corplib-extract", daemon=True
        )
        self._proc.start()
        child.close()
        self._conn = parent

    def _kill(self) -> None:
        if self._proc is not None:
            self._proc.kill()
            self._proc.join(10)
        if self._conn is not None:
            self._conn.close()
        self._proc = self._conn = None

    def extract(self, extension: str, data: bytes) -> Extracted:
        if self._proc is None or not self._proc.is_alive():
            self._kill()
            self._start()
        try:
            self._conn.send((extension, data))
            if not self._conn.poll(self.timeout):
                self._kill()
                raise ExtractionError(f"reading the file took more than {self.timeout:g} s")
            reply = self._conn.recv()
        except (EOFError, OSError):
            self._proc.join(5)
            code = self._proc.exitcode
            self._kill()
            logger.warning("Extractor process died (exit code %s); restarting it.", code)
            raise ExtractionError(f"the file crashed the text extractor (exit code {code})") from None
        kind, value = reply
        if kind == "ok":
            return value
        if kind == "ocr_unavailable":
            raise OcrUnavailable(value)
        raise ExtractionError(value)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()  # the child sees EOF and exits
        if self._proc is not None:
            self._proc.join(5)
            if self._proc.is_alive():
                self._proc.kill()
        self._proc = self._conn = None


def make_extractor() -> Extractor:
    return ChildProcessExtractor() if settings.extract_in_child else InProcessExtractor()
