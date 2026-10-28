"""執行環境路徑（開發 / 打包後共用）。"""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """專案根目錄；PyInstaller onedir 時為 exe 所在資料夾。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent
