#!/usr/bin/env python3
"""
Batch fetch public Xiaohongshu note pages and export parsed text/image metadata.

This tool intentionally does not bypass login, captcha, signatures, or other
access controls. If a page cannot be fetched as a normal public HTTP request,
the result is recorded as blocked/failed so it can be handled manually.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36"
)

IMAGE_URL_RE = re.compile(
    r"https?:\\?/\\?/[^\"'<>\\\s]+?(?:jpg|jpeg|png|webp|gif)(?:\?[^\"'<>\\\s]*)?",
    re.IGNORECASE,
)


@dataclass
class NoteResult:
    source_url: str
    final_url: str = ""
    note_id: str = ""
    status: str = "pending"
    title: str = ""
    content: str = ""
    author: str = ""
    publish_time: str = ""
    likes: str = ""
    comments: str = ""
    collects: str = ""
    shares: str = ""
    images: list[str] = field(default_factory=list)
    downloaded_images: list[str] = field(default_factory=list)
    videos: list[str] = field(default_factory=list)
    downloaded_videos: list[str] = field(default_factory=list)
    error: str = ""


def unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def clean_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def normalize_escaped_url(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("\\/", "/")
    value = value.replace("\\u002F", "/").replace("\\u002f", "/")
    return value


def note_id_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    match = re.search(r"/(?:explore|discovery/item)/([A-Za-z0-9]+)", parsed.path)
    if match:
        return match.group(1)
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def read_links(args: argparse.Namespace) -> list[str]:
    links: list[str] = []
    if args.input:
        for line in Path(args.input).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                links.append(line)
    links.extend(args.link or [])
    return unique(links)


def http_get(url: str, timeout: float) -> tuple[str, str, int]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read().decode(charset, errors="replace")
        return body, response.geturl(), response.status


def looks_blocked(body: str, status: int) -> str:
    lowered = body.lower()
    if status in {401, 403, 429}:
        return f"http_{status}"
    markers = ["captcha", "verify", "验证", "登录后", "安全验证", "访问频繁"]
    for marker in markers:
        if marker.lower() in lowered:
            return f"blocked:{marker}"
    return ""


def extract_meta_content(body: str, names: Iterable[str]) -> str:
    for name in names:
        patterns = [
            rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']*)',
            rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']*)',
            rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{re.escape(name)}["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, body, re.IGNORECASE)
            if match:
                return clean_text(match.group(1))
    return ""


def script_json_candidates(body: str) -> list[Any]:
    candidates: list[Any] = []
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        body,
        re.IGNORECASE | re.DOTALL,
    ):
        raw = html.unescape(match.group(1)).strip()
        try:
            candidates.append(json.loads(raw))
        except json.JSONDecodeError:
            pass

    # Common SSR shape: window.__INITIAL_STATE__ = {...};
    for marker in ("__INITIAL_STATE__", "__INITIAL_SSR_STATE__", "__NEXT_DATA__"):
        idx = body.find(marker)
        if idx == -1:
            continue
        snippet = body[idx : idx + 2_000_000]
        start = snippet.find("{")
        if start == -1:
            continue
        parsed = parse_balanced_json(snippet[start:])
        if parsed is not None:
            candidates.append(parsed)
    return candidates


def parse_balanced_json(text: str) -> Any | None:
    depth = 0
    in_string = False
    escape = False
    for i, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                raw = html.unescape(text[: i + 1])
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return None
    return None


def walk_json(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key), child
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def extract_from_json(candidates: list[Any]) -> tuple[str, str, list[str]]:
    titles: list[str] = []
    contents: list[str] = []
    images: list[str] = []
    title_keys = {"title", "displaytitle", "nickname"}
    content_keys = {"desc", "description", "content", "notecontent", "text"}
    image_keys = {"image", "images", "url", "traceid", "urlpre", "original"}

    for candidate in candidates:
        for key, value in walk_json(candidate):
            normalized_key = key.lower().replace("_", "")
            if isinstance(value, str):
                text = clean_text(value)
                if not text:
                    continue
                if normalized_key in title_keys and len(text) <= 120:
                    titles.append(text)
                if normalized_key in content_keys and len(text) >= 2:
                    contents.append(text)
                if normalized_key in image_keys or "image" in normalized_key:
                    if text.startswith("http"):
                        images.append(normalize_escaped_url(text))
            elif isinstance(value, list) and normalized_key in image_keys:
                for item in value:
                    if isinstance(item, str) and item.startswith("http"):
                        images.append(normalize_escaped_url(item))

    return first_good(titles), first_good(contents), unique(images)


def first_good(values: list[str]) -> str:
    values = [value for value in unique(values) if value and value.lower() != "小红书"]
    if not values:
        return ""
    return max(values, key=len)


def extract_image_urls(body: str) -> list[str]:
    urls = [normalize_escaped_url(match.group(0)) for match in IMAGE_URL_RE.finditer(body)]
    og_image = extract_meta_content(body, ["og:image", "twitter:image"])
    if og_image:
        urls.insert(0, og_image)
    return unique(urls)


def parse_note(source_url: str, body: str, final_url: str, status_code: int) -> NoteResult:
    result = NoteResult(source_url=source_url, final_url=final_url, note_id=note_id_from_url(final_url))
    block_reason = looks_blocked(body, status_code)
    if block_reason:
        result.status = "blocked"
        result.error = block_reason
        return result

    candidates = script_json_candidates(body)
    json_title, json_content, json_images = extract_from_json(candidates)
    meta_title = extract_meta_content(body, ["og:title", "twitter:title", "title"])
    meta_desc = extract_meta_content(body, ["description", "og:description", "twitter:description"])

    result.title = json_title or meta_title
    result.content = json_content or meta_desc
    result.images = unique(json_images + extract_image_urls(body))
    result.status = "ok" if (result.title or result.content or result.images) else "empty"
    if result.status == "empty":
        result.error = "no_parseable_content"
    return result


def safe_filename(value: str, fallback: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|\s]+", "_", value).strip("._")
    return (value or fallback)[:80]


def download_images(result: NoteResult, out_dir: Path, timeout: float) -> None:
    image_dir = out_dir / "images" / result.note_id
    image_dir.mkdir(parents=True, exist_ok=True)
    for index, url in enumerate(result.images, start=1):
        ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            ext = ".jpg"
        filename = image_dir / f"{index:02d}{ext}"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                filename.write_bytes(response.read())
            result.downloaded_images.append(str(filename))
        except Exception as exc:  # noqa: BLE001 - export should continue per note.
            result.downloaded_images.append(f"FAILED {url}: {exc}")


def download_videos(result: NoteResult, out_dir: Path, timeout: float) -> None:
    video_dir = out_dir / "videos" / result.note_id
    video_dir.mkdir(parents=True, exist_ok=True)
    for index, url in enumerate(result.videos, start=1):
        ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
        if ext not in {".mp4", ".mov", ".m4v", ".webm", ".m3u8"}:
            ext = ".mp4"
        filename = video_dir / f"{index:02d}{ext}"
        try:
            request = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT, "Referer": "https://www.xiaohongshu.com/"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                filename.write_bytes(response.read())
            result.downloaded_videos.append(str(filename))
        except Exception as exc:  # noqa: BLE001 - export should continue per note.
            result.downloaded_videos.append(f"FAILED {url}: {exc}")


def write_outputs(results: list[NoteResult], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "notes.jsonl"
    csv_path = out_dir / "notes.csv"
    md_dir = out_dir / "markdown"
    md_dir.mkdir(exist_ok=True)

    with jsonl_path.open("w", encoding="utf-8") as fp:
        for result in results:
            fp.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "status",
                "note_id",
                "title",
                "content",
                "author",
                "publish_time",
                "likes",
                "comments",
                "collects",
                "shares",
                "source_url",
                "final_url",
                "images",
                "downloaded_images",
                "videos",
                "downloaded_videos",
                "error",
            ],
        )
        writer.writeheader()
        for result in results:
            row = asdict(result)
            row["images"] = "\n".join(result.images)
            row["downloaded_images"] = "\n".join(result.downloaded_images)
            row["videos"] = "\n".join(result.videos)
            row["downloaded_videos"] = "\n".join(result.downloaded_videos)
            writer.writerow(row)

    for result in results:
        name = safe_filename(result.title, result.note_id or "note")
        path = md_dir / f"{name}.md"
        lines = [
            f"# {result.title or result.note_id or 'Untitled'}",
            "",
            f"- Status: {result.status}",
            f"- Source: {result.source_url}",
            f"- Final: {result.final_url}",
            f"- Author: {result.author}",
            f"- Publish Time: {result.publish_time}",
            f"- Likes: {result.likes}",
            f"- Comments: {result.comments}",
            f"- Collects: {result.collects}",
            f"- Shares: {result.shares}",
            "",
            result.content,
            "",
        ]
        if result.images:
            lines.append("## Images")
            lines.extend(f"- {url}" for url in result.images)
            lines.append("")
        if result.videos:
            lines.append("## Videos")
            lines.extend(f"- {url}" for url in result.videos)
            lines.append("")
        if result.error:
            lines.extend(["## Error", result.error, ""])
        path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    links = read_links(args)
    if not links:
        print("No links provided. Use --input links.txt or --link URL.", file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    results: list[NoteResult] = []
    for index, link in enumerate(links, start=1):
        print(f"[{index}/{len(links)}] fetching {link}")
        try:
            body, final_url, status_code = http_get(link, timeout=args.timeout)
            result = parse_note(link, body, final_url, status_code)
            if args.download_images and result.images:
                download_images(result, out_dir, timeout=args.timeout)
        except urllib.error.HTTPError as exc:
            result = NoteResult(
                source_url=link,
                final_url=exc.url or link,
                note_id=note_id_from_url(exc.url or link),
                status="failed",
                error=f"http_error:{exc.code}",
            )
        except Exception as exc:  # noqa: BLE001 - keep batch jobs moving.
            result = NoteResult(source_url=link, note_id=note_id_from_url(link), status="failed", error=str(exc))
        results.append(result)
        print(f"  -> {result.status}: {result.title or result.error or result.note_id}")
        if index < len(links) and args.delay > 0:
            time.sleep(args.delay)

    write_outputs(results, out_dir)
    print(f"Done. Wrote {out_dir / 'notes.csv'} and {out_dir / 'notes.jsonl'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch fetch public Xiaohongshu note content.")
    parser.add_argument("--input", "-i", help="Text file with one note link per line.")
    parser.add_argument("--link", "-l", action="append", help="Single note link. Can be repeated.")
    parser.add_argument("--out", "-o", default="xhs_output", help="Output directory.")
    parser.add_argument("--download-images", action="store_true", help="Download parsed images.")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds to wait between links.")
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds.")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
