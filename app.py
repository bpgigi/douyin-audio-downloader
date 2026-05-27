from __future__ import annotations

import sys

from download_douyin_live_audio import parse_duration, record_audio, resolve_stream_url
from download_douyin_video_audio import download_video_audio, parse_video_duration


def ask_mode() -> str:
    print("请选择要下载的类型：")
    print("1. 抖音直播音频")
    print("2. 抖音视频音频")
    while True:
        mode = input("请输入 1 或 2：").strip()
        if mode in {"1", "2"}:
            return mode
        print("输入无效，请输入 1 或 2。")


def run_live() -> None:
    raw_url = input("请输入抖音直播链接（支持 v.douyin.com 短链、live.douyin.com、webcast reflow 链接或整段分享文本）：").strip()
    duration_text = input("请输入下载时长（如 10、30s、10m、1h30m；数字默认按分钟）：").strip()
    duration = parse_duration(duration_text)

    print("正在解析直播音频流...")
    stream_url, title = resolve_stream_url(raw_url, None)

    from datetime import datetime
    from pathlib import Path

    output_dir = Path("downloads")
    output_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{title}_{stamp}.mp3"

    print(f"开始录制直播音频 {duration} 秒：{output_path}")
    record_audio(stream_url, output_path, duration)
    print(f"完成：{output_path.resolve()}")


def run_video() -> None:
    raw_url = input("请输入抖音视频链接（支持 v.douyin.com 短链、douyin.com/video 链接或整段分享文本）：").strip()
    duration_text = input("请输入提取时长（all 表示全部；也支持 30s、10m、1h30m；数字默认按分钟）：").strip()
    duration = parse_video_duration(duration_text)
    download_video_audio(raw_url, duration)


def main() -> int:
    mode = ask_mode()
    if mode == "1":
        run_live()
    else:
        run_video()
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
