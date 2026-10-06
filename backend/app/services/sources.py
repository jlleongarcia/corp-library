"""
File sources: where the scanner reads folders, files and permissions from.

- SmbSource reads a Windows share over SMB with the read-only service account.
- LocalSource reads a local directory; used in development and tests. It has no
  Windows ACLs, so unless an `sd_provider` is supplied every folder ends up with
  no ACL, which the app treats as "nobody but admins" (fail closed).
"""

import os
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import BinaryIO, Iterator, Optional, Protocol

FILE_ATTRIBUTE_DIRECTORY = 0x10
FILE_ATTRIBUTE_REPARSE_POINT = 0x400


@dataclass(frozen=True)
class DirEntry:
    name: str
    is_dir: bool
    size: int
    mtime: Optional[datetime]
    ctime: Optional[datetime]
    is_reparse_point: bool = False


class FileSource(Protocol):
    def list_dir(self, relpath: str) -> list[DirEntry]: ...

    def get_security_descriptor(self, relpath: str) -> Optional[bytes]: ...

    def open_read(self, relpath: str) -> "contextmanager[BinaryIO]": ...

    def display_path(self, relpath: str) -> str: ...


def is_unc(path: str) -> bool:
    return path.startswith("\\\\") or path.startswith("//")


def source_for(path: str) -> FileSource:
    return SmbSource(path) if is_unc(path) else LocalSource(path)


# ── Local ─────────────────────────────────────────────────────────────────────

class LocalSource:
    def __init__(self, root: str, sd_provider: Optional[Callable[[str], Optional[bytes]]] = None):
        self.root = os.path.abspath(root)
        self.sd_provider = sd_provider

    def _abs(self, relpath: str) -> str:
        return os.path.join(self.root, *relpath.split("/")) if relpath else self.root

    def list_dir(self, relpath: str) -> list[DirEntry]:
        out = []
        with os.scandir(self._abs(relpath)) as it:
            for e in it:
                st = e.stat(follow_symlinks=False)
                out.append(
                    DirEntry(
                        name=e.name,
                        is_dir=e.is_dir(follow_symlinks=False),
                        size=0 if e.is_dir(follow_symlinks=False) else st.st_size,
                        mtime=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
                        ctime=datetime.fromtimestamp(st.st_ctime, tz=timezone.utc),
                        is_reparse_point=e.is_symlink(),
                    )
                )
        return out

    def get_security_descriptor(self, relpath: str) -> Optional[bytes]:
        return self.sd_provider(relpath) if self.sd_provider else None

    @contextmanager
    def open_read(self, relpath: str) -> Iterator[BinaryIO]:
        with open(self._abs(relpath), "rb") as f:
            yield f

    def display_path(self, relpath: str) -> str:
        return self._abs(relpath)


# ── SMB ───────────────────────────────────────────────────────────────────────

_registered_servers: set[str] = set()


class SmbSource:
    def __init__(self, unc_root: str):
        self.root = unc_root.replace("/", "\\").rstrip("\\")
        self.server = self.root.lstrip("\\").split("\\")[0]

    def _ensure_session(self) -> None:
        if self.server in _registered_servers:
            return
        import smbclient

        from ..config import settings

        smbclient.register_session(
            self.server,
            username=settings.smb_username or None,
            password=settings.smb_password or None,
            auth_protocol=settings.smb_auth_protocol,
        )
        _registered_servers.add(self.server)

    def _abs(self, relpath: str) -> str:
        return self.root + ("\\" + relpath.replace("/", "\\") if relpath else "")

    def list_dir(self, relpath: str) -> list[DirEntry]:
        import smbclient

        self._ensure_session()
        out = []
        for e in smbclient.scandir(self._abs(relpath)):
            info = e.smb_info
            attrs = info.file_attributes
            is_dir = bool(attrs & FILE_ATTRIBUTE_DIRECTORY)
            out.append(
                DirEntry(
                    name=e.name,
                    is_dir=is_dir,
                    size=0 if is_dir else info.end_of_file,
                    mtime=_aware(info.last_write_time),
                    ctime=_aware(info.creation_time),
                    is_reparse_point=bool(attrs & FILE_ATTRIBUTE_REPARSE_POINT),
                )
            )
        return out

    def get_security_descriptor(self, relpath: str) -> Optional[bytes]:
        """Fetch owner + DACL with an SMB2 QUERY_INFO (InfoType SECURITY)."""
        from smbclient._io import SMBDirectoryIO, SMBFileTransaction
        from smbprotocol.file_info import InfoType
        from smbprotocol.open import (
            DirectoryAccessMask, SMB2QueryInfoRequest, SMB2QueryInfoResponse,
        )

        self._ensure_session()
        raw = SMBDirectoryIO(
            self._abs(relpath),
            mode="r",
            share_access="rwd",
            desired_access=DirectoryAccessMask.READ_CONTROL | DirectoryAccessMask.FILE_READ_ATTRIBUTES,
        )
        with SMBFileTransaction(raw) as tx:
            req = SMB2QueryInfoRequest()
            req["info_type"] = InfoType.SMB2_0_INFO_SECURITY
            req["output_buffer_length"] = 65535
            req["additional_information"] = 0x1 | 0x4  # OWNER | DACL
            req["file_id"] = tx.raw.fd.file_id

            def _receive(request):
                response = tx.raw.fd.connection.receive(request)
                resp = SMB2QueryInfoResponse()
                resp.unpack(response["data"].get_value())
                return resp["buffer"].get_value()

            tx += (req, _receive)
        return tx.results[0]

    @contextmanager
    def open_read(self, relpath: str) -> Iterator[BinaryIO]:
        import smbclient

        self._ensure_session()
        with smbclient.open_file(self._abs(relpath), mode="rb", share_access="rwd") as f:
            yield f

    def display_path(self, relpath: str) -> str:
        return self._abs(relpath)


def _aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
