# DuoPty - Fix Program Hang / "Not Responding" During File Deletion
## Phase 2: Implementation Plan

## Problem Analysis

When the user deletes files without using the Recycle Bin (permanent deletion), or when deleting many files, the program becomes unresponsive and Windows displays `(Not Responding)`, eventually prompting the user to terminate ("crash") the application.

### Root Causes Identified

1. **Synchronous UI Thread Execution**: In `duopty/gui.py`, `_confirm_and_delete()` previously ran `FileDeleter.delete_files()` directly on the Tkinter main UI thread. During deletion of multiple files, large files, or files on slow storage, the Tkinter event loop was blocked from processing Windows window messages (`WM_PAINT`, `WM_TIMER`, etc.). After 5 seconds of message queue starvation, Windows flags the window as **Not Responding** and prompts the user to force-close it.
2. **Post-Deletion Disk Bottleneck**: Following deletion, `duopty/gui.py` iterated through every remaining file in every group and performed synchronous `os.path.exists(f.path)` queries on disk on the UI thread.
3. **Windows Read-Only File Failures**: In `duopty/deleter.py`, `permanently_delete()` calls `os.remove(filepath)`. On Windows, `os.remove` raises `PermissionError: [WinError 5] Access is denied` if a file has the `FILE_ATTRIBUTE_READONLY` attribute set. In contrast, Windows Shell (`send_to_recycle_bin`) automatically handles read-only files.
4. **Lack of Progress Feedback**: No progress dialog or indicator existed during deletion, making the application appear frozen even during fast deletions.

---

## Proposed Changes

### 1. File Deleter Engine (`duopty/deleter.py`)
- **Read-only & Long Path Handling**: In `permanently_delete()`, clear the Windows read-only attribute (`stat.S_IWRITE`) before `os.remove()`, and handle Windows extended path length (`\\?\`) for paths >= 260 characters.
- **`DeleteResult` Model**: Introduce a `DeleteResult` class holding `deleted_count`, `errors`, `deleted_paths`, `freed_bytes`, and `cancelled` status. Support unpacking as a 2-tuple `(deleted_count, errors)` for 100% backward compatibility with any existing tests or callers.
- **Progress & Cancellation Callbacks**: Add `progress_callback: Optional[Callable[[int, int, str], None]]` and `is_cancelled: Optional[Callable[[], bool]]` to `FileDeleter.delete_files()`. Throttle progress reporting (~20 Hz) to keep GUI updates responsive without queue saturation.

### 2. GUI Asynchronous Deletion (`duopty/gui.py`)
- **`DeletionProgressDialog` Component**: Create a modal dialog centered over the main window with:
  - Header & status text: `"Deleting file X of Y..."`
  - Filename / path display with ellipsis truncation
  - Determinate progress bar
  - `"⏹ Cancel"` button to safely abort deletion between files
  - Dark theme styling matching `duopty/theme.py`
- **Background Worker Thread**: In `_confirm_and_delete()`, launch deletion inside a background thread (`threading.Thread(daemon=True)`), dispatching progress updates to the dialog via `root.after_idle()`.
- **Fast Model Update**: Update internal `duplicate_groups` using the returned `res.deleted_paths` set directly, eliminating thousands of redundant `os.path.exists()` calls on the UI thread.
- **Graceful Completion**: Close the dialog and display a clear summary messagebox (including if cancelled, or with specific error details).

### 3. Unit Tests (`tests/test_deleter.py`, `tests/test_gui_headless.py`)
- Add test for `permanently_delete()` with read-only files on Windows.
- Add test for `delete_files()` progress callback and cancellation.
- Add test verifying backward-compatible tuple unpacking of `delete_files()`.
- Add headless GUI test for deletion flow.

---

## Verification Plan

### Automated Tests
- Run full unit test suite: `python -m unittest discover tests`

### Manual / Script Verification
- Run a verification script creating 100+ temporary files (including read-only files and files without recycle bin) to verify that:
  - Read-only files delete successfully without access denied errors.
  - Progress updates smoothly without freezing.
  - Cancellation terminates the loop cleanly.
