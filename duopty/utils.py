import os
import subprocess
import sys
import datetime
from typing import Union


def format_size(bytes_val: Union[int, float]) -> str:
    """Formats bytes into human readable B, KB, MB, GB, TB."""
    if bytes_val < 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if abs(bytes_val) < 1024.0:
            if unit == 'B':
                return f"{int(bytes_val)} B"
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} EB"


def format_timestamp(ts: float) -> str:
    """Formats epoch timestamp into readable YYYY-MM-DD HH:MM:SS."""
    try:
        dt = datetime.datetime.fromtimestamp(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "Unknown"


def reveal_in_explorer(filepath: str):
    """Reveals the file highlighted in Windows Explorer."""
    abs_path = os.path.abspath(filepath)
    if not os.path.exists(abs_path):
        return
    if sys.platform == "win32":
        subprocess.run(["explorer", f"/select,{abs_path}"], check=False)
    elif sys.platform == "darwin":
        subprocess.run(["open", "-R", abs_path], check=False)
    else:
        subprocess.run(["xdg-open", os.path.dirname(abs_path)], check=False)


def open_file_default_app(filepath: str):
    """Opens the file with its default associated application."""
    abs_path = os.path.abspath(filepath)
    if not os.path.exists(abs_path):
        return
    try:
        if sys.platform == "win32":
            os.startfile(abs_path)
        elif sys.platform == "darwin":
            subprocess.run(["open", abs_path], check=False)
        else:
            subprocess.run(["xdg-open", abs_path], check=False)
    except Exception:
        pass
