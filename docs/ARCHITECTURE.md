# DuoPty — Architectural Design Document

DuoPty is a high-performance desktop duplicate file manager designed for Windows 10/11. It combines a progressive multi-tiered duplicate detection algorithm with safe deletion mechanisms and a responsive GUI.

---

## 1. System Overview

```
                      ┌──────────────────────┐
                      │      main.py         │
                      │  (CLI / GUI Launcher)│
                      └──────────┬───────────┘
                                 │
                                 ▼
                      ┌──────────────────────┐
                      │    duopty/gui.py     │
                      │ (Tkinter/ttk Window) │
                      └────┬────────────┬────┘
                           │            │
             (Background Worker)   (Background Worker)
                           │            │
                           ▼            ▼
                 ┌───────────────┐  ┌────────────────┐
                 │duopty/        │  │duopty/         │
                 │scanner.py     │  │deleter.py      │
                 │(Scan Engine)  │  │(Shell / Delete)│
                 └───────┬───────┘  └───────┬────────┘
                         │                  │
                         └────────┬─────────┘
                                  │
                                  ▼
                        ┌──────────────────┐
                        │ duopty/models.py │
                        │  (Data Entities) │
                        └──────────────────┘
```

---

## 2. 4-Stage Progressive Elimination Pipeline (`duopty/scanner.py`)

Duplicate file scanning is often bottlenecked by disk I/O and cryptographic hashing. DuoPty implements a strict early-rejection pipeline to guarantee that expensive operations are only performed when mathematically necessary.

| Stage | Operation | Cost | Elimination Rate |
|---|---|---|---|
| **Stage 1: File Size** | `os.stat().st_size` | ~0 ms / file (Metadata only) | ~90-98% of unique files discarded with 0 disk read. |
| **Stage 2: 3-Point Sample Hash** | Reads 4 KB head, 4 KB mid, 4 KB tail (~12 KB total) | 3 seek/read operations | Eliminates non-identical media, ISOs, archives of identical size. |
| **Stage 3: Full Cryptographic Hash** | Streaming hash (SHA-256, BLAKE2b, MD5, SHA-1) in 64 KB blocks | Full file read (sequential) | Cryptographically distinguishes almost all collisions. |
| **Stage 4: Binary Byte-by-Byte Stream** | Pairwise chunk comparison (`b1 == b2`) | Pairwise stream comparison | Guarantees 100% mathematical certainty against theoretical hash collisions. |

---

## 3. Safe Deletion & Concurrency Architecture (`duopty/deleter.py`, `duopty/gui.py`)

### Deletion Safety Tiers
1. **Windows Recycle Bin (Default)**:
   - Utilizes `ctypes.windll.shell32.SHFileOperationW` with `FOFO_ALLOWUNDO`.
   - Allows users to restore deleted files from the Windows desktop Recycle Bin.
2. **Permanent Deletion**:
   - Clears `stat.S_IWRITE` before invoking `os.remove` to ensure read-only files delete cleanly without Windows Access Denied (`WinError 5`) errors.
   - Prepends `\\?\` extended path prefix for paths >= 260 characters.
3. **Safety Guard (`verify_group_safety`)**:
   - Detects if a user attempts to select *all* copies in a duplicate group and blocks deletion unless explicitly confirmed.

### Concurrency & Threading Model
- Tkinter's event loop (`root.mainloop()`) must never be blocked by disk I/O.
- Long operations (`ScanEngine.scan()` and `FileDeleter.delete_files()`) execute in dedicated background daemon threads.
- GUI synchronization:
  - Background workers report progress via callbacks throttled to ~20 Hz.
  - Progress updates post to Tkinter via `root.after_idle()` or `root.after()`.
  - A modal `DeletionProgressDialog` provides visual feedback with a responsive `"Cancel"` button.
  - Treeview data models are pruned using the `DeleteResult.deleted_paths` set directly, avoiding thousands of synchronous `os.path.exists()` disk calls.

---

## 4. Module Map

- **`duopty/models.py`**:
  - `FileInfo`: Metadata and hash tracking for individual files.
  - `DuplicateGroup`: Holds matched duplicate files and calculates reclaimable space.
  - `ScanConfig`: Configuration parameters (folders, mode, depth, filters, hash algorithm).
  - `ScanProgress` & `ScanStats`: State and performance metrics.
- **`duopty/scanner.py`**:
  - `ScanEngine`: Coordinates directory crawling, progressive filtering, cancel, pause/resume.
- **`duopty/deleter.py`**:
  - `FileDeleter`: Windows Shell Recycle Bin and permanent deletion.
  - `DeleteResult`: Encapsulates deleted count, errors, freed bytes, and cancellation status.
- **`duopty/gui.py`**:
  - `DuoPtyApp`: Main window, controls, and event handlers.
  - `DeletionProgressDialog`: Modal progress and cancellation dialog for deletion.
- **`duopty/theme.py`**:
  - Dark theme color tokens, ttk styles, DPI awareness initialization.
- **`duopty/utils.py`**:
  - Formatting utilities (human-readable bytes, time, path display).
