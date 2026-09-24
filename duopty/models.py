from dataclasses import dataclass, field
from typing import List, Optional, Set
import os


@dataclass
class FileInfo:
    """Represents a discovered file and its analysis metadata."""
    path: str
    size: int
    mtime: float
    dir_index: int = 0  # 0 for Folder A, 1 for Folder B, etc.
    partial_hash: Optional[str] = None
    full_hash: Optional[str] = None
    selected_for_deletion: bool = False

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    @property
    def directory(self) -> str:
        return os.path.dirname(self.path)


@dataclass
class DuplicateGroup:
    """Represents a collection of identical files."""
    group_id: int
    size: int
    hash_val: str
    files: List[FileInfo] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.files)

    @property
    def space_reclaimable(self) -> int:
        """Space saved if only 1 copy is retained."""
        if len(self.files) > 1:
            return (len(self.files) - 1) * self.size
        return 0

    @property
    def selected_count(self) -> int:
        return sum(1 for f in self.files if f.selected_for_deletion)

    @property
    def selected_size(self) -> int:
        return self.selected_count * self.size


@dataclass
class ScanConfig:
    """User-selected configuration for the duplicate scan."""
    folders: List[str] = field(default_factory=list)
    mode: str = "combined"  # 'combined' or 'cross_dir'
    depth: str = "strict"   # 'strict', 'standard', 'quick', 'name_size'
    hash_algo: str = "sha256"  # 'sha256', 'blake2b', 'md5', 'sha1'
    min_size: int = 1       # default 1 byte (skips 0-byte files)
    max_size: Optional[int] = None
    include_exts: Set[str] = field(default_factory=set)
    exclude_exts: Set[str] = field(default_factory=set)
    ignore_hidden: bool = True
    follow_symlinks: bool = False
    sample_size: int = 4096


@dataclass
class ScanProgress:
    """Real-time progress reporting for GUI."""
    phase: str = "Idle"
    current_file: str = ""
    files_scanned: int = 0
    total_files: int = 0
    percentage: float = 0.0
    groups_found: int = 0
    duplicates_found: int = 0
    potential_savings: int = 0


@dataclass
class ScanStats:
    """Final metrics of a completed scan."""
    total_files_discovered: int = 0
    total_size_scanned: int = 0
    candidate_files_evaluated: int = 0
    groups_count: int = 0
    duplicates_count: int = 0
    space_reclaimable: int = 0
    scan_duration: float = 0.0
