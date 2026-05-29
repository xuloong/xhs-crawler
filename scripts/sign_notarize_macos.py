#!/usr/bin/env python3
"""
Sign and notarize the packaged macOS app.

Prerequisites:
  1. Install a "Developer ID Application" certificate in Keychain Access.
  2. Store notarization credentials once with xcrun notarytool, for example:
     xcrun notarytool store-credentials xhs-notary --apple-id you@example.com --team-id TEAMID --password app-specific-password

Usage:
  python3 scripts/sign_notarize_macos.py

Optional environment variables:
  APPLE_CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
  APPLE_NOTARY_PROFILE="xhs-notary"
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "小红书笔记批量爬取工具"
APP_PATH = ROOT / "dist" / f"{APP_NAME}.app"
ZIP_PATH = ROOT / "dist" / f"{APP_NAME}-mac-notarize.zip"
ENTITLEMENTS_PATH = ROOT / "scripts" / "macos-entitlements.plist"
DEFAULT_NOTARY_PROFILE = "xhs-notary"


def main() -> int:
    if sys.platform != "darwin":
        raise SystemExit("macOS 签名和公证必须在 Mac 上执行。")
    if not APP_PATH.exists():
        raise SystemExit(f"没有找到 App：{APP_PATH}\n请先运行 python3 scripts/build_desktop.py")
    ensure_tool("xcrun")
    ensure_tool("codesign")
    ensure_tool("ditto")

    identity = os.environ.get("APPLE_CODESIGN_IDENTITY") or find_developer_id_identity()
    if not identity:
        raise SystemExit(
            "没有找到 Developer ID Application 证书。\n"
            "请先在 Apple Developer 后台创建并安装 Developer ID Application 证书，"
            "或设置 APPLE_CODESIGN_IDENTITY。"
        )

    profile = os.environ.get("APPLE_NOTARY_PROFILE", DEFAULT_NOTARY_PROFILE)
    print(f"使用签名证书：{identity}")
    print(f"使用公证凭据：{profile}")

    run(["xattr", "-cr", str(APP_PATH)])
    sign_app(identity)
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(APP_PATH)])
    run(["spctl", "--assess", "--type", "execute", "--verbose=4", str(APP_PATH)], allow_failure=True)

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    run(["ditto", "-c", "-k", "--keepParent", str(APP_PATH), str(ZIP_PATH)])
    run(["xcrun", "notarytool", "submit", str(ZIP_PATH), "--keychain-profile", profile, "--wait"])
    run(["xcrun", "stapler", "staple", str(APP_PATH)])
    run(["xcrun", "stapler", "validate", str(APP_PATH)])
    run(["spctl", "--assess", "--type", "execute", "--verbose=4", str(APP_PATH)])

    print(f"签名和公证完成：{APP_PATH}")
    print(f"可分发压缩包：{ZIP_PATH}")
    return 0


def sign_app(identity: str) -> None:
    command = [
        "codesign",
        "--force",
        "--deep",
        "--options",
        "runtime",
        "--timestamp",
        "--entitlements",
        str(ENTITLEMENTS_PATH),
        "--sign",
        identity,
        str(APP_PATH),
    ]
    run(command)


def find_developer_id_identity() -> str:
    result = run(["security", "find-identity", "-v", "-p", "codesigning"], capture=True)
    for line in result.splitlines():
        match = re.search(r'"(Developer ID Application: .+?)"', line)
        if match:
            return match.group(1)
    return ""


def ensure_tool(name: str) -> None:
    if not shutil.which(name):
        raise SystemExit(f"缺少命令：{name}")


def run(command: list[str], capture: bool = False, allow_failure: bool = False) -> str:
    print("+", " ".join(command))
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if completed.returncode and not allow_failure:
        output = completed.stdout or ""
        raise SystemExit(output or f"命令执行失败：{' '.join(command)}")
    return completed.stdout or ""


if __name__ == "__main__":
    raise SystemExit(main())
