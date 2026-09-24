# DuoPty — Intelligent Duplicate File Scanner & Remover

[![Tests](https://github.com/BaSSa8/duopty/actions/workflows/tests.yml/badge.svg)](https://github.com/BaSSa8/duopty/actions/workflows/tests.yml)

**DuoPty** is a high-performance Python desktop application designed to accurately identify and safely remove duplicate files across one or multiple directories, or perform cross-folder comparisons (e.g. Directory A vs Directory B).

---

## Key Features

### 1. 🚀 4-Stage Progressive Elimination Pipeline
*"Use all the common and uncommon tools to check files are identical. Only use the ones that are required, don't use them all if they are not needed."*

DuoPty achieves maximum scanning speed and 100% mathematical accuracy by applying a progressive filter where heavy I/O is only executed when strictly necessary:

1. **Stage 1: Instant File Size Grouping (Metadata Check)**
   - Files with unique sizes across the scan are instantly eliminated with **zero disk reads**.
2. **Stage 2: 3-Point Sample Hashing (~12 KB Read)**
   - For files with matching size, reads 4KB header, 4KB middle, and 4KB footer.
   - Non-identical files (e.g., videos or archives of identical size with different content) are filtered out without reading gigabytes of data.
3. **Stage 3: Full Cryptographic Streaming Hash**
   - Full content hash using configurable algorithms: **SHA-256** (default), **BLAKE2b** (high-speed), **MD5**, or **SHA-1**.
   - Streamed in 64 KB chunks with live progress and cancel/pause support.
4. **Stage 4: Exact Byte-by-Byte Binary Stream Verification**
   - Pairwise binary comparison (`b1 == b2`) verifying absolute byte-level equality.
   - Eliminates any theoretical hash collision risk. **Only runs on files that survived Stages 1, 2, and 3.**

---

### 2. 📁 Dual Scanning Modes
- **Combined Mode**: Scans one, two, or multiple directories together to find any duplicate files anywhere.
- **Cross-Folder Comparison**: Compares **Folder 1 vs Folder 2**. Specifically identifies files in Folder 2 that already exist in Folder 1 (perfect for cleaning mirrors, external drives, or backup folders).

---

### 3. 🛡️ Safe Deletion to Windows Recycle Bin
- **Native Windows Recycle Bin**: By default, files are sent to the Windows Recycle Bin (`SHFileOperationW` Shell API), allowing full recovery and undo directly from Windows Explorer.
- **Permanent Delete Option**: Available via checkbox for users who wish to bypass the Recycle Bin.
- **Accidental Deletion Prevention**: If a user selects *all* copies in a duplicate group, DuoPty alerts them with a warning to prevent total data loss.

---

### 4. 🎛️ Modern, Intuitive GUI
- **High-DPI Support**: Crystal clear Segoe UI typography and scaling on Windows 10/11.
- **Checkbox Treeview**: Duplicate groups are organized hierarchically with group headers, sizes, and reclaimable space.
- **Smart Select Helpers**:
  - `Keep Oldest (Select Newer)`: Retains the original file and selects all newer copies for deletion.
  - `Keep Newest (Select Older)`: Retains the most recently modified copy.
  - `Keep First (Select Rest)`: Retains the first encountered file.
  - `Select All in Folder 2`: Selects all duplicates found in the secondary folder.
  - `Select All / Deselect All / Invert`
- **Right-Click Context Menu**:
  - *Open File* (using default Windows app)
  - *Reveal in File Explorer*
  - *Copy Full Path*
- **Export Reports**: Export findings to **CSV** or **JSON** formats.

---

## Running the Application

### Option 1: Double-click Batch File
Simply double-click [`run.bat`](file:///e:/pycode/duopty/run.bat) in the project folder to start the application immediately.

### Option 2: Command Line
Ensure Python 3 is installed, then run:

```bash
python main.py
```

### Optional Command-Line Arguments
You can also launch DuoPty with pre-selected folders or pass them to `run.bat`:

```bash
run.bat "C:\Path\To\Folder1" "D:\Path\To\Folder2" --mode cross_dir
# or:
python main.py "C:\Path\To\Folder1" "D:\Path\To\Folder2" --mode cross_dir
```

---

## Running Tests

DuoPty includes a comprehensive test suite covering all tiers of the detection engine and deletion safety:

```bash
python -m unittest discover tests
```

---

## Project Structure

```
duopty/
├── duopty/
│   ├── models.py        # FileInfo, DuplicateGroup, ScanConfig, ScanProgress, ScanStats
│   ├── scanner.py        # DuplicateScanner with 4-stage progressive pipeline & cancel/pause
│   ├── cache.py          # HashCache: persists hashes across scans, keyed by path/size/mtime
│   ├── deleter.py        # FileDeleter, DeleteResult, Recycle Bin & permanent deletion
│   ├── gui.py            # DuoPtyGUI & DeletionProgressDialog (Tkinter GUI)
│   ├── theme.py          # Modern dark palette, ttk styles, DPI awareness
│   └── utils.py          # File size formatting and helpers
├── tests/                 # Unit and integration test suite
├── docs/                  # Implementation plans, walkthroughs, and architecture docs
├── .github/workflows/     # CI (runs the test suite on windows-latest)
├── main.py                # Application entrypoint
└── run.bat                # Windows batch file launcher
```

---

## Documentation & Developer Guide

- **[System Architecture](docs/ARCHITECTURE.md)**: Details on the 4-stage detection pipeline, safe deletion engine, and concurrency model.
- **[Documentation Index](docs/INDEX.md)**: Links to implementation plans and verification walkthroughs.
- **[AGENTS.md](AGENTS.md)**: Developer instructions and project conventions for Claude Code and other coding agents.
