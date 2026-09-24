import os
import tempfile
import shutil
import unittest

from duopty.cache import HashCache


class TestHashCache(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="duopty_cache_test_")
        self.cache_path = os.path.join(self.tmp_dir, "cache.json")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_miss_on_empty_cache(self):
        cache = HashCache(self.cache_path)
        self.assertIsNone(cache.get("C:\\file.txt", 100, 123.0, "sha256"))

    def test_put_then_get_hit(self):
        cache = HashCache(self.cache_path)
        cache.put("C:\\file.txt", 100, 123.0, "sha256", full_hash="abc123")
        entry = cache.get("C:\\file.txt", 100, 123.0, "sha256")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["full_hash"], "abc123")

    def test_miss_when_size_changed(self):
        cache = HashCache(self.cache_path)
        cache.put("C:\\file.txt", 100, 123.0, "sha256", full_hash="abc123")
        self.assertIsNone(cache.get("C:\\file.txt", 200, 123.0, "sha256"))

    def test_miss_when_mtime_changed(self):
        cache = HashCache(self.cache_path)
        cache.put("C:\\file.txt", 100, 123.0, "sha256", full_hash="abc123")
        self.assertIsNone(cache.get("C:\\file.txt", 100, 999.0, "sha256"))

    def test_miss_when_algo_changed(self):
        cache = HashCache(self.cache_path)
        cache.put("C:\\file.txt", 100, 123.0, "sha256", full_hash="abc123")
        self.assertIsNone(cache.get("C:\\file.txt", 100, 123.0, "md5"))

    def test_persists_across_instances(self):
        cache1 = HashCache(self.cache_path)
        cache1.put("C:\\file.txt", 100, 123.0, "sha256", partial_hash="sample1", full_hash="full1")
        cache1.save()

        cache2 = HashCache(self.cache_path)
        entry = cache2.get("C:\\file.txt", 100, 123.0, "sha256")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["partial_hash"], "sample1")
        self.assertEqual(entry["full_hash"], "full1")

    def test_clear_removes_entries_and_persists(self):
        cache = HashCache(self.cache_path)
        cache.put("C:\\file.txt", 100, 123.0, "sha256", full_hash="abc123")
        cache.save()
        cache.clear()
        self.assertEqual(len(cache), 0)

        reloaded = HashCache(self.cache_path)
        self.assertEqual(len(reloaded), 0)

    def test_save_is_noop_without_changes(self):
        cache = HashCache(self.cache_path)
        cache.save()
        self.assertFalse(os.path.exists(self.cache_path))


if __name__ == "__main__":
    unittest.main()
