from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


URL_RE = re.compile(r"https?://[^\s\"'<>]+")


def parse_duration(value: str) -> int:
    text = value.strip().lower()
    if not text:
        raise argparse.ArgumentTypeError("Duration cannot be empty.")

    if text.isdigit():
        return int(text) * 60

    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", text)
    if not match or not any(match.groups()):
        raise argparse.ArgumentTypeError("Use a duration like 10, 10m, 1h30m, or 90s.")

    hours, minutes, seconds = (int(part or 0) for part in match.groups())
    total = hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        raise argparse.ArgumentTypeError("Duration must be greater than 0.")
    return total


def prompt_if_missing(value: str | None, label: str) -> str:
    if value:
        return value
    return input(label).strip()


def safe_filename(value: str) -> str:
    cleaned: list[str] = []
    for char in value:
        category = unicodedata.category(char)
        if category[0] in {"L", "N"} or char in " -_":
            cleaned.append(char)
        else:
            cleaned.append("_")

    value = "".join(cleaned)
    value = re.sub(r"_+", "_", value)
    value = re.sub(r"\s+", " ", value).strip(" ._")
    value = value[:60].strip(" ._")
    return value or "douyin_audio"


def extract_first_url(text: str) -> str:
    match = URL_RE.search(text.strip())
    if not match:
        raise RuntimeError("No URL found in your input.")
    return match.group(0).rstrip(".,;!?，。；！？")


def fetch_redirect_url(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            return response.geturl()
    except URLError:
        return url


def read_url(url: str, mobile: bool = False) -> str:
    user_agent = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_4_1 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Mobile/15E148 Safari/604.1"
        if mobile
        else (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )
    )
    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Referer": "https://www.douyin.com/",
        },
    )
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def normalize_douyin_url(raw_url: str) -> str:
    url = extract_first_url(raw_url)
    parsed = urlparse(url)

    if parsed.netloc.endswith("v.douyin.com"):
        url = fetch_redirect_url(url)
        parsed = urlparse(url)

    reflow_match = re.search(r"/reflow/(\d+)", url)
    if "webcast.amemv.com" in parsed.netloc and reflow_match:
        return f"https://live.douyin.com/{reflow_match.group(1)}"

    if "webcast.amemv.com" in parsed.netloc:
        raise RuntimeError(
            "This Douyin redirect URL does not contain a live room id. "
            "Open the link in a browser and copy the live.douyin.com room URL."
        )

    return url


def room_id_from_reflow_text(text: str) -> str | None:
    match = re.search(r"/reflow/(\d+)", text)
    if not match:
        return None
    return match.group(1)


def room_id_from_live_page(url: str) -> str | None:
    parsed = urlparse(url)
    path_id = parsed.path.strip("/").split("/")[0]

    query_match = re.search(r"(?:room_id|roomId|liveId)=(\d+)", url)
    if query_match:
        return query_match.group(1)

    if path_id.isdigit() and len(path_id) >= 16:
        return path_id

    if not (parsed.netloc.endswith("douyin.com") and path_id):
        return None

    html = read_url(f"https://live.douyin.com/{path_id}")
    patterns = [
        r'roomStore.*?roomInfo.*?room.*?id_str\\":\\"(\d+)\\"',
        r'"roomStore".*?"roomInfo".*?"room".*?"id_str"\s*:\s*"(\d+)"',
        r'id_str\\":\\"(\d+)\\",\\"status\\":2',
        r'"id_str"\s*:\s*"(\d+)"\s*,\s*"status"\s*:\s*2',
        r'roomId%22%3A%22(\d+)%22',
        r'"roomId"\s*:\s*"(\d+)"',
        r'"room_id"\s*:\s*"(\d+)"',
        r'"roomId"\s*:\s*(\d+)',
        r'"room_id"\s*:\s*(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def extract_room_id(raw_url: str) -> str:
    page_url = normalize_douyin_url(raw_url)
    print(f"Using URL: {page_url}")

    room_id = room_id_from_reflow_text(page_url) or room_id_from_live_page(page_url)
    if room_id:
        return room_id

    raise RuntimeError("Could not find a Douyin live room_id from this URL.")


def first_url(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, list):
        for item in value:
            result = first_url(item)
            if result:
                return result
    if isinstance(value, dict):
        for key in ("url", "main", "FULL_HD1", "HD1", "SD1", "SD2"):
            result = first_url(value.get(key))
            if result:
                return result
        for item in value.values():
            result = first_url(item)
            if result:
                return result
    return None


def ensure_scheme(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return url


def pick_stream_url(stream_url: dict) -> str:
    candidates = [
        stream_url.get("flv_pull_url"),
        stream_url.get("hls_pull_url"),
        stream_url.get("rtmp_pull_url"),
        stream_url.get("pull_datas"),
    ]
    for candidate in candidates:
        url = first_url(candidate)
        if url:
            return ensure_scheme(url)
    raise RuntimeError("The live room response did not include a playable stream URL.")


def resolve_stream_url(page_url: str, cookies_from_browser: str | None) -> tuple[str, str]:
    if cookies_from_browser:
        print("Note: --cookies-from-browser is not used by the direct Douyin API parser.")

    room_id = extract_room_id(page_url)
    print(f"Using room_id: {room_id}")

    api_url = (
        "https://webcast.amemv.com/webcast/room/reflow/info/"
        f"?type_id=0&live_id=1&room_id={room_id}&app_id=1128"
    )
    payload = json.loads(read_url(api_url, mobile=True))
    room = (payload.get("data") or {}).get("room") or {}
    if not room:
        raise RuntimeError("Douyin did not return room data. The live may be ended, private, or region/login restricted.")

    status = room.get("status")
    if status not in (None, 2, "2"):
        raise RuntimeError(f"This room is not live now. status={status}")

    stream_url = room.get("stream_url") or {}
    title = safe_filename(room.get("title") or (room.get("owner") or {}).get("nickname") or f"douyin_{room_id}")
    return pick_stream_url(stream_url), title


def record_audio(stream_url: str, output_path: Path, seconds: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            import imageio_ffmpeg

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as exc:
            raise RuntimeError("ffmpeg was not found, and imageio-ffmpeg could not be loaded.") from exc

    command = [
        ffmpeg,
        "-hide_banner",
        "-y",
        "-loglevel",
        "info",
        "-t",
        str(seconds),
        "-i",
        stream_url,
        "-vn",
        "-acodec",
        "libmp3lame",
        "-b:a",
        "192k",
        str(output_path),
    ]
    subprocess.run(command, check=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download Douyin live audio only.")
    parser.add_argument("url", nargs="?", help="Douyin live URL or share text")
    parser.add_argument("duration", nargs="?", type=parse_duration, help="Duration: 10 means 10 minutes; also supports 30s, 10m, 1h30m")
    parser.add_argument("-o", "--output", help="Output filename or path. Defaults to the downloads folder.")
    parser.add_argument(
        "--cookies-from-browser",
        choices=["chrome", "edge", "firefox", "brave", "vivaldi", "opera"],
        help="Read cookies from a local browser if the live room requires login.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    url = prompt_if_missing(args.url, "请输入抖音直播链接：")
    duration = args.duration
    if duration is None:
        duration = parse_duration(prompt_if_missing(None, "请输入下载时长（如 10、10m、90s、1h30m）："))

    print("正在解析直播音频流...")
    stream_url, title = resolve_stream_url(url, args.cookies_from_browser)

    output_dir = Path("downloads")
    output_dir.mkdir(exist_ok=True)
    if args.output:
        output_path = Path(args.output)
        if output_path.suffix.lower() != ".mp3":
            output_path = output_path.with_suffix(".mp3")
    else:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"{title}_{stamp}.mp3"

    print(f"开始录制音频 {duration} 秒：{output_path}")
    record_audio(stream_url, output_path, duration)
    print(f"完成：{output_path.resolve()}")
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
