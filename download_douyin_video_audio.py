from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from download_douyin_live_audio import (
    extract_first_url,
    fetch_redirect_url,
    parse_duration,
    read_url,
    safe_filename,
)


def normalize_video_url(raw_url: str) -> str:
    url = extract_first_url(raw_url)
    parsed = urlparse(url)
    if parsed.netloc.endswith("v.douyin.com"):
        return fetch_redirect_url(url)
    return url


def extract_aweme_id(url: str) -> str | None:
    patterns = [
        r"/video/(\d+)",
        r"(?:aweme_id|modal_id|group_id)=(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def iter_values(value: object):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from iter_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_values(item)
    else:
        yield value


def first_string(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, list):
        for item in value:
            result = first_string(item)
            if result:
                return result
    if isinstance(value, dict):
        for key in ("url", "uri", "main"):
            result = first_string(value.get(key))
            if result:
                return result
        for item in value.values():
            result = first_string(item)
            if result:
                return result
    return None


def ensure_scheme(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return url


def extract_json_blocks(page_html: str) -> list[object]:
    blocks: list[object] = []

    render_match = re.search(
        r'<script[^>]+id=["\']RENDER_DATA["\'][^>]*>(.*?)</script>',
        page_html,
        re.DOTALL,
    )
    if render_match:
        text = html.unescape(render_match.group(1).strip())
        for candidate in (text, unquote(text)):
            try:
                blocks.append(json.loads(candidate))
                break
            except json.JSONDecodeError:
                pass

    router_match = re.search(
        r"window\._ROUTER_DATA\s*=\s*(\{.*?\})\s*</script>",
        page_html,
        re.DOTALL,
    )
    if router_match:
        try:
            blocks.append(json.loads(router_match.group(1)))
        except json.JSONDecodeError:
            pass

    return blocks


def pick_video_play_url(data: object) -> str | None:
    for item in iter_values(data):
        if not isinstance(item, dict):
            continue

        for key in ("play_addr", "playAddr", "download_addr", "downloadAddr"):
            value = item.get(key)
            if not isinstance(value, dict):
                continue
            url = first_string(value.get("url_list") or value.get("urlList") or value)
            if url:
                return ensure_scheme(url)

    for item in iter_values(data):
        if isinstance(item, str) and ("http://" in item or "https://" in item):
            if ".mp4" in item or "mime_type=video_mp4" in item or "video_id=" in item:
                return ensure_scheme(item)
    return None


def pick_title(data: object) -> str:
    for item in iter_values(data):
        if isinstance(item, dict):
            for key in ("desc", "description", "title"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return safe_filename(value.strip()[:60])
    return "douyin_video_audio"


def is_video_media_url(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    ignored = (
        "douyin_pc_client",
        "bytednsdoc.com",
        "douyinstatic.com",
    )
    if any(marker in url for marker in ignored):
        return False
    markers = (
        "mime_type=video",
        "douyinvod.com",
        "douyinvideo.net",
        "/video/tos/",
    )
    return any(marker in url for marker in markers)


def resolve_video_url_with_browser(page_url: str) -> tuple[str, str]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Run: python -m pip install -r requirements.txt") from exc

    print("页面需要浏览器解析，正在用 Edge 获取视频地址...")
    media_urls: list[str] = []
    aweme_id = extract_aweme_id(page_url)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge", headless=True)
        except Exception as exc:
            raise RuntimeError("Could not start Microsoft Edge for video parsing.") from exc

        page = browser.new_page(
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
            ),
        )

        def remember_media(response) -> None:
            url = response.url
            if is_video_media_url(url):
                media_urls.append(url)

        page.on("response", remember_media)

        try:
            page.goto(page_url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(5_000)
            page.mouse.click(640, 360)
            page.wait_for_timeout(15_000)
        except PlaywrightTimeoutError:
            page.wait_for_timeout(5_000)

        page_html = page.content()
        title = safe_filename((page.title() or "").strip()[:60] or f"douyin_video_{aweme_id or 'audio'}")

        for url in media_urls:
            if not aweme_id or aweme_id in url:
                browser.close()
                return url, title

        if media_urls:
            browser.close()
            return media_urls[0], title

        for block in extract_json_blocks(page_html):
            play_url = pick_video_play_url(block)
            if play_url and is_video_media_url(play_url):
                browser.close()
                return play_url, pick_title(block)

        browser.close()

    raise RuntimeError("Browser parsing finished, but no video media URL was captured.")


def resolve_video_url(raw_url: str) -> tuple[str, str]:
    page_url = normalize_video_url(raw_url)
    print(f"Using URL: {page_url}")

    page_html = read_url(page_url)
    json_blocks = extract_json_blocks(page_html)
    for block in json_blocks:
        play_url = pick_video_play_url(block)
        if play_url:
            return play_url, pick_title(block)

    return resolve_video_url_with_browser(page_url)


def get_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise RuntimeError("ffmpeg was not found, and imageio-ffmpeg could not be loaded.") from exc


def extract_audio(media_url: str, output_path: Path, seconds: int | None) -> None:
    command = [
        get_ffmpeg(),
        "-hide_banner",
        "-y",
        "-loglevel",
        "info",
        "-headers",
        (
            "Referer: https://www.douyin.com/\r\n"
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0\r\n"
        ),
    ]
    if seconds is not None:
        command.extend(["-t", str(seconds)])
    command.extend(
        [
            "-i",
            media_url,
            "-vn",
            "-acodec",
            "libmp3lame",
            "-b:a",
            "192k",
            str(output_path),
        ]
    )
    subprocess.run(command, check=True)


def parse_video_duration(value: str) -> int | None:
    text = value.strip().lower()
    if text == "all":
        return None
    return parse_duration(text)


def download_video_audio(raw_url: str, duration: int | None, output: str | None = None) -> Path:
    media_url, title = resolve_video_url(raw_url)

    output_dir = Path("downloads")
    output_dir.mkdir(exist_ok=True)
    if output:
        output_path = Path(output)
        if output_path.suffix.lower() != ".mp3":
            output_path = output_path.with_suffix(".mp3")
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"{title}_{stamp}.mp3"

    duration_label = "全部" if duration is None else f"{duration} 秒"
    print(f"开始提取视频音频 {duration_label}：{output_path}")
    extract_audio(media_url, output_path, duration)
    print(f"完成：{output_path.resolve()}")
    return output_path.resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract audio from a Douyin video.")
    parser.add_argument("url", nargs="?", help="Douyin video URL or share text")
    parser.add_argument("duration", nargs="?", help="Duration: all, 30s, 10m, 1h30m; plain number means minutes")
    parser.add_argument("-o", "--output", help="Output filename or path. Defaults to the downloads folder.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    raw_url = args.url or input("请输入抖音视频链接（支持分享短链或整段分享文本）：").strip()
    duration_text = args.duration or input("请输入提取时长（all 表示全部，也支持 30s、10m、1h30m）：").strip()
    duration = parse_video_duration(duration_text)
    download_video_audio(raw_url, duration, args.output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已取消。")
        raise SystemExit(130)
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)
