from __future__ import annotations

import ctypes
import os
import sys
from typing import Any


def _set_windows_console_code_page() -> None:
    if os.name != "nt":
        return

    try:
        kernel32 = ctypes.windll.kernel32
        utf8_code_page = 65001
        kernel32.SetConsoleCP(utf8_code_page)
        kernel32.SetConsoleOutputCP(utf8_code_page)
    except Exception:
        pass


def _reconfigure_text_stream(stream: Any) -> None:
    if stream is None:
        return

    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def setup_console_utf8() -> None:
    _set_windows_console_code_page()
    _reconfigure_text_stream(sys.stdout)
    _reconfigure_text_stream(sys.stderr)
    _reconfigure_text_stream(sys.stdin)
