# DuoPty - Intelligent Duplicate File Scanner & Remover
## Phase 1: Initial Implementation Plan

A comprehensive, high-performance Python application with a modern GUI to scan single or multiple directories (and compare Directory A vs Directory B) for duplicate files. It uses an optimized progressive filtering pipeline ("common and uncommon tools") to only perform expensive disk and cryptographic operations when necessary, with interactive duplicate inspection, smart selection helpers, and safe deletion to the Windows Recycle Bin.

---

## Architecture & Detection Pipeline

**Design Philosophy**: *"Use all the common and uncommon tools to check files are identical. Only use the ones that are required, don't use them all if they are not needed."*

We implement a **4-Stage Progressive Elimination Pipeline**:

```
[ All Candidate Files in Selected Directories ]
                     │
                     ▼  (Phase 1: Metadata Filter)
  [ Stage 1: File Size Grouping (Common & Instant) ]
  • Unique sizes are immediately eliminated without any disk reads.
  • Files with identical sizes are grouped together.
                     │
                     ▼  (Phase 2: Quick Sample Verification)
  [ Stage 2: Head/Mid/Tail Partial Hashes (Common & Fast) ]
  • Reads small 4KB blocks (header, middle, footer).
  • If partial hashes differ, files are guaranteed different — skip full read.
                     │
                     ▼  (Phase 3: Cryptographic Full Hashes)
  [ Stage 3: Full Stream Hashing (Common & Robust) ]
  • Configurable: SHA-256 (default), BLAKE2b, MD5, SHA-1.
  • Streamed in 64KB/1MB chunks with progress reporting.
                     │
                     ▼  (Phase 4: Binary Byte-by-Byte Verification)
  [ Stage 4: Byte-by-Byte Exact Binary Comparison (Uncommon & 100% Definitive) ]
  • Direct pairwise chunk-by-chunk binary stream check (buffer matching).
  • Guards against any theoretical hash collisions or hash skepticism.
  • ONLY executed on files that passed all 3 previous stages!
```

---

## User Review & Key Design Decisions

- **Platform & Deletion Safety**: By default, deletions target the **Windows Recycle Bin** via the native Windows Shell API (`SHFileOperationW`), ensuring users can easily restore any accidentally removed file from Windows Explorer. An option for permanent deletion with confirmation is also provided.
- **Single vs Dual Directory Modes**:
  1. **Combined / Intra-Directory Mode**: Scans one or more directories to find any duplicates anywhere among them.
  2. **Cross-Folder Comparison (Dir A vs Dir B)**: Flags duplicates found in Directory B that already exist in Directory A (ideal for cleaning backup or mirror folders).

---

## Project Structure

```
duopty/
├── duopty/
│   ├── __init__.py
│   ├── scanner.py          # 4-stage progressive duplicate detection engine
│   ├── deleter.py          # Safe Windows Recycle Bin & permanent deletion handler
│   ├── models.py           # Data structures (FileInfo, DuplicateGroup, ScanConfig, ScanStats)
│   ├── gui.py              # Tkinter/ttk modern GUI with High-DPI support
│   ├── theme.py            # Modern color palette, styles, custom checkbox treeview
│   └── utils.py            # Formatting & system helpers
├── tests/
│   ├── __init__.py
│   ├── test_scanner.py     # Unit tests for multi-stage duplicate detection
│   └── test_deleter.py     # Unit tests for deletion safety & group preservation
├── main.py                 # Application launcher
└── README.md               # User guide & documentation
```

---

## Detailed Components

### 1. `duopty/models.py`
- `FileInfo`: `path`, `size`, `mtime`, `dir_id`, `partial_hash`, `full_hash`
- `DuplicateGroup`: `group_id`, `size`, `hash`, `files: List[FileInfo]`
- `ScanConfig`:
  - `folders`: List of folder paths (Dir 1, Dir 2, or more)
  - `mode`: `"combined"` vs `"cross_dir"` (Dir A vs Dir B)
  - `depth`: `"strict"` (Size + Partial + Full Hash + Byte check), `"standard"` (Size + Partial + Full Hash), `"quick"` (Size + Partial Hash), `"name_and_size"`
  - `hash_algo`: `"sha256"`, `"blake2b"`, `"md5"`, `"sha1"`
  - `min_size`: Minimum file size (default: 1 byte, ignores empty files if set)
  - `max_size`: Maximum file size (optional)
  - `include_exts` / `exclude_exts`: File extension filtering
  - `ignore_hidden`: Ignore hidden files and dot-folders
  - `follow_symlinks`: False by default

### 2. `duopty/scanner.py`
- Multi-stage worker engine executing in a background thread.
- Progress callbacks providing: `phase_name`, `percent`, `current_file`, `items_processed`, `duplicates_found`.
- Progressive stage skips:
  - If a file is alone in its size bucket -> immediately discarded.
  - If files in size bucket differ in sample hash -> immediately discarded.
  - Full hash is only calculated for files surviving stages 1 & 2.
  - Byte-by-byte comparison is only performed on files surviving stage 3.
- Thread-safe cancellation and pause/resume.

### 3. `duopty/deleter.py`
- Native Windows Recycle Bin deletion using `ctypes.windll.shell32.SHFileOperationW` with `FOF_ALLOWUNDO`.
- Permanent deletion option (`os.remove`).
- Group safety validator: Prevents deleting *all* copies in a duplicate group unless explicitly forced by the user.

### 4. `duopty/gui.py` & `duopty/theme.py`
- High-DPI scaling enabled (`SetProcessDpiAwareness`).
- Modern UI layout:
  - **Top Panel**: Folder selectors (Folder 1, Folder 2, Browse buttons, Mode toggle: Combined vs Compare A to B).
  - **Options Accordion/Bar**: Depth of scan, hash algorithm, min/max file size, extension filters, ignore hidden/empty.
  - **Progress Bar & Status**: Real-time phase description, progress bar, current file scanned, stop/start buttons.
  - **Results Table (Custom Checkbox Treeview)**:
    - Displays collapsible duplicate groups.
    - Group header: Group #, duplicate count, file size, space reclaimable.
    - Child items: [x] Checkbox, File Name, Folder/Directory, Size, Modified Date.
  - **Smart Selection Toolbar**:
    - "Select All Except Newest"
    - "Select All Except Oldest"
    - "Select All Except First"
    - "Select All in Folder B"
    - "Select All / Deselect All / Invert"
  - **Action Bar**:
    - Status: "Selected: X files (Y MB)"
    - Recycle Bin toggle (Safe delete vs Permanent delete)
    - "Delete Selected" button with confirmation modal showing preview of files to remove.
    - "Export Report" button (CSV / TXT / JSON).

---

## Verification Plan

### Automated Tests
- Run `unittest` on `tests/test_scanner.py` and `tests/test_deleter.py`:
  - Test exact duplicate files are detected.
  - Test files with same size but different content are rejected at sample hash stage.
  - Test files with same size, same prefix, but different end are rejected at full hash stage.
  - Test cross-directory comparison mode (Dir A vs Dir B).
  - Test deletion safety guard (cannot delete all copies without warning).
- Command: `python -m unittest discover tests`

### Manual & Interactive Verification
- Launch GUI via `python main.py`.
- Create a test directory structure with synthetic duplicate files of various sizes, identical contents, different timestamps, and different names.
- Perform scans with different depths (Strict vs Standard vs Quick).
- Test smart selection buttons (Keep Newest, Keep Oldest, Keep First).
- Test sending duplicate to Recycle Bin and verifying the file appears in the Windows Recycle Bin.
