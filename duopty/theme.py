"""
Styling and theme configuration for DuoPty.
Provides a modern dark theme with clean high-contrast colors and custom Treeview styling.
"""
import tkinter as tk
from tkinter import ttk

# Modern Dark Palette
BG_MAIN = "#1a1b26"        # Deep slate background
BG_SURFACE = "#24283b"     # Card / Panel surface
BG_INPUT = "#1f2335"       # Entry / list surface
BG_HOVER = "#2f354f"       # Hover state
BORDER_COLOR = "#414868"   # Border lines

TEXT_PRIMARY = "#c0caf5"   # Main body text
TEXT_WHITE = "#ffffff"     # Highlight headers
TEXT_MUTED = "#7aa2f7"     # Subtle accent text
TEXT_DIM = "#565f89"       # Inactive / placeholder

ACCENT_PRIMARY = "#7aa2f7" # Vibrant Indigo / Soft Blue
ACCENT_GREEN = "#9ece6a"   # Emerald green (actions / success)
ACCENT_RED = "#f7768e"     # Red (deletion / danger)
ACCENT_ORANGE = "#ff9e64"  # Orange (warnings / info)
ACCENT_PURPLE = "#bb9af7"  # Purple (group badges)

FONT_MAIN = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_HEADING = ("Segoe UI", 12, "bold")
FONT_TITLE = ("Segoe UI", 14, "bold")
FONT_MONO = ("Consolas", 9)


def apply_theme(root: tk.Tk):
    """Applies modern dark styling to standard ttk widgets."""
    style = ttk.Style(root)
    style.theme_use("clam")

    # Global window background
    root.configure(bg=BG_MAIN)

    # Frame styles
    style.configure("TFrame", background=BG_MAIN)
    style.configure("Surface.TFrame", background=BG_SURFACE)
    style.configure("Card.TFrame", background=BG_SURFACE, relief="solid", borderwidth=1)

    # Label styles
    style.configure("TLabel", background=BG_MAIN, foreground=TEXT_PRIMARY, font=FONT_MAIN)
    style.configure("Surface.TLabel", background=BG_SURFACE, foreground=TEXT_PRIMARY, font=FONT_MAIN)
    style.configure("Title.TLabel", background=BG_MAIN, foreground=TEXT_WHITE, font=FONT_TITLE)
    style.configure("Heading.TLabel", background=BG_SURFACE, foreground=TEXT_WHITE, font=FONT_HEADING)
    style.configure("Muted.TLabel", background=BG_SURFACE, foreground=TEXT_DIM, font=FONT_MAIN)
    style.configure("Accent.TLabel", background=BG_SURFACE, foreground=ACCENT_PRIMARY, font=FONT_BOLD)

    # LabelFrame styles
    style.configure(
        "TLabelframe",
        background=BG_SURFACE,
        foreground=TEXT_WHITE,
        font=FONT_BOLD,
        relief="solid",
        borderwidth=1
    )
    style.configure(
        "TLabelframe.Label",
        background=BG_SURFACE,
        foreground=ACCENT_PRIMARY,
        font=FONT_BOLD
    )

    # Entry styles
    style.configure(
        "TEntry",
        fieldbackground=BG_INPUT,
        background=BORDER_COLOR,
        foreground=TEXT_WHITE,
        insertcolor=TEXT_WHITE,
        bordercolor=BORDER_COLOR,
        lightcolor=BORDER_COLOR,
        darkcolor=BORDER_COLOR,
        padding=6
    )

    # Combobox styles
    style.configure(
        "TCombobox",
        fieldbackground=BG_INPUT,
        background=BG_SURFACE,
        foreground=TEXT_WHITE,
        arrowcolor=TEXT_PRIMARY,
        padding=5
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", BG_INPUT)],
        selectbackground=[("readonly", BG_HOVER)],
        selectforeground=[("readonly", TEXT_WHITE)]
    )

    # Checkbutton & Radiobutton styles
    style.configure(
        "TCheckbutton",
        background=BG_SURFACE,
        foreground=TEXT_PRIMARY,
        font=FONT_MAIN
    )
    style.map(
        "TCheckbutton",
        background=[("active", BG_SURFACE)],
        foreground=[("active", TEXT_WHITE)]
    )

    style.configure(
        "TRadiobutton",
        background=BG_SURFACE,
        foreground=TEXT_PRIMARY,
        font=FONT_MAIN
    )
    style.map(
        "TRadiobutton",
        background=[("active", BG_SURFACE)],
        foreground=[("active", TEXT_WHITE)]
    )

    # Button styles
    style.configure(
        "TButton",
        background=BG_SURFACE,
        foreground=TEXT_WHITE,
        font=FONT_MAIN,
        padding=(10, 6),
        relief="flat",
        borderwidth=1,
        bordercolor=BORDER_COLOR
    )
    style.map(
        "TButton",
        background=[("active", BG_HOVER), ("pressed", BG_INPUT)],
        foreground=[("active", TEXT_WHITE)]
    )

    # Primary Action Button (Indigo/Blue)
    style.configure(
        "Primary.TButton",
        background=ACCENT_PRIMARY,
        foreground="#1a1b26",
        font=FONT_BOLD,
        padding=(14, 7),
        relief="flat"
    )
    style.map(
        "Primary.TButton",
        background=[("active", "#89b4fa"), ("pressed", "#6c7086")],
        foreground=[("active", "#11111b")]
    )

    # Danger Action Button (Red)
    style.configure(
        "Danger.TButton",
        background=ACCENT_RED,
        foreground="#ffffff",
        font=FONT_BOLD,
        padding=(14, 7),
        relief="flat"
    )
    style.map(
        "Danger.TButton",
        background=[("active", "#f38ba8"), ("pressed", "#eba0ac")],
        foreground=[("active", "#ffffff")]
    )

    # Success Action Button (Green)
    style.configure(
        "Success.TButton",
        background=ACCENT_GREEN,
        foreground="#11111b",
        font=FONT_BOLD,
        padding=(12, 6),
        relief="flat"
    )
    style.map(
        "Success.TButton",
        background=[("active", "#a6e3a1"), ("pressed", "#94e2d5")],
        foreground=[("active", "#11111b")]
    )

    # Progressbar style
    style.configure(
        "Horizontal.TProgressbar",
        troughcolor=BG_INPUT,
        background=ACCENT_PRIMARY,
        bordercolor=BG_MAIN,
        lightcolor=ACCENT_PRIMARY,
        darkcolor=ACCENT_PRIMARY
    )

    # Treeview styles (Results list)
    style.configure(
        "Treeview",
        background=BG_SURFACE,
        foreground=TEXT_PRIMARY,
        fieldbackground=BG_SURFACE,
        bordercolor=BORDER_COLOR,
        font=FONT_MAIN,
        rowheight=28
    )
    style.configure(
        "Treeview.Heading",
        background=BG_INPUT,
        foreground=TEXT_WHITE,
        font=FONT_BOLD,
        relief="flat",
        padding=6
    )
    style.map(
        "Treeview.Heading",
        background=[("active", BG_HOVER)],
        foreground=[("active", TEXT_WHITE)]
    )
    style.map(
        "Treeview",
        background=[("selected", "#364a82")],
        foreground=[("selected", TEXT_WHITE)]
    )
