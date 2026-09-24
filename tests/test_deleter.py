import os
import tempfile
import shutil
import unittest

from duopty.models import FileInfo, DuplicateGroup
from duopty.deleter import FileDeleter


class TestFileDeleter(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="duopty_del_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_group_safety_all_selected(self):
        """Test detection of groups where every copy has been selected for deletion."""
        f1 = FileInfo(path=os.path.join(self.test_dir, "f1.txt"), size=10, mtime=100.0, selected_for_deletion=True)
        f2 = FileInfo(path=os.path.join(self.test_dir, "f2.txt"), size=10, mtime=101.0, selected_for_deletion=True)
        group1 = DuplicateGroup(group_id=1, size=10, hash_val="abc", files=[f1, f2])

        f3 = FileInfo(path=os.path.join(self.test_dir, "f3.txt"), size=20, mtime=100.0, selected_for_deletion=False)
        f4 = FileInfo(path=os.path.join(self.test_dir, "f4.txt"), size=20, mtime=101.0, selected_for_deletion=True)
        group2 = DuplicateGroup(group_id=2, size=20, hash_val="xyz", files=[f3, f4])

        selected, unsafe = FileDeleter.validate_group_safety([group1, group2])

        self.assertEqual(len(selected), 3)
        self.assertEqual(len(unsafe), 1)
        self.assertEqual(unsafe[0].group_id, 1)

    def test_permanent_delete(self):
        """Test permanent deletion removes file from disk."""
        target = os.path.join(self.test_dir, "to_delete.txt")
        with open(target, "w") as f:
            f.write("content")
        self.assertTrue(os.path.exists(target))

        success = FileDeleter.permanently_delete(target)
        self.assertTrue(success)
        self.assertFalse(os.path.exists(target))

    def test_recycle_bin_delete(self):
        """Test moving file to Windows Recycle Bin."""
        target = os.path.join(self.test_dir, "to_recycle.txt")
        with open(target, "w") as f:
            f.write("content to recycle")
        self.assertTrue(os.path.exists(target))

        success = FileDeleter.send_to_recycle_bin(target)
        self.assertTrue(success)
        self.assertFalse(os.path.exists(target))

    def test_permanent_delete_readonly_file(self):
        """Test permanent deletion succeeds even if file has Windows read-only attribute set."""
        import stat
        target = os.path.join(self.test_dir, "readonly_to_delete.txt")
        with open(target, "w") as f:
            f.write("readonly file content")
        # Mark file as read-only
        os.chmod(target, stat.S_IREAD)
        self.assertTrue(os.path.exists(target))

        success = FileDeleter.permanently_delete(target)
        self.assertTrue(success)
        self.assertFalse(os.path.exists(target))

    def test_delete_files_progress_and_result(self):
        """Test delete_files returns DeleteResult with progress updates and deleted paths."""
        f1_path = os.path.join(self.test_dir, "del1.txt")
        f2_path = os.path.join(self.test_dir, "del2.txt")
        with open(f1_path, "w") as f:
            f.write("data1")
        with open(f2_path, "w") as f:
            f.write("data2")

        files = [
            FileInfo(path=f1_path, size=5, mtime=100.0),
            FileInfo(path=f2_path, size=5, mtime=101.0),
        ]

        progress_calls = []

        def on_prog(curr, tot, path):
            progress_calls.append((curr, tot, path))

        res = FileDeleter.delete_files(files, to_recycle_bin=False, progress_callback=on_prog)

        # Verify tuple unpacking compatibility
        count, errs = res
        self.assertEqual(count, 2)
        self.assertEqual(len(errs), 0)

        # Verify extended DeleteResult attributes
        self.assertEqual(res.deleted_count, 2)
        self.assertEqual(res.freed_bytes, 10)
        self.assertFalse(res.cancelled)
        self.assertIn(f1_path, res.deleted_paths)
        self.assertIn(f2_path, res.deleted_paths)
        self.assertTrue(len(progress_calls) > 0)

    def test_delete_files_cancellation(self):
        """Test delete_files stops when is_cancelled returns True."""
        f1_path = os.path.join(self.test_dir, "del_c1.txt")
        f2_path = os.path.join(self.test_dir, "del_c2.txt")
        with open(f1_path, "w") as f:
            f.write("data1")
        with open(f2_path, "w") as f:
            f.write("data2")

        files = [
            FileInfo(path=f1_path, size=5, mtime=100.0),
            FileInfo(path=f2_path, size=5, mtime=101.0),
        ]

        # Cancel immediately on or after first file
        cancel_state = {"cancelled": False}

        def check_cancelled():
            return cancel_state["cancelled"]

        def on_prog(curr, tot, path):
            cancel_state["cancelled"] = True

        res = FileDeleter.delete_files(
            files,
            to_recycle_bin=False,
            progress_callback=on_prog,
            is_cancelled=check_cancelled
        )

        self.assertTrue(res.cancelled)
        self.assertEqual(res.deleted_count, 1)
        self.assertFalse(os.path.exists(f1_path))
        # f2 should not have been deleted
        self.assertTrue(os.path.exists(f2_path))


if __name__ == "__main__":
    unittest.main()
