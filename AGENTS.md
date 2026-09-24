# AGENTS.md — DuoPty Project Guidelines for Claude Code and Other Coding Agents

## Project Overview
**DuoPty** is a high-performance Python desktop application for Windows 10/11 that finds and safely removes duplicate files across single or multiple directories, and supports cross-directory comparisons (Directory A vs Directory B).

- **UI Framework**: Python Tkinter / ttk with custom modern dark theme and Windows High-DPI awareness.
- **Dependencies**: Python standard library only (no external pip dependencies required).
- **Platform**: Windows-first (`ctypes.windll.shell32` for Windows Recycle Bin, Windows long paths `\\?\`, Windows file attributes).

---

## Common Developer Commands

### Run Application
```bash
# Launch GUI
python main.py

# Launch GUI via batch launcher
run.bat

# Launch with preloaded folders and comparison mode
python main.py "C:\Path\To\Folder1" "D:\Path\To\Folder2" --mode cross_dir
```

### Run Tests
```bash
# Run all unit and integration tests
python -m unittest discover tests

# Run specific test modules
python -m unittest tests.test_scanner
python -m unittest tests.test_deleter
python -m unittest tests.test_gui_headless
```

---

## Architectural Principles & Core Modules

### 1. 4-Stage Progressive Elimination Pipeline (`duopty/scanner.py`)
Heavy I/O and hashing are only executed when strictly necessary:
1. **Stage 1 (File Size)**: Metadata only (`os.stat().st_size`). Discards unique sizes with 0 disk read.
2. **Stage 2 (3-Point Sample Hash)**: Reads 4KB head, 4KB mid, 4KB tail (~12 KB total).
3. **Stage 3 (Full Cryptographic Hash)**: Full streaming hash (SHA-256 by default, BLAKE2b, MD5, SHA-1).
4. **Stage 4 (Byte-by-Byte Stream Verification)**: Pairwise exact binary buffer match (`b1 == b2`) to ensure 100% mathematical certainty.

### 2. Deletion Engine & Concurrency (`duopty/deleter.py`, `duopty/gui.py`)
- **Windows Recycle Bin**: Default deletion method using `ctypes.windll.shell32.SHFileOperationW` (`FOF_ALLOWUNDO`), allowing desktop restoration.
- **Permanent Deletion**: Clears Windows read-only attribute (`stat.S_IWRITE`) before `os.remove` and handles extended paths (`\\?\`).
- **Threading Model**: Never run file scans or batch deletions on the Tkinter main thread. Run in background daemon threads (`threading.Thread(daemon=True)`) and post progress back to Tkinter via `root.after_idle()` or `root.after()`.
- **Return Type**: `FileDeleter.delete_files()` returns a `DeleteResult` instance which also unpacks as `(deleted_count, errors)` for backward compatibility.
- **In-Memory Pruning**: Update duplicate groups using `res.deleted_paths` set directly; avoid running synchronous `os.path.exists()` on every file after deletion.

### 3. Key Files Map
```
duopty/
├── duopty/
│   ├── models.py       # FileInfo, DuplicateGroup, ScanConfig, ScanProgress, ScanStats
│   ├── scanner.py      # DuplicateScanner with 4-stage progressive pipeline & cancel/pause
│   ├── cache.py        # HashCache: persists hashes across scans, keyed by path/size/mtime
│   ├── deleter.py      # FileDeleter, DeleteResult, Recycle Bin & permanent deletion
│   ├── gui.py          # DuoPtyGUI & DeletionProgressDialog (Tkinter GUI)
│   ├── theme.py        # Modern dark palette, ttk styles, DPI awareness
│   └── utils.py        # File size formatting and helpers
├── tests/
│   ├── test_scanner.py       # Engine tests for all 4 stages, cross-dir mode, cache, symlink guard
│   ├── test_cache.py         # HashCache persistence and invalidation tests
│   ├── test_deleter.py       # Deletion tests, read-only permissions, cancellation
│   └── test_gui_headless.py  # Headless Tkinter tests for scan & deletion workflows
├── docs/                     # Implementation plans, walkthroughs, and architecture docs
├── .github/workflows/        # CI (runs the test suite on windows-latest)
├── main.py                   # Application entrypoint
├── run.bat                   # Windows batch file launcher
└── README.md                 # User documentation
```

---

## Documentation & History

Historical context, implementation plans, and verification walkthroughs are cataloged in `docs/`:

- **[System Architecture](docs/ARCHITECTURE.md)**: In-depth technical architecture.
- **[Documentation Index](docs/INDEX.md)**: Index of all documentation.
- **Implementation Plans**:
  - `docs/plans/01_initial_implementation_plan.md`: Foundational system design and pipeline.
  - `docs/plans/02_deletion_concurrency_fix_plan.md`: Fix for Tkinter UI freeze & read-only permissions.
- **Walkthroughs**:
  - `docs/walkthroughs/01_initial_walkthrough.md`: Initial system build verification.
  - `docs/walkthroughs/02_deletion_concurrency_fix_walkthrough.md`: Deletion concurrency fix verification.

---

## Code Style & Conventions

- **Standard Library Only**: Do not introduce external dependencies unless explicitly requested.
- **Type Annotations**: Use `typing` annotations (`Optional`, `List`, `Dict`, `Tuple`, `Callable`).
- **Thread Safety**: Never update Tkinter widgets directly from background worker threads; always use `root.after_idle()` or `root.after()`.
- **Windows Compatibility**: Always use `os.path.normpath` or raw strings for Windows paths; support paths exceeding 260 chars where applicable.
