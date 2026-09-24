import os
import tempfile
import shutil
import unittest

from duopty.models import ScanConfig, ScanProgress, FileInfo
from duopty.scanner import DuplicateScanner


class TestDuplicateScanner(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="duopty_test_")
        self.dir_a = os.path.join(self.test_dir, "dir_a")
        self.dir_b = os.path.join(self.test_dir, "dir_b")
        os.makedirs(self.dir_a, exist_ok=True)
        os.makedirs(self.dir_b, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_identical_files_detected_single_folder(self):
        """Test finding exact duplicates within a single directory."""
        content = b"Exact identical content repeated in multiple files for testing."
        f1 = os.path.join(self.dir_a, "file1.txt")
        f2 = os.path.join(self.dir_a, "file2.txt")
        f3 = os.path.join(self.dir_a, "unique.txt")

        with open(f1, "wb") as f: f.write(content)
        with open(f2, "wb") as f: f.write(content)
        with open(f3, "wb") as f: f.write(b"Completely unique different content.")

        config = ScanConfig(folders=[self.dir_a], depth="strict")
        scanner = DuplicateScanner(config)
        groups = scanner.scan()

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].count, 2)
        paths = {f.path for f in groups[0].files}
        self.assertIn(f1, paths)
        self.assertIn(f2, paths)
        self.assertNotIn(f3, paths)

    def test_different_sizes_eliminated_early(self):
        """Test files with different sizes are eliminated immediately without hashing."""
        f1 = os.path.join(self.dir_a, "short.txt")
        f2 = os.path.join(self.dir_a, "long.txt")

        with open(f1, "wb") as f: f.write(b"12345")
        with open(f2, "wb") as f: f.write(b"1234567890")

        config = ScanConfig(folders=[self.dir_a], depth="strict")
        scanner = DuplicateScanner(config)
        groups = scanner.scan()

        self.assertEqual(len(groups), 0)
        self.assertEqual(scanner.stats.candidate_files_evaluated, 0)

    def test_same_size_different_sample_eliminated(self):
        """Test files with same size but different sample headers are eliminated in Stage 2."""
        size = 10000
        f1 = os.path.join(self.dir_a, "f1.dat")
        f2 = os.path.join(self.dir_a, "f2.dat")

        with open(f1, "wb") as f: f.write(b"A" * size)
        with open(f2, "wb") as f: f.write(b"B" * size)

        config = ScanConfig(folders=[self.dir_a], depth="strict")
        scanner = DuplicateScanner(config)
        groups = scanner.scan()

        self.assertEqual(len(groups), 0)

    def test_same_sample_different_body_eliminated_in_full_hash(self):
        """
        Test files with matching 4KB head and tail, but different middle,
        are caught and eliminated during full cryptographic hashing.
        """
        head = b"H" * 4096
        tail = b"T" * 4096
        # Size = 4096 + 8192 + 4096 = 16384 bytes
        # Middle is at offset 8192. Let's make bytes 5000-7000 differ!
        mid1 = b"1" * 8192
        mid2 = b"2" * 8192

        f1 = os.path.join(self.dir_a, "head_tail1.bin")
        f2 = os.path.join(self.dir_a, "head_tail2.bin")

        with open(f1, "wb") as f: f.write(head + mid1 + tail)
        with open(f2, "wb") as f: f.write(head + mid2 + tail)

        config = ScanConfig(folders=[self.dir_a], depth="strict")
        scanner = DuplicateScanner(config)
        groups = scanner.scan()

        self.assertEqual(len(groups), 0)

    def test_cross_directory_comparison(self):
        """Test cross-directory mode: only duplicates spanning both Dir A and Dir B are returned."""
        content1 = b"Shared duplicate between folder A and folder B."
        content_intra = b"Intra duplicate only in folder A."

        # File in A and file in B (cross-directory duplicate)
        f_a1 = os.path.join(self.dir_a, "shared_a.txt")
        f_b1 = os.path.join(self.dir_b, "shared_b.txt")
        with open(f_a1, "wb") as f: f.write(content1)
        with open(f_b1, "wb") as f: f.write(content1)

        # Two files in A only (intra-folder duplicate in A)
        f_a_dup1 = os.path.join(self.dir_a, "intra1.txt")
        f_a_dup2 = os.path.join(self.dir_a, "intra2.txt")
        with open(f_a_dup1, "wb") as f: f.write(content_intra)
        with open(f_a_dup2, "wb") as f: f.write(content_intra)

        # Cross-dir mode
        config = ScanConfig(folders=[self.dir_a, self.dir_b], mode="cross_dir", depth="strict")
        scanner = DuplicateScanner(config)
        groups = scanner.scan()

        self.assertEqual(len(groups), 1)
        paths = {f.path for f in groups[0].files}
        self.assertIn(f_a1, paths)
        self.assertIn(f_b1, paths)
        self.assertNotIn(f_a_dup1, paths)

    def test_filter_min_size(self):
        """Test skipping empty / zero-byte files."""
        f1 = os.path.join(self.dir_a, "empty1.txt")
        f2 = os.path.join(self.dir_a, "empty2.txt")
        with open(f1, "wb") as f: pass
        with open(f2, "wb") as f: pass

        config = ScanConfig(folders=[self.dir_a], min_size=1)
        scanner = DuplicateScanner(config)
        groups = scanner.scan()

        self.assertEqual(len(groups), 0)

    def test_extension_filter(self):
        """Test include extensions."""
        content = b"Same content"
        f_txt1 = os.path.join(self.dir_a, "doc1.txt")
        f_txt2 = os.path.join(self.dir_a, "doc2.txt")
        f_jpg1 = os.path.join(self.dir_a, "img1.jpg")
        f_jpg2 = os.path.join(self.dir_a, "img2.jpg")

        for p in [f_txt1, f_txt2, f_jpg1, f_jpg2]:
            with open(p, "wb") as f: f.write(content)

        config = ScanConfig(folders=[self.dir_a], include_exts={".jpg"})
        scanner = DuplicateScanner(config)
        groups = scanner.scan()

        self.assertEqual(len(groups), 1)
        paths = {f.path for f in groups[0].files}
        self.assertIn(f_jpg1, paths)
        self.assertIn(f_jpg2, paths)
        self.assertNotIn(f_txt1, paths)

    def test_hash_cache_hit_avoids_recompute(self):
        """A second scan with use_cache=True should reuse hashes from the first scan."""
        content = b"Cached duplicate content." * 100
        f1 = os.path.join(self.dir_a, "cache1.bin")
        f2 = os.path.join(self.dir_a, "cache2.bin")
        with open(f1, "wb") as f: f.write(content)
        with open(f2, "wb") as f: f.write(content)

        cache_path = os.path.join(self.test_dir, "hash_cache.json")
        config = ScanConfig(folders=[self.dir_a], depth="strict", use_cache=True, cache_path=cache_path)

        first = DuplicateScanner(config)
        groups1 = first.scan()
        self.assertEqual(len(groups1), 1)
        self.assertTrue(os.path.exists(cache_path))

        second = DuplicateScanner(config)
        groups2 = second.scan()
        self.assertEqual(len(groups2), 1)
        paths = {f.path for f in groups2[0].files}
        self.assertIn(f1, paths)
        self.assertIn(f2, paths)

    def test_unreadable_file_increments_error_stats(self):
        """Hash computation on a file that can't be opened should be recorded, not silently dropped."""
        config = ScanConfig(folders=[self.dir_a])
        scanner = DuplicateScanner(config)
        ghost = FileInfo(path=os.path.join(self.dir_a, "does_not_exist.bin"), size=10, mtime=0.0)

        result = scanner._compute_full_hash(ghost)

        self.assertIsNone(result)
        self.assertEqual(scanner.stats.read_errors, 1)
        self.assertIn(ghost.path, scanner.stats.error_samples)

    def test_symlink_cycle_does_not_hang(self):
        """A directory symlink pointing back at an ancestor must not cause an infinite walk."""
        loop_link = os.path.join(self.dir_a, "loop_back")
        try:
            os.symlink(self.dir_a, loop_link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Creating symlinks is not permitted in this environment")

        with open(os.path.join(self.dir_a, "f1.txt"), "wb") as f: f.write(b"same content")
        with open(os.path.join(self.dir_a, "f2.txt"), "wb") as f: f.write(b"same content")

        config = ScanConfig(folders=[self.dir_a], depth="strict", follow_symlinks=True)
        scanner = DuplicateScanner(config)

        groups = scanner.scan()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].count, 2)


if __name__ == "__main__":
    unittest.main()
