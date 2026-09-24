import os
import stat
import time
import hashlib
from typing import List, Dict, Tuple, Optional, Callable, Set
from collections import defaultdict

from duopty.models import FileInfo, DuplicateGroup, ScanConfig, ScanProgress, ScanStats
from duopty.cache import HashCache

MAX_ERROR_SAMPLES = 20


class DuplicateScanner:
    """
    High-performance progressive elimination duplicate scanner.
    Tiers:
      1. Size grouping (Eliminates unique sizes with zero file read)
      2. 3-Point Sample hashing (Eliminates non-identical contents reading only ~12KB)
      3. Full cryptographic hashing (SHA-256 / BLAKE2b / MD5 / SHA-1)
      4. Exact byte-by-byte binary stream comparison (Guarantees 100% identity)
    """

    CHUNK_SIZE = 65536  # 64 KB read buffer
    SAMPLE_BLOCK_SIZE = 4096  # 4 KB per sample block (head, mid, tail)

    def __init__(self, config: ScanConfig, progress_callback: Optional[Callable[[ScanProgress], None]] = None):
        self.config = config
        self.progress_callback = progress_callback
        self._is_cancelled = False
        self._is_paused = False
        self.stats = ScanStats()
        self.cache: Optional[HashCache] = HashCache(config.cache_path) if config.use_cache else None

    def _record_error(self, path: str):
        """Tracks a file that could not be read, so results can note it instead of silently dropping it."""
        self.stats.read_errors += 1
        if len(self.stats.error_samples) < MAX_ERROR_SAMPLES:
            self.stats.error_samples.append(path)

    def cancel(self):
        """Signals the scanner to stop immediately."""
        self._is_cancelled = True

    def pause(self):
        self._is_paused = True

    def resume(self):
        self._is_paused = False

    def _check_pause(self):
        while self._is_paused and not self._is_cancelled:
            time.sleep(0.1)

    def _report_progress(self, progress: ScanProgress):
        if self.progress_callback:
            self.progress_callback(progress)

    def _is_hidden(self, filepath: str) -> bool:
        """Checks if a file or its parent directories are hidden."""
        parts = filepath.replace('/', '\\').split('\\')
        for part in parts:
            if part.startswith('.') and part != '.' and part != '..':
                return True
        # Check Windows hidden attribute
        try:
            attrs = os.stat(filepath).st_file_attributes
            if attrs & stat.FILE_ATTRIBUTE_HIDDEN:
                return True
        except (AttributeError, OSError):
            pass
        return False

    def _matches_extension(self, filename: str) -> bool:
        """Check include / exclude extensions."""
        ext = os.path.splitext(filename)[1].lower()
        if self.config.include_exts:
            if ext not in self.config.include_exts:
                return False
        if self.config.exclude_exts:
            if ext in self.config.exclude_exts:
                return False
        return True

    def scan(self) -> List[DuplicateGroup]:
        """
        Executes the 4-stage progressive duplicate detection pipeline.
        Returns a list of DuplicateGroup objects.
        """
        try:
            return self._scan_impl()
        finally:
            if self.cache is not None:
                self.cache.save()

    def _scan_impl(self) -> List[DuplicateGroup]:
        start_time = time.time()
        self._is_cancelled = False
        self._is_paused = False

        # ----------------------------------------------------
        # Phase 1: File Discovery
        # ----------------------------------------------------
        progress = ScanProgress(phase="Discovering candidate files...", files_scanned=0)
        self._report_progress(progress)

        discovered_files: List[FileInfo] = []
        total_discovered_size = 0

        # When following symlinks, track real directory paths already walked so a
        # symlink/junction cycle (a link pointing back into its own ancestry) can't
        # cause an infinite walk.
        visited_real_dirs: Set[str] = set()
        if self.config.follow_symlinks:
            for folder in self.config.folders:
                try:
                    visited_real_dirs.add(os.path.realpath(folder))
                except OSError:
                    pass

        for dir_idx, folder in enumerate(self.config.folders):
            if not os.path.isdir(folder):
                continue

            for root, dirs, files in os.walk(folder, followlinks=self.config.follow_symlinks):
                self._check_pause()
                if self._is_cancelled:
                    return []

                # Filter hidden directories in-place to prevent traversing them
                if self.config.ignore_hidden:
                    dirs[:] = [d for d in dirs if not d.startswith('.')]

                if self.config.follow_symlinks:
                    kept_dirs = []
                    for d in dirs:
                        try:
                            real_d = os.path.realpath(os.path.join(root, d))
                        except OSError:
                            continue
                        if real_d in visited_real_dirs:
                            continue
                        visited_real_dirs.add(real_d)
                        kept_dirs.append(d)
                    dirs[:] = kept_dirs

                for filename in files:
                    if self._is_cancelled:
                        return []

                    if not self._matches_extension(filename):
                        continue

                    full_path = os.path.join(root, filename)

                    if self.config.ignore_hidden and self._is_hidden(full_path):
                        continue

                    try:
                        st = os.stat(full_path)
                    except (OSError, PermissionError):
                        self._record_error(full_path)
                        continue

                    # Filter by min/max size
                    if st.st_size < self.config.min_size:
                        continue
                    if self.config.max_size is not None and st.st_size > self.config.max_size:
                        continue

                    file_info = FileInfo(
                        path=full_path,
                        size=st.st_size,
                        mtime=st.st_mtime,
                        dir_index=dir_idx
                    )
                    discovered_files.append(file_info)
                    total_discovered_size += st.st_size

                    if len(discovered_files) % 500 == 0:
                        progress.files_scanned = len(discovered_files)
                        progress.current_file = full_path
                        self._report_progress(progress)

        self.stats.total_files_discovered = len(discovered_files)
        self.stats.total_size_scanned = total_discovered_size

        if not discovered_files or self._is_cancelled:
            return []

        # ----------------------------------------------------
        # Phase 2 (Stage 1): Size Grouping (Instant Discard)
        # ----------------------------------------------------
        progress = ScanProgress(
            phase="Phase 1/4: Analyzing file sizes (eliminating unique sizes)...",
            files_scanned=0,
            total_files=len(discovered_files),
            percentage=10.0
        )
        self._report_progress(progress)

        size_groups: Dict[int, List[FileInfo]] = defaultdict(list)
        for f in discovered_files:
            size_groups[f.size].append(f)

        # Retain only groups with >= 2 files
        candidate_groups: List[List[FileInfo]] = []
        for size, file_list in size_groups.items():
            if len(file_list) < 2:
                continue
            if self.config.mode == "cross_dir":
                # In cross-dir mode, must have files from at least 2 distinct directories
                dir_indices = {f.dir_index for f in file_list}
                if len(dir_indices) < 2:
                    continue
            candidate_groups.append(file_list)

        candidate_file_count = sum(len(grp) for grp in candidate_groups)
        self.stats.candidate_files_evaluated = candidate_file_count

        if not candidate_groups or self._is_cancelled:
            return []

        # ----------------------------------------------------
        # Special Mode: Name & Size Only
        # ----------------------------------------------------
        if self.config.depth == "name_size":
            final_groups = self._filter_by_name_and_size(candidate_groups)
            return self._build_result_groups(final_groups, start_time)

        # ----------------------------------------------------
        # Phase 3 (Stage 2): Sample / Partial Hash (Head, Mid, Tail)
        # ----------------------------------------------------
        progress = ScanProgress(
            phase="Phase 2/4: Computing quick sample hashes (head/mid/tail)...",
            files_scanned=0,
            total_files=candidate_file_count,
            percentage=20.0
        )
        self._report_progress(progress)

        sample_hash_groups: List[List[FileInfo]] = []
        processed_candidates = 0

        for group in candidate_groups:
            self._check_pause()
            if self._is_cancelled:
                return []

            hash_subgroups: Dict[str, List[FileInfo]] = defaultdict(list)
            for f in group:
                self._check_pause()
                if self._is_cancelled:
                    return []

                sample_hash = self._compute_sample_hash(f)
                f.partial_hash = sample_hash
                if sample_hash:
                    hash_subgroups[sample_hash].append(f)

                processed_candidates += 1
                if processed_candidates % 50 == 0:
                    progress.files_scanned = processed_candidates
                    progress.percentage = 20.0 + (processed_candidates / candidate_file_count) * 20.0
                    progress.current_file = f.filename
                    self._report_progress(progress)

            for shash, sub_files in hash_subgroups.items():
                if len(sub_files) < 2:
                    continue
                if self.config.mode == "cross_dir":
                    if len({f.dir_index for f in sub_files}) < 2:
                        continue
                sample_hash_groups.append(sub_files)

        if not sample_hash_groups or self._is_cancelled:
            return []

        # If user requested 'quick' depth, sample hash is sufficient!
        if self.config.depth == "quick":
            return self._build_result_groups(sample_hash_groups, start_time)

        # ----------------------------------------------------
        # Phase 4 (Stage 3): Full Cryptographic Hash
        # ----------------------------------------------------
        full_hash_candidates = sum(len(grp) for grp in sample_hash_groups)
        progress = ScanProgress(
            phase=f"Phase 3/4: Computing full cryptographic hashes ({self.config.hash_algo.upper()})...",
            files_scanned=0,
            total_files=full_hash_candidates,
            percentage=45.0
        )
        self._report_progress(progress)

        full_hash_groups: List[List[FileInfo]] = []
        processed_full = 0

        for group in sample_hash_groups:
            self._check_pause()
            if self._is_cancelled:
                return []

            full_subgroups: Dict[str, List[FileInfo]] = defaultdict(list)
            for f in group:
                self._check_pause()
                if self._is_cancelled:
                    return []

                # Optimization: If file was <= 3 * SAMPLE_BLOCK_SIZE, partial hash already covered it
                if f.size <= self.SAMPLE_BLOCK_SIZE * 3 and f.partial_hash:
                    f_hash = f.partial_hash
                else:
                    f_hash = self._compute_full_hash(f)

                f.full_hash = f_hash
                if f_hash:
                    full_subgroups[f_hash].append(f)

                processed_full += 1
                if processed_full % 10 == 0 or processed_full == full_hash_candidates:
                    progress.files_scanned = processed_full
                    progress.percentage = 45.0 + (processed_full / full_hash_candidates) * 35.0
                    progress.current_file = f.filename
                    self._report_progress(progress)

            for fhash, sub_files in full_subgroups.items():
                if len(sub_files) < 2:
                    continue
                if self.config.mode == "cross_dir":
                    if len({f.dir_index for f in sub_files}) < 2:
                        continue
                full_hash_groups.append(sub_files)

        if not full_hash_groups or self._is_cancelled:
            return []

        # If user requested 'standard' depth, full hash is sufficient!
        if self.config.depth == "standard":
            return self._build_result_groups(full_hash_groups, start_time)

        # ----------------------------------------------------
        # Phase 5 (Stage 4): Exact Byte-by-Byte Binary Verification
        # ----------------------------------------------------
        progress = ScanProgress(
            phase="Phase 4/4: Performing exact byte-by-byte binary stream verification...",
            files_scanned=0,
            total_files=sum(len(grp) for grp in full_hash_groups),
            percentage=85.0
        )
        self._report_progress(progress)

        verified_groups: List[List[FileInfo]] = []
        verified_count = 0
        total_to_verify = sum(len(grp) for grp in full_hash_groups)

        for group in full_hash_groups:
            self._check_pause()
            if self._is_cancelled:
                return []

            # Partition group into byte-identical clusters
            byte_clusters = self._verify_byte_identical_group(group)
            for cluster in byte_clusters:
                if len(cluster) >= 2:
                    if self.config.mode == "cross_dir":
                        if len({f.dir_index for f in cluster}) < 2:
                            continue
                    verified_groups.append(cluster)

            verified_count += len(group)
            progress.files_scanned = verified_count
            progress.percentage = 85.0 + (verified_count / max(1, total_to_verify)) * 14.0
            self._report_progress(progress)

        return self._build_result_groups(verified_groups, start_time)

    def _compute_sample_hash(self, file_info: FileInfo) -> Optional[str]:
        """
        Reads 3 small blocks: Head (first 4KB), Mid (middle 4KB), Tail (last 4KB).
        Returns the hexadecimal digest of the sample.
        """
        if self.cache is not None:
            cached = self.cache.get(file_info.path, file_info.size, file_info.mtime, self.config.hash_algo)
            if cached and cached.get("partial_hash"):
                return cached["partial_hash"]

        size = file_info.size
        hasher = hashlib.new(self.config.hash_algo)

        try:
            with open(file_info.path, "rb") as f:
                if size <= self.SAMPLE_BLOCK_SIZE * 3:
                    # Small file: read the whole file
                    hasher.update(f.read())
                else:
                    # 1. Head
                    hasher.update(f.read(self.SAMPLE_BLOCK_SIZE))
                    # 2. Mid
                    f.seek(size // 2)
                    hasher.update(f.read(self.SAMPLE_BLOCK_SIZE))
                    # 3. Tail
                    f.seek(size - self.SAMPLE_BLOCK_SIZE)
                    hasher.update(f.read(self.SAMPLE_BLOCK_SIZE))
        except (OSError, PermissionError):
            self._record_error(file_info.path)
            return None

        digest = hasher.hexdigest()
        if self.cache is not None:
            self.cache.put(file_info.path, size, file_info.mtime, self.config.hash_algo, partial_hash=digest)
        return digest

    def _compute_full_hash(self, file_info: FileInfo) -> Optional[str]:
        """Computes complete cryptographic hash by streaming chunks."""
        if self.cache is not None:
            cached = self.cache.get(file_info.path, file_info.size, file_info.mtime, self.config.hash_algo)
            if cached and cached.get("full_hash"):
                return cached["full_hash"]

        hasher = hashlib.new(self.config.hash_algo)
        try:
            with open(file_info.path, "rb") as f:
                while True:
                    self._check_pause()
                    if self._is_cancelled:
                        return None
                    chunk = f.read(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    hasher.update(chunk)
        except (OSError, PermissionError):
            self._record_error(file_info.path)
            return None

        digest = hasher.hexdigest()
        if self.cache is not None:
            self.cache.put(file_info.path, file_info.size, file_info.mtime, self.config.hash_algo, full_hash=digest)
        return digest

    def _compare_files_byte_by_byte(self, path1: str, path2: str) -> bool:
        """Compares two files chunk-by-chunk for 100% exact binary equality."""
        try:
            with open(path1, "rb") as f1, open(path2, "rb") as f2:
                while True:
                    self._check_pause()
                    if self._is_cancelled:
                        return False
                    b1 = f1.read(self.CHUNK_SIZE)
                    b2 = f2.read(self.CHUNK_SIZE)
                    if b1 != b2:
                        return False
                    if not b1:
                        return True
        except (OSError, PermissionError):
            return False

    def _verify_byte_identical_group(self, group: List[FileInfo]) -> List[List[FileInfo]]:
        """
        Partitions candidate files into lists of byte-identical files.
        Since hash already matched, usually all files in group are identical.
        We compare against the first file of each cluster.
        """
        clusters: List[List[FileInfo]] = []
        for file_info in group:
            matched = False
            for cluster in clusters:
                if self._compare_files_byte_by_byte(cluster[0].path, file_info.path):
                    cluster.append(file_info)
                    matched = True
                    break
            if not matched:
                clusters.append([file_info])
        return clusters

    def _filter_by_name_and_size(self, candidate_groups: List[List[FileInfo]]) -> List[List[FileInfo]]:
        """Used when depth is 'name_size': group strictly by identical filename and size."""
        name_groups: List[List[FileInfo]] = []
        for grp in candidate_groups:
            by_name: Dict[str, List[FileInfo]] = defaultdict(list)
            for f in grp:
                by_name[f.filename.lower()].append(f)
            for fname, sub in by_name.items():
                if len(sub) >= 2:
                    if self.config.mode == "cross_dir":
                        if len({f.dir_index for f in sub}) < 2:
                            continue
                    name_groups.append(sub)
        return name_groups

    def _build_result_groups(self, file_groups: List[List[FileInfo]], start_time: float) -> List[DuplicateGroup]:
        """Builds final DuplicateGroup objects sorted by total potential savings."""
        result_groups: List[DuplicateGroup] = []
        group_id = 1
        total_duplicates = 0
        total_space_reclaimable = 0

        # Sort files in each group by modification time (oldest first)
        for files in file_groups:
            files.sort(key=lambda f: f.mtime)
            size = files[0].size
            hash_val = files[0].full_hash or files[0].partial_hash or f"size_{size}"
            group = DuplicateGroup(
                group_id=group_id,
                size=size,
                hash_val=hash_val,
                files=files
            )
            result_groups.append(group)
            total_duplicates += (len(files) - 1)
            total_space_reclaimable += group.space_reclaimable
            group_id += 1

        # Sort groups by size descending (largest space wasters first)
        result_groups.sort(key=lambda g: g.space_reclaimable, reverse=True)

        # Reassign sequential IDs
        for idx, grp in enumerate(result_groups, start=1):
            grp.group_id = idx

        self.stats.groups_count = len(result_groups)
        self.stats.duplicates_count = total_duplicates
        self.stats.space_reclaimable = total_space_reclaimable
        self.stats.scan_duration = time.time() - start_time

        final_progress = ScanProgress(
            phase="Scan completed!",
            files_scanned=self.stats.candidate_files_evaluated,
            total_files=self.stats.candidate_files_evaluated,
            percentage=100.0,
            groups_found=len(result_groups),
            duplicates_found=total_duplicates,
            potential_savings=total_space_reclaimable
        )
        self._report_progress(final_progress)

        return result_groups
