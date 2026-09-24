import os
import stat
import sys
import time
import ctypes
from ctypes import wintypes
from typing import List, Tuple, Optional, Callable, Set
from duopty.models import FileInfo, DuplicateGroup


class DeleteResult:
    """Holds detailed results of a deletion run while remaining tuple-unpackable."""

    def __init__(
        self,
        deleted_count: int,
        errors: List[str],
        deleted_paths: Optional[Set[str]] = None,
        freed_bytes: int = 0,
        cancelled: bool = False
    ):
        self.deleted_count = deleted_count
        self.errors = errors
        self.deleted_paths = deleted_paths if deleted_paths is not None else set()
        self.freed_bytes = freed_bytes
        self.cancelled = cancelled

    def __iter__(self):
        # Enables backward-compatible tuple unpacking: deleted_count, errors = result
        return iter((self.deleted_count, self.errors))

    def __repr__(self) -> str:
        return (
            f"DeleteResult(deleted_count={self.deleted_count}, errors={len(self.errors)}, "
            f"deleted_paths={len(self.deleted_paths)}, freed_bytes={self.freed_bytes}, cancelled={self.cancelled})"
        )


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.WORD),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


FO_DELETE = 0x0003
FOF_ALLOWUNDO = 0x0040        # Moves file to Windows Recycle Bin
FOF_NOCONFIRMATION = 0x0010   # Suppress system prompt (GUI already confirms)
FOF_SILENT = 0x0004           # Don't show progress dialog
FOF_NOERRORUI = 0x0400        # Suppress system error UI


class FileDeleter:
    """Handles safe deletion of duplicate files to the Recycle Bin or permanent deletion."""

    @staticmethod
    def send_to_recycle_bin(filepath: str) -> bool:
        """Sends a file to the Windows Recycle Bin using native Shell API."""
        abs_path = os.path.abspath(filepath)
        if not os.path.exists(abs_path):
            return False

        # Attempt send2trash if available in environment
        try:
            import send2trash
            send2trash.send2trash(abs_path)
            return True
        except ImportError:
            pass
        except Exception:
            pass

        # Windows ctypes Shell API
        try:
            # Clear read-only flag if present so Shell API proceeds cleanly
            try:
                os.chmod(abs_path, stat.S_IWRITE)
            except Exception:
                pass

            # SHFileOperation requires double null termination
            buffer = abs_path + "\0\0"
            op = SHFILEOPSTRUCTW()
            op.wFunc = FO_DELETE
            op.pFrom = buffer
            op.pTo = None
            op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
            ret = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
            return ret == 0
        except Exception:
            return False

    @staticmethod
    def permanently_delete(filepath: str) -> bool:
        """Permanently deletes a file from disk with Windows permissions and path safety."""
        target = filepath
        # On Windows, support extended-length paths (>= 260 characters)
        if sys.platform == "win32" and not target.startswith("\\\\?\\"):
            abs_p = os.path.abspath(target)
            if len(abs_p) >= 260:
                target = "\\\\?\\" + abs_p

        try:
            # On Windows, os.remove fails with PermissionError (Access Denied) if the file
            # has the Read-Only attribute set. Clear the read-only flag before removal.
            try:
                os.chmod(target, stat.S_IWRITE)
            except Exception:
                pass

            os.remove(target)
            return True
        except OSError:
            return False

    @classmethod
    def validate_group_safety(cls, groups: List[DuplicateGroup]) -> Tuple[List[FileInfo], List[DuplicateGroup]]:
        """
        Inspects all groups and finds:
        1. All files selected for deletion.
        2. Groups where EVERY copy is selected (which would destroy the file completely!).
        Returns (selected_files, unsafe_groups).
        """
        selected_files: List[FileInfo] = []
        unsafe_groups: List[DuplicateGroup] = []

        for group in groups:
            group_selected = [f for f in group.files if f.selected_for_deletion]
            selected_files.extend(group_selected)

            if len(group_selected) == len(group.files) and len(group.files) > 0:
                unsafe_groups.append(group)

        return selected_files, unsafe_groups

    @classmethod
    def delete_files(
        cls,
        files: List[FileInfo],
        to_recycle_bin: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None
    ) -> DeleteResult:
        """
        Executes deletion for the given files with optional progress and cancellation.
        Returns a DeleteResult (which can also be unpacked as (deleted_count, errors)).
        """
        deleted_count = 0
        freed_bytes = 0
        errors: List[str] = []
        deleted_paths: Set[str] = set()
        cancelled = False
        total = len(files)
        last_progress_time = 0.0

        for idx, f in enumerate(files):
            if is_cancelled and is_cancelled():
                cancelled = True
                break

            current_num = idx + 1
            now = time.time()
            # Throttle progress callbacks to at most ~20 Hz to avoid flooding GUI event loops
            if progress_callback:
                if current_num == 1 or current_num == total or (now - last_progress_time >= 0.05):
                    progress_callback(current_num, total, f.path)
                    last_progress_time = now

            success = False
            if to_recycle_bin:
                success = cls.send_to_recycle_bin(f.path)
                if not success:
                    # If recycle bin fails (e.g. file on network drive or external drive without recycle bin),
                    # note the error
                    errors.append(f"Failed to recycle: {f.path}")
            else:
                success = cls.permanently_delete(f.path)
                if not success:
                    errors.append(f"Failed to delete: {f.path}")

            if success:
                deleted_count += 1
                freed_bytes += f.size
                deleted_paths.add(f.path)

        # Final progress update if we ran to completion
        if progress_callback and not cancelled and total > 0:
            progress_callback(total, total, files[-1].path)

        return DeleteResult(
            deleted_count=deleted_count,
            errors=errors,
            deleted_paths=deleted_paths,
            freed_bytes=freed_bytes,
            cancelled=cancelled
        )

