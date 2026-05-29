#!/usr/bin/env python3
"""
Browser-assisted Xiaohongshu fetcher.

This module uses a Chrome window that the user logs into directly. It only
extracts content visible to that logged-in browser session and does not bypass
captcha, login, signatures, or access controls.
"""

from __future__ import annotations

import asyncio
import os
import platform
import re
import shutil
import subprocess
import threading
import urllib.parse
from dataclasses import asdict
from pathlib import Path
from typing import Any

from xhs_batch_fetcher import NoteResult, clean_text, note_id_from_url, unique


APP_DIR = Path(__file__).resolve().parent
BROWSER_PROFILE_DIR = APP_DIR / ".xhs_browser_profile"
_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_playwright: Any | None = None
_context: Any | None = None


def ensure_login_browser() -> str:
    return run_in_browser_loop(_ensure_login_browser_async())


async def _ensure_login_browser_async() -> str:
    context = await get_browser_context()
    page = await context.new_page()
    target_url = "https://www.xiaohongshu.com/explore"
    try:
        await page.goto(target_url, wait_until="commit", timeout=15000)
    except Exception:
        try:
            await page.evaluate("(url) => { window.location.href = url; }", target_url)
        except Exception:
            pass
    try:
        await page.bring_to_front()
    except Exception:
        pass
    focus_chrome_window()
    return target_url


async def get_browser_context() -> Any:
    global _playwright, _context
    if _context is not None:
        try:
            if _context.pages:
                return _context
        except Exception:
            _context = None

    from playwright.async_api import async_playwright

    BROWSER_PROFILE_DIR.mkdir(exist_ok=True)
    _playwright = await async_playwright().start()
    launch_options = {
        "user_data_dir": str(BROWSER_PROFILE_DIR),
        "headless": False,
        "viewport": {"width": 1280, "height": 900},
        "ignore_default_args": ["--no-sandbox"],
        "args": [
            "--no-first-run",
            "--no-default-browser-check",
        ],
    }
    chrome_path = find_browser_executable()
    if chrome_path:
        launch_options["executable_path"] = chrome_path
    else:
        launch_options["channel"] = "chrome"
    _context = await _playwright.chromium.launch_persistent_context(
        **launch_options,
    )
    return _context


def close_login_browser() -> None:
    run_in_browser_loop(_close_login_browser_async())


async def _close_login_browser_async() -> None:
    global _playwright, _context
    if _context is not None:
        try:
            await _context.close()
        except Exception:
            pass
    if _playwright is not None:
        try:
            await _playwright.stop()
        except Exception:
            pass
    _context = None
    _playwright = None


def focus_chrome_window() -> None:
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to activate'], check=False, timeout=2)
        elif system == "Windows":
            # Browser windows usually come to front when launched; no hard dependency on pywin32.
            return
    except Exception:
        pass


def find_browser_executable() -> str:
    explicit = os.environ.get("XHS_BROWSER_PATH") or os.environ.get("XHS_CHROME_PATH")
    if explicit and Path(explicit).exists():
        return explicit

    system = platform.system()
    candidates: list[str] = []
    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        ]
    elif system == "Windows":
        roots = [os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")]
        for root in [value for value in roots if value]:
            candidates.extend(
                [
                    str(Path(root) / "Google/Chrome/Application/chrome.exe"),
                    str(Path(root) / "Microsoft/Edge/Application/msedge.exe"),
                ]
            )
    else:
        candidates = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"]

    for candidate in candidates:
        path = shutil.which(candidate) if not Path(candidate).is_absolute() else candidate
        if path and Path(path).exists():
            return str(path)
    return ""


def fetch_with_logged_in_browser(links: list[str], delay: float = 1.5, timeout: float = 25) -> list[NoteResult]:
    return run_in_browser_loop(_fetch_with_logged_in_browser_async(links, delay=delay, timeout=timeout))


async def _fetch_with_logged_in_browser_async(
    links: list[str],
    delay: float = 1.5,
    timeout: float = 25,
) -> list[NoteResult]:
    context = await get_browser_context()
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    results: list[NoteResult] = []
    page = await context.new_page()
    page.set_default_timeout(timeout * 1000)

    for index, link in enumerate(unique(links), start=1):
        result = NoteResult(source_url=link, note_id=note_id_from_url(link))
        try:
            await page.goto(link, wait_until="domcontentloaded", timeout=timeout * 1000)
            await settle_page(page)
            result.final_url = page.url
            result.note_id = note_id_from_url(page.url)
            result = await extract_page_result(page, result)
        except PlaywrightTimeoutError as exc:
            result.status = "failed"
            result.error = f"browser_timeout:{exc}"
        except Exception as exc:  # noqa: BLE001 - keep batch jobs moving.
            result.status = "failed"
            result.error = f"browser_error:{exc}"
        results.append(result)
        if index < len(links) and delay > 0:
            await asyncio.sleep(delay)
    try:
        await page.close()
    except Exception:
        pass
    return results


def get_browser_loop() -> asyncio.AbstractEventLoop:
    global _loop, _loop_thread
    if _loop and _loop.is_running():
        return _loop
    _loop = asyncio.new_event_loop()

    def run_loop() -> None:
        assert _loop is not None
        asyncio.set_event_loop(_loop)
        _loop.run_forever()

    _loop_thread = threading.Thread(target=run_loop, name="xhs-browser-loop", daemon=True)
    _loop_thread.start()
    return _loop


def run_in_browser_loop(coro: Any) -> Any:
    loop = get_browser_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()


async def settle_page(page: Any) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=6000)
    except Exception:
        pass
    # Give client-rendered note content a small moment to hydrate.
    await asyncio.sleep(1)


async def extract_page_result(page: Any, result: NoteResult) -> NoteResult:
    data = await page.evaluate(
        """
        () => {
          const meta = (name) => {
            const node = document.querySelector(`meta[property="${name}"], meta[name="${name}"]`);
            return node ? node.getAttribute("content") || "" : "";
          };
          const visibleText = (selector) => Array.from(document.querySelectorAll(selector))
            .map((node) => (node.innerText || node.textContent || "").trim())
            .filter(Boolean);
          const attrText = (selector, attr) => Array.from(document.querySelectorAll(selector))
            .map((node) => node.getAttribute(attr) || "")
            .filter(Boolean);
          const images = Array.from(document.images)
            .map((img) => img.currentSrc || img.src || "")
            .filter(Boolean);
          const videos = Array.from(document.querySelectorAll("video, video source, source"))
            .map((node) => node.currentSrc || node.src || node.getAttribute("src") || "")
            .filter(Boolean);
          const buttonTexts = Array.from(document.querySelectorAll("button, [role=button], a, span, div"))
            .map((node) => [
              node.innerText || node.textContent || "",
              node.getAttribute("aria-label") || "",
              node.getAttribute("title") || ""
            ].join(" ").trim())
            .filter(Boolean);
          const times = Array.from(document.querySelectorAll("time, [datetime], [class*=time], [class*=date]"))
            .map((node) => node.getAttribute("datetime") || node.innerText || node.textContent || "")
            .filter(Boolean);
          return {
            title: document.title || meta("og:title") || meta("twitter:title"),
            description: meta("description") || meta("og:description") || meta("twitter:description"),
            videoMeta: meta("og:video") || meta("og:video:url") || meta("twitter:player:stream"),
            authorMeta: meta("author") || meta("og:author") || meta("article:author"),
            headings: visibleText("h1, [class*=title], [id*=title]"),
            authors: visibleText("[class*=author], [class*=user], [class*=name], [class*=nickname], a[href*='/user/profile']"),
            texts: visibleText("[class*=desc], [class*=content], [class*=note], article, main"),
            buttonTexts,
            times,
            datetimeAttrs: attrText("[datetime]", "datetime"),
            bodyText: (document.body && document.body.innerText || "").trim(),
            images,
            videos,
          };
        }
        """
    )
    title = first_text(data.get("headings", []), max_len=140) or strip_xhs_suffix(data.get("title", ""))
    images = normalize_images(data.get("images", []), page.url)
    videos = normalize_videos(data.get("videos", []) + [data.get("videoMeta", "")], page.url)
    body_text = clean_text(data.get("bodyText", ""))
    content = extract_note_content(body_text, title) or first_text(data.get("texts", []), min_len=8, max_len=5000)
    content = content or clean_text(data.get("description", ""))
    stats = extract_stats(data.get("buttonTexts", []) + [body_text])

    if is_blocked_text(body_text):
        result.status = "blocked"
        result.error = "browser_blocked_or_login_required"
    elif title or content or images or videos:
        result.status = "ok"
    else:
        result.status = "empty"
        result.error = "browser_no_parseable_content"

    result.title = title
    result.content = content
    result.author = extract_author(data, body_text)
    result.publish_time = extract_publish_time(data.get("times", []) + data.get("datetimeAttrs", []) + [body_text])
    result.likes = stats.get("likes", "")
    result.comments = stats.get("comments", "")
    result.collects = stats.get("collects", "")
    result.shares = stats.get("shares", "")
    result.images = images
    result.videos = videos
    return result


def first_text(values: list[str], min_len: int = 1, max_len: int = 300) -> str:
    cleaned = [clean_text(value) for value in values if isinstance(value, str)]
    cleaned = [value for value in unique(cleaned) if min_len <= len(value) <= max_len and value != "小红书"]
    if not cleaned:
        return ""
    return max(cleaned, key=len)


def strip_xhs_suffix(value: str) -> str:
    value = clean_text(value)
    value = re.sub(r"\s*-\s*小红书\s*$", "", value)
    return value if value != "小红书" else ""


def normalize_images(values: list[str], base_url: str) -> list[str]:
    images: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        url = urllib.parse.urljoin(base_url, value)
        if not url.startswith(("http://", "https://")):
            continue
        lowered = url.lower()
        if any(skip in lowered for skip in ("avatar", "favicon", "logo", "data:", "picasso-static", "/comment/")):
            continue
        images.append(url)
    return unique(images)


def normalize_videos(values: list[str], base_url: str) -> list[str]:
    videos: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        url = urllib.parse.urljoin(base_url, value)
        if not url.startswith(("http://", "https://")):
            continue
        lowered = url.lower()
        if any(skip in lowered for skip in ("blob:", "data:", "poster", "avatar", "favicon")):
            continue
        videos.append(url)
    return unique(videos)


def extract_note_content(body_text: str, title: str) -> str:
    text = clean_text(body_text)
    if title and title in text:
        text = text[text.find(title) :]
    text = re.sub(r"^\d+\s*/\s*\d+\s+.*?\s+关注\s+", "", text)
    cut_patterns = [
        r"\s+猜你想搜\s+",
        r"\s+编辑于\s+",
        r"\s+共\s*\d+\s*条评论\s+",
        r"\s+说点什么",
    ]
    for pattern in cut_patterns:
        match = re.search(pattern, text)
        if match:
            text = text[: match.start()]
    return clean_text(text)


def extract_author(data: dict[str, Any], body_text: str = "") -> str:
    body_match = re.search(r"(?:^|\s)\d+\s*/\s*\d+\s+(.{1,60}?)\s+关注\s+", clean_text(body_text))
    if body_match:
        return clean_text(body_match.group(1))
    meta_author = clean_text(data.get("authorMeta", ""))
    if meta_author and len(meta_author) <= 80:
        return meta_author
    candidates = data.get("authors", [])
    cleaned = []
    for value in candidates:
        text = clean_text(value)
        if not text or len(text) > 80:
            continue
        if any(skip in text for skip in ("关注", "粉丝", "获赞", "小红书号")):
            continue
        cleaned.append(text)
    return first_text(cleaned, max_len=80)


def extract_publish_time(values: list[str]) -> str:
    patterns = [
        r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?(?:\s+\d{1,2}:\d{2})?",
        r"\d{1,2}[-/.月]\d{1,2}(?:日)?(?:\s+\d{1,2}:\d{2})?",
        r"\d+\s*(?:分钟前|小时前|天前|周前|个月前|年前)",
        r"(?:昨天|前天)\s*\d{0,2}:?\d{0,2}",
    ]
    for value in values:
        text = clean_text(value)
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0).strip()
    return ""


def extract_stats(values: list[str]) -> dict[str, str]:
    stats = {"likes": "", "comments": "", "collects": "", "shares": ""}
    rules = [
        ("likes", ["赞", "点赞", "like"]),
        ("comments", ["评论", "comment"]),
        ("collects", ["收藏", "collect"]),
        ("shares", ["分享", "转发", "share"]),
    ]
    for value in values:
        text = clean_text(value)
        comment_match = re.search(r"共\s*([0-9.]+万?|[0-9.]+[kK]?)\s*条评论", text)
        if comment_match and not stats["comments"]:
            stats["comments"] = comment_match.group(1)
        bottom_match = re.search(r"说点什么.*?(?:赞\s+)?([0-9.]+万?|[0-9.]+[kK]?)\s+([0-9.]+万?|[0-9.]+[kK]?)\s+可以添加到收藏夹啦\s+([0-9.]+万?|[0-9.]+[kK]?)", text)
        if bottom_match:
            stats["likes"] = stats["likes"] or bottom_match.group(1)
            stats["collects"] = stats["collects"] or bottom_match.group(2)
            stats["comments"] = stats["comments"] or bottom_match.group(3)
        compact_bottom_match = re.search(r"说点什么.*?\s([0-9.]+万?|[0-9.]+[kK]?)\s+([0-9.]+万?|[0-9.]+[kK]?)\s+([0-9.]+万?|[0-9.]+[kK]?)\s+发送", text)
        if compact_bottom_match:
            stats["likes"] = stats["likes"] or compact_bottom_match.group(1)
            stats["collects"] = stats["collects"] or compact_bottom_match.group(2)
            stats["comments"] = stats["comments"] or compact_bottom_match.group(3)
        for key, labels in rules:
            if stats[key]:
                continue
            parsed = parse_stat_value(text, labels)
            if parsed:
                stats[key] = parsed
    return stats


def parse_stat_value(text: str, labels: list[str]) -> str:
    for label in labels:
        patterns = [
            rf"{re.escape(label)}\s*[:：]?\s*([0-9.]+万?|[0-9.]+k|[0-9.]+K)",
            rf"([0-9.]+万?|[0-9.]+k|[0-9.]+K)\s*{re.escape(label)}",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
    return ""


def is_blocked_text(text: str) -> bool:
    markers = ["登录", "扫码", "验证码", "安全验证", "访问频繁", "请完成验证"]
    return any(marker in text for marker in markers) and not ("关注" in text and "收藏" in text)


def results_as_dicts(results: list[NoteResult]) -> list[dict[str, Any]]:
    return [asdict(result) for result in results]
