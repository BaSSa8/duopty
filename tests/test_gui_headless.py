import os
import tempfile
import shutil
import unittest
from unittest.mock import patch
import tkinter as tk

from duopty.gui import DuoPtyGUI, CHECK_CHAR, UNCHECK_CHAR
from duopty.deleter import FileDeleter


class TestGUIIntegration(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="duopty_gui_test_")
        self.f1 = os.path.join(self.test_dir, "file_a.txt")
        self.f2 = os.path.join(self.test_dir, "file_b.txt")
        with open(self.f1, "w") as f: f.write("duplicate content test 12345")
        with open(self.f2, "w") as f: f.write("duplicate content test 12345")

        self.root = tk.Tk()
        self.root.withdraw()  # Don't show window on screen during automated test
        self.app = DuoPtyGUI(self.root)

    def tearDown(self):
        self.root.destroy()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_gui_scan_and_smart_select(self):
        """Simulate setting folders, scanning, and testing smart selection in GUI."""
        self.app.folder1_var.set(self.test_dir)
        self.app._start_scan()

        # Wait for scanner thread to complete
        if self.app.scanner_thread:
            self.app.scanner_thread.join(timeout=3.0)

        # Process pending Tk events
        self.app._start_queue_listener()
        self.root.update_idletasks()

        # Verify duplicate groups found
        self.assertEqual(len(self.app.duplicate_groups), 1)
        group = self.app.duplicate_groups[0]
        self.assertEqual(group.count, 2)

        # Test Smart Select 'keep_first'
        self.app._smart_select("keep_first")
        self.assertFalse(group.files[0].selected_for_deletion)
        self.assertTrue(group.files[1].selected_for_deletion)

        # Test Smart Select 'keep_newest'
        self.app._smart_select("keep_newest")
        self.root.update_idletasks()

        # Test Deselect All
        self.app._select_all(False)
        self.assertEqual(group.selected_count, 0)

        # Test Select All
        self.app._select_all(True)
        self.assertEqual(group.selected_count, 2)

    def test_gui_deletion_flow_permanent(self):
        """Simulate scanning, selecting duplicate, and permanent deletion flow."""
        self.app.folder1_var.set(self.test_dir)
        self.app._start_scan()

        if self.app.scanner_thread:
            self.app.scanner_thread.join(timeout=3.0)

        self.app._start_queue_listener()
        self.root.update_idletasks()

        self.assertEqual(len(self.app.duplicate_groups), 1)

        # Select second file for deletion
        self.app._smart_select("keep_first")
        self.app.recycle_bin_var.set(False)

        selected_files, _ = FileDeleter.validate_group_safety(self.app.duplicate_groups)
        self.assertEqual(len(selected_files), 1)
        deleted_file_path = selected_files[0].path

        # Execute deletion through FileDeleter directly to simulate worker thread
        res = FileDeleter.delete_files(selected_files, to_recycle_bin=False)
        self.assertEqual(res.deleted_count, 1)
        self.assertFalse(os.path.exists(deleted_file_path))

        # Invoke _on_deletion_completed with dummy dialog and mocked messagebox
        class DummyDialog:
            def winfo_exists(self): return False
            def destroy(self): pass

        with patch("duopty.gui.messagebox.showinfo") as mock_info:
            self.app._on_deletion_completed(res, DummyDialog(), to_recycle=False)
            self.assertTrue(mock_info.called)

        # Group should be removed because only 1 copy remains (len < 2)
        self.assertEqual(len(self.app.duplicate_groups), 0)
        self.assertEqual(len(self.app.tree.get_children()), 0)



if __name__ == "__main__":
    unittest.main()

