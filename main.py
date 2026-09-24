#!/usr/bin/env python3
"""
DuoPty — Intelligent Duplicate File Scanner & Removal Suite.
Main application entry point.
"""
import sys
import os
import argparse
import tkinter as tk

# Ensure current package directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from duopty.gui import DuoPtyGUI


def main():
    parser = argparse.ArgumentParser(
        description="DuoPty: Intelligent multi-tiered duplicate file scanner and safe removal tool."
    )
    parser.add_argument("folder1", nargs="?", default="", help="Initial primary folder to scan")
    parser.add_argument("folder2", nargs="?", default="", help="Optional secondary folder for comparison")
    parser.add_argument(
        "--mode",
        choices=["combined", "cross_dir"],
        default="combined",
        help="Scan mode: 'combined' to scan all folders together, or 'cross_dir' to compare folder 1 vs folder 2."
    )

    args = parser.parse_args()

    root = tk.Tk()
    app = DuoPtyGUI(root)

    # Pre-populate folders from command line arguments if supplied
    if args.folder1:
        app.folder1_var.set(os.path.abspath(args.folder1))
    if args.folder2:
        app.folder2_var.set(os.path.abspath(args.folder2))
    if args.mode:
        app.scan_mode_var.set(args.mode)

    root.mainloop()


if __name__ == "__main__":
    main()
