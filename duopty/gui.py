import os
import sys
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List, Dict, Optional, Set
import csv
import json
import time

from duopty.models import FileInfo, DuplicateGroup, ScanConfig, ScanProgress, ScanStats
from duopty.scanner import DuplicateScanner
from duopty.deleter import FileDeleter, DeleteResult
from duopty.utils import format_size, format_timestamp, reveal_in_explorer, open_file_default_app
from duopty.theme import (
    apply_theme, BG_MAIN, BG_SURFACE, BG_INPUT, TEXT_WHITE, TEXT_PRIMARY,
    TEXT_DIM, ACCENT_PRIMARY, ACCENT_GREEN, ACCENT_RED, ACCENT_PURPLE,
    FONT_MAIN, FONT_BOLD, FONT_HEADING, FONT_TITLE, FONT_MONO
)


CHECK_CHAR = "☑"
UNCHECK_CHAR = "☐"


class DeletionProgressDialog(tk.Toplevel):
    """Modal dialog displaying real-time deletion progress with cancellation support."""

    def __init__(self, parent: tk.Tk, total_files: int, to_recycle: bool):
        super().__init__(parent)
        self.title("Deleting Duplicate Files")
        self.configure(bg=BG_SURFACE)
        self.geometry("520x240")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Center over parent window
        self.update_idletasks()
        try:
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            w = 520
            h = 240
            x = px + max(0, (pw - w) // 2)
            y = py + max(0, (ph - h) // 2)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

        self.cancelled = False
        self.total_files = total_files

        # Frame container
        frame = ttk.Frame(self, style="Surface.TFrame", padding=16)
        frame.pack(fill="both", expand=True)

        # Header
        dest_text = "Windows Recycle Bin" if to_recycle else "Permanent Deletion"
        dest_color = ACCENT_PRIMARY if to_recycle else ACCENT_RED

        header_frame = ttk.Frame(frame, style="Surface.TFrame")
        header_frame.pack(fill="x", pady=(0, 8))

        lbl_title = ttk.Label(header_frame, text="🗑 Deleting Duplicate Files...", style="Heading.TLabel")
        lbl_title.pack(side="left")

        lbl_dest = tk.Label(
            header_frame,
            text=f"[{dest_text}]",
            bg=BG_SURFACE,
            fg=dest_color,
            font=FONT_BOLD
        )
        lbl_dest.pack(side="right")

        # Progress count label
        self.count_label = ttk.Label(
            frame,
            text=f"Preparing deletion of {total_files} file(s)...",
            style="Surface.TLabel",
            font=FONT_BOLD
        )
        self.count_label.pack(anchor="w", pady=(4, 2))

        # Current file path label
        self.file_label = ttk.Label(
            frame,
            text="",
            style="Muted.TLabel"
        )
        self.file_label.pack(anchor="w", pady=(0, 8))

        # Progressbar
        self.progress_bar = ttk.Progressbar(
            frame,
            orient="horizontal",
            mode="determinate",
            maximum=100
        )
        self.progress_bar.pack(fill="x", pady=(0, 16))

        # Bottom button
        btn_box = ttk.Frame(frame, style="Surface.TFrame")
        btn_box.pack(fill="x")

        self.btn_cancel = ttk.Button(
            btn_box,
            text="⏹ Cancel",
            command=self._request_cancel
        )
        self.btn_cancel.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._request_cancel)

    def _truncate_path(self, path: str, max_len: int = 58) -> str:
        """Truncates middle of file path for clean single-line display."""
        if len(path) <= max_len:
            return path
        half = (max_len - 3) // 2
        return path[:half] + "..." + path[-half:]

    def update_progress(self, current: int, total: int, filepath: str):
        """Updates progress bar and label text smoothly."""
        if not self.winfo_exists():
            return
        pct = (current / max(1, total)) * 100.0
        self.progress_bar.configure(value=pct)
        self.count_label.configure(text=f"Deleting file {current} of {total} ({pct:.1f}%)...")
        self.file_label.configure(text=self._truncate_path(filepath))

    def _request_cancel(self):
        """Signals background thread to stop deletion."""
        if not self.cancelled:
            self.cancelled = True
            self.btn_cancel.configure(text="Cancelling...", state="disabled")
            self.count_label.configure(text="Cancelling deletion, finishing current file...")

    def is_cancelled(self) -> bool:
        return self.cancelled


class DuoPtyGUI:
    """Main Application GUI for DuoPty."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("DuoPty — Intelligent Duplicate File Scanner & Remover")
        self.root.geometry("1180x820")
        self.root.minsize(980, 680)

        # Apply high-DPI scaling on Windows
        self._enable_high_dpi()

        # Apply theme
        apply_theme(self.root)

        # State variables
        self.folder1_var = tk.StringVar(value="")
        self.folder2_var = tk.StringVar(value="")
        self.scan_mode_var = tk.StringVar(value="combined")  # 'combined' or 'cross_dir'
        self.additional_folders: List[str] = []

        self.depth_var = tk.StringVar(value="strict")
        self.hash_algo_var = tk.StringVar(value="sha256")
        self.min_size_var = tk.StringVar(value="1 Byte (Skip 0-byte)")
        self.ignore_hidden_var = tk.BooleanVar(value=True)
        self.include_exts_var = tk.StringVar(value="")
        self.exclude_exts_var = tk.StringVar(value="")
        self.recycle_bin_var = tk.BooleanVar(value=True)
        self.use_cache_var = tk.BooleanVar(value=True)

        self.scanner_thread: Optional[threading.Thread] = None
        self.scanner: Optional[DuplicateScanner] = None
        self.event_queue: queue.Queue = queue.Queue()
        self.is_scanning = False
        self.is_paused = False

        self.duplicate_groups: List[DuplicateGroup] = []
        # Maps tree item ID to (DuplicateGroup, Optional[FileInfo])
        self.tree_item_map: Dict[str, tuple] = {}

        self._build_ui()
        self._setup_context_menu()
        self._start_queue_listener()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _enable_high_dpi(self):
        """Enables crisp high-DPI font rendering on Windows."""
        if sys.platform == "win32":
            try:
                import ctypes
                try:
                    ctypes.windll.shcore.SetProcessDpiAwareness(1)
                except Exception:
                    ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    def _build_ui(self):
        """Constructs the complete application layout."""
        # Top banner
        header_frame = ttk.Frame(self.root, padding=(16, 12, 16, 8))
        header_frame.pack(fill="x")

        title_lbl = ttk.Label(header_frame, text="DuoPty Duplicate File Scanner", style="Title.TLabel")
        title_lbl.pack(anchor="w")
        sub_lbl = ttk.Label(
            header_frame,
            text="Multi-tiered progressive elimination duplicate finder with safe Windows Recycle Bin removal",
            style="Muted.TLabel"
        )
        sub_lbl.pack(anchor="w", pady=(2, 0))

        # Main content container
        content_frame = ttk.Frame(self.root, padding=(16, 4, 16, 12))
        content_frame.pack(fill="both", expand=True)

        # Top Section: Folder Selection & Configuration Card
        top_card = ttk.LabelFrame(content_frame, text=" 📁 Scan Targets & Detection Configuration ", padding=12)
        top_card.pack(fill="x", pady=(0, 8))

        self._build_folder_inputs(top_card)
        self._build_options_bar(top_card)

        # Middle Section: Progress & Controls Card
        control_card = ttk.LabelFrame(content_frame, text=" ⚡ Scan Progress & Controls ", padding=10)
        control_card.pack(fill="x", pady=(0, 8))
        self._build_control_panel(control_card)

        # Bottom Section: Results Table & Smart Actions
        results_card = ttk.LabelFrame(content_frame, text=" 📋 Duplicate Groups & File Removal ", padding=8)
        results_card.pack(fill="both", expand=True)
        self._build_results_panel(results_card)

        # Bottom Action Bar
        self._build_bottom_action_bar(content_frame)

    def _build_folder_inputs(self, parent: ttk.LabelFrame):
        """Builds directory picker rows."""
        grid = ttk.Frame(parent, style="Surface.TFrame")
        grid.pack(fill="x", pady=(0, 8))
        grid.columnconfigure(1, weight=1)

        # Folder 1
        ttk.Label(grid, text="Folder 1 (Primary):", style="Surface.TLabel", font=FONT_BOLD).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        f1_entry = ttk.Entry(grid, textvariable=self.folder1_var)
        f1_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8), pady=3)
        ttk.Button(grid, text="Browse...", command=lambda: self._browse_folder(self.folder1_var)).grid(row=0, column=2, padx=2, pady=3)

        # Folder 2
        ttk.Label(grid, text="Folder 2 (Optional):", style="Surface.TLabel", font=FONT_BOLD).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        f2_entry = ttk.Entry(grid, textvariable=self.folder2_var)
        f2_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=3)
        ttk.Button(grid, text="Browse...", command=lambda: self._browse_folder(self.folder2_var)).grid(row=1, column=2, padx=2, pady=3)
        ttk.Button(grid, text="Clear", command=lambda: self.folder2_var.set("")).grid(row=1, column=3, padx=(4, 0), pady=3)

        # Mode Selection Row
        mode_frame = ttk.Frame(parent, style="Surface.TFrame")
        mode_frame.pack(fill="x", pady=(4, 6))

        ttk.Label(mode_frame, text="Scan Mode:", style="Surface.TLabel", font=FONT_BOLD).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(
            mode_frame,
            text="Combined Mode (Find all duplicates across selected folders)",
            variable=self.scan_mode_var,
            value="combined"
        ).pack(side="left", padx=(0, 16))

        ttk.Radiobutton(
            mode_frame,
            text="Cross-Folder Comparison (Find files in Folder 2 that already exist in Folder 1)",
            variable=self.scan_mode_var,
            value="cross_dir"
        ).pack(side="left")

        ttk.Button(
            mode_frame,
            text="+ More Folders...",
            command=self._open_more_folders_dialog
        ).pack(side="right")

    def _build_options_bar(self, parent: ttk.LabelFrame):
        """Builds scanner options and filters."""
        opts_frame = ttk.Frame(parent, style="Surface.TFrame")
        opts_frame.pack(fill="x", pady=(4, 0))

        # Row 1 of options
        r1 = ttk.Frame(opts_frame, style="Surface.TFrame")
        r1.pack(fill="x", pady=2)

        ttk.Label(r1, text="Comparison Depth:", style="Surface.TLabel").pack(side="left", padx=(0, 6))
        depth_combo = ttk.Combobox(
            r1,
            textvariable=self.depth_var,
            values=[
                "strict",
                "standard",
                "quick",
                "name_size"
            ],
            state="readonly",
            width=12
        )
        depth_combo.pack(side="left", padx=(0, 16))

        # Tooltip explanation
        depth_hint = ttk.Label(
            r1,
            text="(Strict = Size + Sample + Hash + Byte-by-Byte | Standard = Hash | Quick = Sample)",
            style="Muted.TLabel"
        )
        depth_hint.pack(side="left", padx=(0, 20))

        ttk.Label(r1, text="Hash Algorithm:", style="Surface.TLabel").pack(side="left", padx=(0, 6))
        algo_combo = ttk.Combobox(
            r1,
            textvariable=self.hash_algo_var,
            values=["sha256", "blake2b", "md5", "sha1"],
            state="readonly",
            width=10
        )
        algo_combo.pack(side="left", padx=(0, 16))

        # Row 2 of options (Filters)
        r2 = ttk.Frame(opts_frame, style="Surface.TFrame")
        r2.pack(fill="x", pady=(6, 2))

        ttk.Label(r2, text="Min File Size:", style="Surface.TLabel").pack(side="left", padx=(0, 6))
        size_combo = ttk.Combobox(
            r2,
            textvariable=self.min_size_var,
            values=[
                "1 Byte (Skip 0-byte)",
                "0 Bytes (Include empty)",
                "1 KB",
                "100 KB",
                "1 MB",
                "10 MB"
            ],
            state="readonly",
            width=19
        )
        size_combo.pack(side="left", padx=(0, 16))

        ttk.Checkbutton(
            r2,
            text="Ignore hidden/system files",
            variable=self.ignore_hidden_var
        ).pack(side="left", padx=(0, 16))

        ttk.Label(r2, text="Include Exts (e.g. .jpg, .png):", style="Surface.TLabel").pack(side="left", padx=(0, 6))
        ext_entry = ttk.Entry(r2, textvariable=self.include_exts_var, width=18)
        ext_entry.pack(side="left", padx=(0, 12))

        ttk.Checkbutton(
            r2,
            text="Use hash cache (faster rescans)",
            variable=self.use_cache_var
        ).pack(side="left", padx=(0, 8))

        ttk.Button(r2, text="Clear Cache", command=self._clear_hash_cache).pack(side="left")

    def _build_control_panel(self, parent: ttk.LabelFrame):
        """Builds the progress bar, scan start/stop buttons, and status labels."""
        ctrl_frame = ttk.Frame(parent, style="Surface.TFrame")
        ctrl_frame.pack(fill="x")

        # Buttons
        btn_frame = ttk.Frame(ctrl_frame, style="Surface.TFrame")
        btn_frame.pack(side="left", padx=(0, 16))

        self.btn_start = ttk.Button(btn_frame, text="▶ Start Scan", style="Primary.TButton", command=self._start_scan)
        self.btn_start.pack(side="left", padx=(0, 6))

        self.btn_pause = ttk.Button(btn_frame, text="⏸ Pause", command=self._toggle_pause, state="disabled")
        self.btn_pause.pack(side="left", padx=(0, 6))

        self.btn_cancel = ttk.Button(btn_frame, text="⏹ Cancel", command=self._cancel_scan, state="disabled")
        self.btn_cancel.pack(side="left")

        # Progress and Status Area
        status_frame = ttk.Frame(ctrl_frame, style="Surface.TFrame")
        status_frame.pack(side="left", fill="x", expand=True)

        self.phase_label = ttk.Label(status_frame, text="Ready to scan.", style="Accent.TLabel")
        self.phase_label.pack(anchor="w")

        self.progress_bar = ttk.Progressbar(status_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill="x", pady=(4, 4))

        self.detail_label = ttk.Label(
            status_frame,
            text="Select folder(s) above and click Start Scan.",
            style="Muted.TLabel"
        )
        self.detail_label.pack(anchor="w")

    def _build_results_panel(self, parent: ttk.LabelFrame):
        """Builds the Treeview for displaying duplicate groups with checkbox selection."""
        # Smart selection bar
        sel_bar = ttk.Frame(parent, style="Surface.TFrame")
        sel_bar.pack(fill="x", pady=(0, 6))

        ttk.Label(sel_bar, text="Smart Select:", style="Surface.TLabel", font=FONT_BOLD).pack(side="left", padx=(0, 8))

        ttk.Button(sel_bar, text="Keep Oldest (Select Newer)", command=lambda: self._smart_select("keep_oldest")).pack(side="left", padx=2)
        ttk.Button(sel_bar, text="Keep Newest (Select Older)", command=lambda: self._smart_select("keep_newest")).pack(side="left", padx=2)
        ttk.Button(sel_bar, text="Keep First (Select Rest)", command=lambda: self._smart_select("keep_first")).pack(side="left", padx=2)
        ttk.Button(sel_bar, text="Select All in Folder 2", command=lambda: self._smart_select("folder2")).pack(side="left", padx=2)

        ttk.Separator(sel_bar, orient="vertical").pack(side="left", fill="y", padx=8)

        ttk.Button(sel_bar, text="Select All", command=lambda: self._select_all(True)).pack(side="left", padx=2)
        ttk.Button(sel_bar, text="Deselect All", command=lambda: self._select_all(False)).pack(side="left", padx=2)
        ttk.Button(sel_bar, text="Invert", command=self._invert_selection).pack(side="left", padx=2)

        # Treeview with scrollbars
        tree_container = ttk.Frame(parent)
        tree_container.pack(fill="both", expand=True)

        columns = ("name", "directory", "size", "mtime", "origin")
        self.tree = ttk.Treeview(
            tree_container,
            columns=columns,
            selectmode="extended",
            show="tree headings"
        )

        self.tree.heading("#0", text="[Select]")
        self.tree.heading("name", text="File Name")
        self.tree.heading("directory", text="Folder Path")
        self.tree.heading("size", text="Size")
        self.tree.heading("mtime", text="Modified Date")
        self.tree.heading("origin", text="Location")

        self.tree.column("#0", width=80, stretch=False, anchor="center")
        self.tree.column("name", width=220, anchor="w")
        self.tree.column("directory", width=380, anchor="w")
        self.tree.column("size", width=100, anchor="e")
        self.tree.column("mtime", width=150, anchor="center")
        self.tree.column("origin", width=90, anchor="center")

        # Configure custom row tags
        self.tree.tag_configure("group_header", background="#2a2e48", foreground=ACCENT_PURPLE, font=FONT_BOLD)
        self.tree.tag_configure("checked", foreground=ACCENT_RED)
        self.tree.tag_configure("unchecked", foreground=TEXT_PRIMARY)

        # Scrollbars
        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        # Tree events
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<space>", self._on_tree_space)

    def _build_bottom_action_bar(self, parent: ttk.Frame):
        """Builds bottom bar with selection summary and action buttons."""
        bar = ttk.Frame(parent, padding=(4, 8, 4, 0))
        bar.pack(fill="x")

        # Stats label on left
        self.stats_label = ttk.Label(
            bar,
            text="Duplicates: 0 groups (0 files) | Selected: 0 files (0 B to free)",
            style="Surface.TLabel",
            font=FONT_BOLD
        )
        self.stats_label.pack(side="left", padx=4)

        # Right actions
        self.btn_delete = ttk.Button(
            bar,
            text="🗑 Delete Selected Files",
            style="Danger.TButton",
            command=self._confirm_and_delete
        )
        self.btn_delete.pack(side="right", padx=(8, 0))

        self.btn_export = ttk.Button(
            bar,
            text="📥 Export Report...",
            command=self._export_report
        )
        self.btn_export.pack(side="right", padx=(8, 0))

        ttk.Checkbutton(
            bar,
            text="Move to Windows Recycle Bin (Safe)",
            variable=self.recycle_bin_var
        ).pack(side="right", padx=(0, 12))

    def _setup_context_menu(self):
        """Creates right-click popup menu for files in results."""
        self.context_menu = tk.Menu(self.root, tearoff=0, bg=BG_SURFACE, fg=TEXT_WHITE, activebackground=BG_INPUT)
        self.context_menu.add_command(label="Toggle Selection (Space)", command=self._toggle_selected_item)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Open File", command=self._context_open_file)
        self.context_menu.add_command(label="Reveal in File Explorer", command=self._context_reveal_explorer)
        self.context_menu.add_command(label="Copy Full Path", command=self._context_copy_path)

        self.tree.bind("<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event):
        """Shows right-click menu at cursor position."""
        item_id = self.tree.identify_row(event.y)
        if item_id:
            if item_id not in self.tree.selection():
                self.tree.selection_set(item_id)
            self.context_menu.post(event.x_root, event.y_root)

    def _browse_folder(self, target_var: tk.StringVar):
        """Opens native Windows folder picker dialog."""
        folder = filedialog.askdirectory(parent=self.root, title="Select Directory to Scan")
        if folder:
            target_var.set(os.path.normpath(folder))

    def _open_more_folders_dialog(self):
        """Dialog to add multiple directories."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Manage Scan Folders")
        dlg.geometry("550x380")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.configure(bg=BG_MAIN)

        ttk.Label(dlg, text="Additional Scan Folders:", style="Heading.TLabel").pack(anchor="w", padx=16, pady=12)

        list_frame = ttk.Frame(dlg)
        list_frame.pack(fill="both", expand=True, padx=16)

        folder_listbox = tk.Listbox(list_frame, bg=BG_INPUT, fg=TEXT_WHITE, font=FONT_MAIN, selectbackground="#364a82")
        folder_listbox.pack(side="left", fill="both", expand=True)

        for f in self.additional_folders:
            folder_listbox.insert("end", f)

        btn_box = ttk.Frame(dlg, padding=16)
        btn_box.pack(fill="x")

        def add_dir():
            f = filedialog.askdirectory(parent=dlg, title="Select Directory")
            if f and f not in self.additional_folders:
                self.additional_folders.append(os.path.normpath(f))
                folder_listbox.insert("end", os.path.normpath(f))

        def remove_dir():
            sel = folder_listbox.curselection()
            if sel:
                idx = sel[0]
                self.additional_folders.pop(idx)
                folder_listbox.delete(idx)

        ttk.Button(btn_box, text="+ Add Directory", command=add_dir).pack(side="left", padx=(0, 8))
        ttk.Button(btn_box, text="Remove Selected", command=remove_dir).pack(side="left")
        ttk.Button(btn_box, text="Done", command=dlg.destroy).pack(side="right")

    def _clear_hash_cache(self):
        """Discards the persisted hash cache used to speed up rescans."""
        from duopty.cache import HashCache
        cache = HashCache()
        entries = len(cache)
        cache.clear()
        messagebox.showinfo(
            "Cache Cleared",
            f"Removed {entries} cached hash entr{'y' if entries == 1 else 'ies'}.",
            parent=self.root
        )

    def _get_min_size_bytes(self) -> int:
        """Parses user min size combobox selection."""
        val = self.min_size_var.get()
        if "0 Bytes" in val:
            return 0
        if "1 Byte" in val:
            return 1
        if "1 KB" in val:
            return 1024
        if "100 KB" in val:
            return 100 * 1024
        if "1 MB" in val:
            return 1024 * 1024
        if "10 MB" in val:
            return 10 * 1024 * 1024
        try:
            return int(val)
        except ValueError:
            return 1

    def _parse_extensions(self, raw: str) -> Set[str]:
        """Parses comma/space separated extension string into a normalized set."""
        exts = set()
        for token in raw.replace(",", " ").split():
            token = token.strip().lower()
            if token:
                if not token.startswith("."):
                    token = "." + token
                exts.add(token)
        return exts

    def _start_scan(self):
        """Prepares configuration and starts background scanner thread."""
        folders = []
        f1 = self.folder1_var.get().strip()
        f2 = self.folder2_var.get().strip()

        if f1 and os.path.isdir(f1):
            folders.append(f1)
        if f2 and os.path.isdir(f2):
            folders.append(f2)
        for af in self.additional_folders:
            if af and os.path.isdir(af) and af not in folders:
                folders.append(af)

        if not folders:
            messagebox.showwarning(
                "No Folders Selected",
                "Please select at least one valid folder to scan.",
                parent=self.root
            )
            return

        mode = self.scan_mode_var.get()
        if mode == "cross_dir" and len(folders) < 2:
            messagebox.showwarning(
                "Cross-Folder Mode Requires 2 Folders",
                "Cross-Folder comparison requires both Folder 1 and Folder 2 to be selected.",
                parent=self.root
            )
            return

        config = ScanConfig(
            folders=folders,
            mode=mode,
            depth=self.depth_var.get(),
            hash_algo=self.hash_algo_var.get(),
            min_size=self._get_min_size_bytes(),
            include_exts=self._parse_extensions(self.include_exts_var.get()),
            exclude_exts=self._parse_extensions(self.exclude_exts_var.get()),
            ignore_hidden=self.ignore_hidden_var.get(),
            use_cache=self.use_cache_var.get()
        )

        # Clear existing tree
        self.tree.delete(*self.tree.get_children())
        self.tree_item_map.clear()
        self.duplicate_groups.clear()
        self._update_stats_display()

        self.is_scanning = True
        self.is_paused = False
        self.btn_start.configure(state="disabled")
        self.btn_pause.configure(state="normal", text="⏸ Pause")
        self.btn_cancel.configure(state="normal")
        self.progress_bar.configure(value=0)

        self.scanner = DuplicateScanner(
            config=config,
            progress_callback=lambda prog: self.event_queue.put(("progress", prog))
        )

        def run_thread():
            try:
                results = self.scanner.scan()
                self.event_queue.put(("complete", results))
            except Exception as e:
                self.event_queue.put(("error", str(e)))

        self.scanner_thread = threading.Thread(target=run_thread, daemon=True)
        self.scanner_thread.start()

    def _toggle_pause(self):
        if not self.scanner or not self.is_scanning:
            return
        if self.is_paused:
            self.scanner.resume()
            self.is_paused = False
            self.btn_pause.configure(text="⏸ Pause")
            self.phase_label.configure(text="Resumed scanning...")
        else:
            self.scanner.pause()
            self.is_paused = True
            self.btn_pause.configure(text="▶ Resume")
            self.phase_label.configure(text="Paused.")

    def _cancel_scan(self):
        if self.scanner and self.is_scanning:
            self.scanner.cancel()
            self.phase_label.configure(text="Cancelling scan...")
            self.btn_cancel.configure(state="disabled")

    def _start_queue_listener(self):
        """Polls queue for scanner events and updates GUI smoothly."""
        try:
            while True:
                msg_type, payload = self.event_queue.get_nowait()
                if msg_type == "progress":
                    prog: ScanProgress = payload
                    self.phase_label.configure(text=prog.phase)
                    self.progress_bar.configure(value=prog.percentage)
                    self.detail_label.configure(
                        text=f"Files processed: {prog.files_scanned} | Duplicates: {prog.duplicates_found} | Reclaimable: {format_size(prog.potential_savings)}"
                    )
                elif msg_type == "complete":
                    results: List[DuplicateGroup] = payload
                    self._on_scan_completed(results)
                elif msg_type == "error":
                    self._on_scan_error(payload)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._start_queue_listener)

    def _on_scan_completed(self, groups: List[DuplicateGroup]):
        self.is_scanning = False
        self.is_paused = False
        self.btn_start.configure(state="normal")
        self.btn_pause.configure(state="disabled", text="⏸ Pause")
        self.btn_cancel.configure(state="disabled")
        self.progress_bar.configure(value=100)

        self.duplicate_groups = groups
        self._populate_tree(groups)
        self._update_stats_display()

        self.phase_label.configure(text=f"Scan Finished! Found {len(groups)} duplicate groups.")
        detail_text = f"Discovered {self.scanner.stats.total_files_discovered} files in {self.scanner.stats.scan_duration:.2f}s."
        read_errors = self.scanner.stats.read_errors
        if read_errors:
            detail_text += f" | {read_errors} file(s) skipped (could not be read)."
        self.detail_label.configure(text=detail_text)

        if not groups:
            msg = "No duplicate files were found matching your criteria."
            if read_errors:
                msg += f"\n\n{read_errors} file(s) could not be read (permission denied or in use) and were excluded from the scan."
            messagebox.showinfo("Scan Completed", msg, parent=self.root)
        elif read_errors:
            sample_lines = "\n".join(self.scanner.stats.error_samples[:5])
            more = f"\n... and {read_errors - 5} more." if read_errors > 5 else ""
            messagebox.showwarning(
                "Scan Completed with Warnings",
                f"{read_errors} file(s) could not be read (permission denied or in use) and were excluded:\n\n{sample_lines}{more}",
                parent=self.root
            )

    def _on_scan_error(self, err_msg: str):
        self.is_scanning = False
        self.btn_start.configure(state="normal")
        self.btn_pause.configure(state="disabled")
        self.btn_cancel.configure(state="disabled")
        self.phase_label.configure(text="Scan encountered an error.")
        messagebox.showerror("Scan Error", f"An error occurred during scanning:\n{err_msg}", parent=self.root)

    def _populate_tree(self, groups: List[DuplicateGroup]):
        """Populates the Treeview with duplicate groups and file items."""
        self.tree.delete(*self.tree.get_children())
        self.tree_item_map.clear()

        for group in groups:
            group_item_id = f"group_{group.group_id}"
            group_text = f"📁 Group #{group.group_id}  ({group.count} duplicates | {format_size(group.size)} each | Reclaimable: {format_size(group.space_reclaimable)})"

            self.tree.insert(
                "",
                "end",
                iid=group_item_id,
                text=UNCHECK_CHAR,
                values=(
                    group_text,
                    f"Hash: {group.hash_val[:16]}..." if group.hash_val else "",
                    format_size(group.size),
                    "",
                    f"{group.count} files"
                ),
                open=True,
                tags=("group_header",)
            )
            self.tree_item_map[group_item_id] = (group, None)

            # Insert file children
            for idx, file_info in enumerate(group.files):
                file_item_id = f"file_{group.group_id}_{idx}"
                chk = CHECK_CHAR if file_info.selected_for_deletion else UNCHECK_CHAR
                tag = "checked" if file_info.selected_for_deletion else "unchecked"
                loc = f"Folder {file_info.dir_index + 1}"

                self.tree.insert(
                    group_item_id,
                    "end",
                    iid=file_item_id,
                    text=chk,
                    values=(
                        file_info.filename,
                        file_info.directory,
                        format_size(file_info.size),
                        format_timestamp(file_info.mtime),
                        loc
                    ),
                    tags=(tag,)
                )
                self.tree_item_map[file_item_id] = (group, file_info)

    def _on_tree_click(self, event):
        """Handles single clicks on rows, toggling checkbox if clicked on icon column."""
        region = self.tree.identify_region(event.x, event.y)
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        # If click was in #0 (tree/checkbox column)
        if region in ("tree", "indicator"):
            self._toggle_checkbox(item_id)

    def _on_tree_double_click(self, event):
        """Double clicking a file opens it."""
        item_id = self.tree.identify_row(event.y)
        if item_id and item_id in self.tree_item_map:
            group, file_info = self.tree_item_map[item_id]
            if file_info:
                open_file_default_app(file_info.path)

    def _on_tree_space(self, event):
        """Spacebar toggles selection of currently highlighted item(s)."""
        selected = self.tree.selection()
        for item_id in selected:
            self._toggle_checkbox(item_id)
        return "break"

    def _toggle_checkbox(self, item_id: str):
        """Toggles the check state of an item."""
        if item_id not in self.tree_item_map:
            return

        group, file_info = self.tree_item_map[item_id]

        if file_info is None:
            # Clicked on group header: Toggle all files in group
            any_unchecked = any(not f.selected_for_deletion for f in group.files)
            new_state = any_unchecked
            for idx, f in enumerate(group.files):
                f.selected_for_deletion = new_state
                child_id = f"file_{group.group_id}_{idx}"
                self._update_item_ui(child_id, new_state)
            self._update_group_header_checkbox(group)
        else:
            # Clicked on specific file
            file_info.selected_for_deletion = not file_info.selected_for_deletion
            self._update_item_ui(item_id, file_info.selected_for_deletion)
            self._update_group_header_checkbox(group)

        self._update_stats_display()

    def _update_item_ui(self, item_id: str, is_checked: bool):
        chk = CHECK_CHAR if is_checked else UNCHECK_CHAR
        tag = "checked" if is_checked else "unchecked"
        self.tree.item(item_id, text=chk, tags=(tag,))

    def _update_group_header_checkbox(self, group: DuplicateGroup):
        """Updates group header checkbox based on children states."""
        group_item_id = f"group_{group.group_id}"
        total = len(group.files)
        selected = group.selected_count

        if selected == 0:
            header_chk = UNCHECK_CHAR
        elif selected == total:
            header_chk = CHECK_CHAR
        else:
            header_chk = "▣"  # Partially selected indicator

        self.tree.item(group_item_id, text=header_chk)

    def _smart_select(self, strategy: str):
        """
        Applies smart selection strategies:
        - keep_oldest: keeps oldest file, selects all newer copies
        - keep_newest: keeps newest file, selects all older copies
        - keep_first: keeps first file, selects rest
        - folder2: selects files located in Folder 2 (dir_index == 1)
        """
        if not self.duplicate_groups:
            return

        for group in self.duplicate_groups:
            if not group.files:
                continue

            if strategy == "keep_oldest":
                # Oldest has min mtime
                oldest = min(group.files, key=lambda f: f.mtime)
                for f in group.files:
                    f.selected_for_deletion = (f != oldest)

            elif strategy == "keep_newest":
                # Newest has max mtime
                newest = max(group.files, key=lambda f: f.mtime)
                for f in group.files:
                    f.selected_for_deletion = (f != newest)

            elif strategy == "keep_first":
                for idx, f in enumerate(group.files):
                    f.selected_for_deletion = (idx != 0)

            elif strategy == "folder2":
                for f in group.files:
                    f.selected_for_deletion = (f.dir_index == 1)

            # Update UI for this group
            for idx, f in enumerate(group.files):
                child_id = f"file_{group.group_id}_{idx}"
                self._update_item_ui(child_id, f.selected_for_deletion)
            self._update_group_header_checkbox(group)

        self._update_stats_display()

    def _select_all(self, state: bool):
        """Selects or deselects all duplicate files."""
        for group in self.duplicate_groups:
            for idx, f in enumerate(group.files):
                f.selected_for_deletion = state
                child_id = f"file_{group.group_id}_{idx}"
                self._update_item_ui(child_id, state)
            self._update_group_header_checkbox(group)
        self._update_stats_display()

    def _invert_selection(self):
        """Inverts the current selection for all files."""
        for group in self.duplicate_groups:
            for idx, f in enumerate(group.files):
                f.selected_for_deletion = not f.selected_for_deletion
                child_id = f"file_{group.group_id}_{idx}"
                self._update_item_ui(child_id, f.selected_for_deletion)
            self._update_group_header_checkbox(group)
        self._update_stats_display()

    def _toggle_selected_item(self):
        selected = self.tree.selection()
        for item_id in selected:
            self._toggle_checkbox(item_id)

    def _context_open_file(self):
        selected = self.tree.selection()
        for item_id in selected:
            if item_id in self.tree_item_map:
                _, file_info = self.tree_item_map[item_id]
                if file_info:
                    open_file_default_app(file_info.path)

    def _context_reveal_explorer(self):
        selected = self.tree.selection()
        for item_id in selected:
            if item_id in self.tree_item_map:
                _, file_info = self.tree_item_map[item_id]
                if file_info:
                    reveal_in_explorer(file_info.path)

    def _context_copy_path(self):
        selected = self.tree.selection()
        paths = []
        for item_id in selected:
            if item_id in self.tree_item_map:
                _, file_info = self.tree_item_map[item_id]
                if file_info:
                    paths.append(file_info.path)
        if paths:
            self.root.clipboard_clear()
            self.root.clipboard_append("\n".join(paths))

    def _update_stats_display(self):
        """Updates the bottom bar statistics count."""
        total_groups = len(self.duplicate_groups)
        total_files = sum(g.count for g in self.duplicate_groups)
        selected_files = sum(g.selected_count for g in self.duplicate_groups)
        selected_bytes = sum(g.selected_size for g in self.duplicate_groups)

        self.stats_label.configure(
            text=f"Total: {total_groups} duplicate groups ({total_files} files) | Selected for removal: {selected_files} files ({format_size(selected_bytes)} to free)"
        )

    def _confirm_and_delete(self):
        """Performs safety checks, opens confirmation modal, and deletes files."""
        selected_files, unsafe_groups = FileDeleter.validate_group_safety(self.duplicate_groups)

        if not selected_files:
            messagebox.showinfo("No Files Selected", "Please select at least one file to delete.", parent=self.root)
            return

        # Critical Safety Check: Are ALL copies selected in any group?
        if unsafe_groups:
            msg = (
                f"CAUTION: In {len(unsafe_groups)} group(s), you have selected ALL copies for deletion!\n\n"
                f"Deleting every copy will cause complete and permanent loss of those files:\n"
            )
            for grp in unsafe_groups[:3]:
                msg += f" • Group #{grp.group_id}: '{grp.files[0].filename}' ({grp.count} copies)\n"
            if len(unsafe_groups) > 3:
                msg += f" • ... and {len(unsafe_groups) - 3} more groups.\n"

            msg += "\nDo you really want to delete ALL copies of these files?"

            confirmed = messagebox.askyesno("Warning: All Copies Selected", msg, icon="warning", parent=self.root)
            if not confirmed:
                return

        # Confirmation Dialog
        to_recycle = self.recycle_bin_var.get()
        destination = "Windows Recycle Bin (Restorable)" if to_recycle else "PERMANENT DELETION (Cannot be undone)"
        total_bytes = sum(f.size for f in selected_files)

        summary_msg = (
            f"Are you sure you want to remove {len(selected_files)} duplicate file(s)?\n\n"
            f"• Total space to be freed: {format_size(total_bytes)}\n"
            f"• Target Destination: {destination}\n\n"
            f"Proceed with deletion?"
        )

        if not messagebox.askyesno("Confirm Deletion", summary_msg, icon="question", parent=self.root):
            return

        # Disable action buttons during deletion to prevent duplicate triggers
        self.btn_delete.configure(state="disabled")
        self.btn_export.configure(state="disabled")

        # Open non-blocking progress dialog
        dialog = DeletionProgressDialog(self.root, len(selected_files), to_recycle)

        # Execute deletion on a background worker thread so the GUI never freezes or hangs
        def worker():
            res = FileDeleter.delete_files(
                selected_files,
                to_recycle_bin=to_recycle,
                progress_callback=lambda curr, tot, path: self.root.after_idle(
                    dialog.update_progress, curr, tot, path
                ),
                is_cancelled=dialog.is_cancelled
            )
            self.root.after_idle(self._on_deletion_completed, res, dialog, to_recycle)

        threading.Thread(target=worker, daemon=True).start()

    def _on_deletion_completed(self, res: DeleteResult, dialog: DeletionProgressDialog, to_recycle: bool):
        """Processes deletion results on the main thread and refreshes the UI."""
        try:
            if dialog.winfo_exists():
                dialog.destroy()
        except Exception:
            pass

        # Re-enable action buttons
        self.btn_delete.configure(state="normal")
        self.btn_export.configure(state="normal")

        # Efficiently update data models: remove deleted files using in-memory set (no disk I/O)
        if res.deleted_paths:
            for group in self.duplicate_groups:
                group.files = [f for f in group.files if f.path not in res.deleted_paths]

            # Remove groups that now have < 2 files remaining
            self.duplicate_groups = [g for g in self.duplicate_groups if len(g.files) >= 2]

            # Refresh treeview and statistics
            self._populate_tree(self.duplicate_groups)
            self._update_stats_display()

        # Display result notification
        if res.cancelled:
            msg = (
                f"Deletion was stopped by user.\n\n"
                f"Successfully removed: {res.deleted_count} file(s)\n"
                f"Space freed: {format_size(res.freed_bytes)}"
            )
            if res.errors:
                msg += f"\n\nErrors encountered:\n" + "\n".join(res.errors[:5])
            messagebox.showinfo("Deletion Stopped", msg, parent=self.root)
        elif res.errors:
            err_text = "\n".join(res.errors[:5])
            if len(res.errors) > 5:
                err_text += f"\n... and {len(res.errors) - 5} more errors."
            messagebox.showwarning(
                "Deletion Completed with Warnings",
                f"Removed {res.deleted_count} file(s).\n"
                f"Space freed: {format_size(res.freed_bytes)}\n\n"
                f"Errors:\n{err_text}",
                parent=self.root
            )
        else:
            messagebox.showinfo(
                "Deletion Successful",
                f"Successfully deleted {res.deleted_count} file(s)!\n"
                f"Freed {format_size(res.freed_bytes)} of disk space.",
                parent=self.root
            )


    def _export_report(self):
        """Exports duplicate scan results to CSV or JSON."""
        if not self.duplicate_groups:
            messagebox.showinfo("No Results", "No scan results available to export.", parent=self.root)
            return

        filepath = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export Duplicate Report",
            defaultextension=".csv",
            filetypes=[("CSV Files (*.csv)", "*.csv"), ("JSON Files (*.json)", "*.json")]
        )
        if not filepath:
            return

        try:
            if filepath.lower().endswith(".json"):
                data = []
                for g in self.duplicate_groups:
                    data.append({
                        "group_id": g.group_id,
                        "file_size": g.size,
                        "hash": g.hash_val,
                        "space_reclaimable": g.space_reclaimable,
                        "files": [
                            {
                                "path": f.path,
                                "filename": f.filename,
                                "directory": f.directory,
                                "mtime": format_timestamp(f.mtime),
                                "location": f"Folder {f.dir_index + 1}",
                                "selected_for_deletion": f.selected_for_deletion
                            }
                            for f in g.files
                        ]
                    })
                with open(filepath, "w", encoding="utf-8") as out:
                    json.dump(data, out, indent=2)
            else:
                with open(filepath, "w", newline="", encoding="utf-8") as out:
                    writer = csv.writer(out)
                    writer.writerow(["Group ID", "File Name", "Folder Path", "Size (Bytes)", "Size (Formatted)", "Modified Date", "Location", "Selected For Deletion", "Full Hash"])
                    for g in self.duplicate_groups:
                        for f in g.files:
                            writer.writerow([
                                g.group_id,
                                f.filename,
                                f.directory,
                                f.size,
                                format_size(f.size),
                                format_timestamp(f.mtime),
                                f"Folder {f.dir_index + 1}",
                                "YES" if f.selected_for_deletion else "NO",
                                f.full_hash or ""
                            ])

            messagebox.showinfo("Report Exported", f"Successfully saved duplicate report to:\n{filepath}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Export Failed", f"Could not export report:\n{e}", parent=self.root)

    def _on_close(self):
        """Handle window closing cleanly."""
        if self.scanner and self.is_scanning:
            if messagebox.askyesno("Scan in Progress", "A scan is currently running. Do you want to cancel and exit?", parent=self.root):
                self.scanner.cancel()
                self.root.destroy()
        else:
            self.root.destroy()
