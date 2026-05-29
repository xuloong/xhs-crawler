#!/usr/bin/env python3
"""
Build a macOS .app or Windows .exe with PyInstaller.

Run this script on the target platform:
  python scripts/build_desktop.py
"""

from __future__ import annotations

import platform
import subprocess
import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "小红书笔记批量爬取工具"


def main() -> int:
    env = os.environ.copy()
    env["PYINSTALLER_CONFIG_DIR"] = str(ROOT / ".pyinstaller-cache")
    system = platform.system()
    ensure_icon_assets()
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        APP_NAME,
        "--add-data",
        data_arg("README.md"),
        "--add-data",
        data_arg("assets/app_icon.png", "assets"),
        "desktop_launcher.py",
    ]
    icon_path = icon_arg(system)
    if icon_path:
        command[command.index("desktop_launcher.py"):command.index("desktop_launcher.py")] = ["--icon", icon_path]
    subprocess.run(command, cwd=ROOT, check=True, env=env)
    if system == "Darwin":
        print(f"构建完成：{ROOT / 'dist' / (APP_NAME + '.app')}")
    elif system == "Windows":
        print(f"构建完成：{ROOT / 'dist' / APP_NAME / (APP_NAME + '.exe')}")
    else:
        print(f"构建完成：{ROOT / 'dist'}")
    return 0


def data_arg(path: str, target: str = ".") -> str:
    separator = ";" if platform.system() == "Windows" else ":"
    return f"{path}{separator}{target}"


def icon_arg(system: str) -> str:
    if system == "Darwin":
        return str(ROOT / "assets" / "app_icon.icns")
    if system == "Windows":
        return str(ROOT / "assets" / "app_icon.ico")
    return ""


def ensure_icon_assets() -> None:
    required = [ROOT / "assets" / "app_icon.png"]
    if platform.system() == "Darwin":
        required.append(ROOT / "assets" / "app_icon.icns")
    elif platform.system() == "Windows":
        required.append(ROOT / "assets" / "app_icon.ico")
    if all(path.exists() for path in required):
        return
    subprocess.run([sys.executable, "scripts/generate_app_icon.py"], cwd=ROOT, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
