import os
import json
import threading
from typing import Optional, Dict, Any


class HashCache:
    """
    Persists partial/full file hashes across scans, keyed by absolute path.
    An entry is only reused when the file's recorded size and mtime still
    match the file on disk, so any modification invalidates it automatically.
    """

    def __init__(self, cache_path: Optional[str] = None):
        self.cache_path = cache_path or self._default_path()
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._dirty = False
        self._lock = threading.Lock()
        self._load()

    @staticmethod
    def _default_path() -> str:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        cache_dir = os.path.join(base, "DuoPty")
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except OSError:
            pass
        return os.path.join(cache_dir, "hash_cache.json")

    def _load(self):
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._entries = data
        except (OSError, ValueError):
            self._entries = {}

    def get(self, path: str, size: int, mtime: float, algo: str) -> Optional[Dict[str, Any]]:
        """Returns the cached entry if it still matches size/mtime/algo, else None."""
        entry = self._entries.get(path)
        if not entry:
            return None
        if entry.get("size") != size or entry.get("algo") != algo:
            return None
        # Filesystem mtimes can carry tiny float rounding drift between reads.
        if abs(entry.get("mtime", 0.0) - mtime) > 1e-6:
            return None
        return entry

    def put(
        self,
        path: str,
        size: int,
        mtime: float,
        algo: str,
        partial_hash: Optional[str] = None,
        full_hash: Optional[str] = None
    ):
        """Records a hash result. Stale entries (different size/mtime/algo) are replaced."""
        with self._lock:
            entry = self._entries.get(path)
            if not entry or entry.get("size") != size or entry.get("mtime") != mtime or entry.get("algo") != algo:
                entry = {"size": size, "mtime": mtime, "algo": algo}
            if partial_hash is not None:
                entry["partial_hash"] = partial_hash
            if full_hash is not None:
                entry["full_hash"] = full_hash
            self._entries[path] = entry
            self._dirty = True

    def save(self):
        """Writes the cache to disk if it has unsaved changes."""
        if not self._dirty:
            return
        with self._lock:
            try:
                tmp_path = self.cache_path + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(self._entries, f)
                os.replace(tmp_path, self.cache_path)
                self._dirty = False
            except OSError:
                pass

    def clear(self):
        """Discards all cached entries, in memory and on disk."""
        with self._lock:
            self._entries = {}
            self._dirty = True
        self.save()

    def __len__(self) -> int:
        return len(self._entries)
