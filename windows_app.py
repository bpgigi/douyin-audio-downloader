from __future__ import annotations

import contextlib
import io
import os
import queue
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from download_douyin_live_audio import parse_duration, record_audio, resolve_stream_url
from download_douyin_video_audio import download_video_audio, parse_video_duration


APP_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = APP_DIR / "downloads"


class QueueWriter(io.TextIOBase):
    def __init__(self, log_queue: queue.Queue[str]) -> None:
        self.log_queue = log_queue

    def write(self, text: str) -> int:
        if text:
            self.log_queue.put(text)
        return len(text)

    def flush(self) -> None:
        return None


class DouyinAudioApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("抖音音频下载工具")
        self.geometry("760x560")
        self.minsize(680, 500)

        self.mode_var = tk.StringVar(value="video")
        self.url_var = tk.StringVar()
        self.duration_var = tk.StringVar(value="all")
        self.status_var = tk.StringVar(value="准备就绪")
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None

        self._build_ui()
        self._poll_log_queue()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(root, text="抖音音频下载工具", font=("Microsoft YaHei UI", 18, "bold"))
        title.pack(anchor=tk.W)

        mode_frame = ttk.LabelFrame(root, text="下载类型", padding=10)
        mode_frame.pack(fill=tk.X, pady=(14, 10))
        ttk.Radiobutton(mode_frame, text="直播音频", value="live", variable=self.mode_var, command=self._on_mode_change).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text="视频音频", value="video", variable=self.mode_var, command=self._on_mode_change).pack(side=tk.LEFT, padx=(20, 0))

        form = ttk.Frame(root)
        form.pack(fill=tk.X)

        ttk.Label(form, text="链接").grid(row=0, column=0, sticky=tk.W, pady=(0, 6))
        self.url_entry = ttk.Entry(form, textvariable=self.url_var)
        self.url_entry.grid(row=1, column=0, sticky=tk.EW)
        ttk.Button(form, text="粘贴", command=self._paste_url).grid(row=1, column=1, padx=(8, 0))

        self.hint_label = ttk.Label(
            form,
            text="视频支持 v.douyin.com 短链、douyin.com/video 链接或整段分享文本。",
            foreground="#555555",
        )
        self.hint_label.grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(6, 12))

        ttk.Label(form, text="时长").grid(row=3, column=0, sticky=tk.W, pady=(0, 6))
        duration_row = ttk.Frame(form)
        duration_row.grid(row=4, column=0, columnspan=2, sticky=tk.EW)
        self.duration_entry = ttk.Entry(duration_row, textvariable=self.duration_var, width=22)
        self.duration_entry.pack(side=tk.LEFT)
        ttk.Button(duration_row, text="10 秒", command=lambda: self.duration_var.set("10s")).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(duration_row, text="1 分钟", command=lambda: self.duration_var.set("1m")).pack(side=tk.LEFT, padx=(8, 0))
        self.all_button = ttk.Button(duration_row, text="全部", command=lambda: self.duration_var.set("all"))
        self.all_button.pack(side=tk.LEFT, padx=(8, 0))

        self.duration_hint = ttk.Label(form, text="视频可填 all 提取全部；也支持 30s、10m、1h30m，纯数字按分钟。", foreground="#555555")
        self.duration_hint.grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(6, 12))
        form.columnconfigure(0, weight=1)

        actions = ttk.Frame(root)
        actions.pack(fill=tk.X, pady=(2, 10))
        self.start_button = ttk.Button(actions, text="开始下载", command=self._start)
        self.start_button.pack(side=tk.LEFT)
        ttk.Button(actions, text="打开 downloads", command=self._open_downloads).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(actions, text="清空日志", command=self._clear_log).pack(side=tk.LEFT, padx=(8, 0))

        status = ttk.Label(root, textvariable=self.status_var, foreground="#0b5cad")
        status.pack(anchor=tk.W)

        log_frame = ttk.LabelFrame(root, text="日志", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.log_text = tk.Text(log_frame, height=12, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self._on_mode_change()

    def _on_mode_change(self) -> None:
        if self.mode_var.get() == "live":
            self.hint_label.configure(text="直播支持 v.douyin.com 短链、live.douyin.com、webcast reflow 链接或整段分享文本。")
            self.duration_hint.configure(text="直播必须填写固定时长，如 30s、10m、1h30m；纯数字按分钟。")
            if self.duration_var.get().strip().lower() == "all":
                self.duration_var.set("10s")
            self.all_button.configure(state=tk.DISABLED)
        else:
            self.hint_label.configure(text="视频支持 v.douyin.com 短链、douyin.com/video 链接或整段分享文本。")
            self.duration_hint.configure(text="视频可填 all 提取全部；也支持 30s、10m、1h30m，纯数字按分钟。")
            self.all_button.configure(state=tk.NORMAL)

    def _paste_url(self) -> None:
        try:
            self.url_var.set(self.clipboard_get().strip())
        except tk.TclError:
            messagebox.showinfo("提示", "剪贴板里没有可粘贴的文本。")

    def _open_downloads(self) -> None:
        DOWNLOADS_DIR.mkdir(exist_ok=True)
        os.startfile(DOWNLOADS_DIR)

    def _clear_log(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, text)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _set_running(self, running: bool) -> None:
        self.start_button.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.status_var.set("正在处理，请稍等..." if running else "准备就绪")

    def _start(self) -> None:
        raw_url = self.url_var.get().strip()
        duration_text = self.duration_var.get().strip()

        if not raw_url:
            messagebox.showwarning("缺少链接", "请先粘贴抖音直播或视频链接。")
            return
        if not duration_text:
            messagebox.showwarning("缺少时长", "请填写下载或提取时长。")
            return

        try:
            if self.mode_var.get() == "live":
                parse_duration(duration_text)
            else:
                parse_video_duration(duration_text)
        except Exception as exc:
            messagebox.showerror("时长格式错误", str(exc))
            return

        self._set_running(True)
        self._append_log("\n--- 开始新任务 ---\n")
        self.worker = threading.Thread(target=self._run_download, args=(self.mode_var.get(), raw_url, duration_text), daemon=True)
        self.worker.start()

    def _run_download(self, mode: str, raw_url: str, duration_text: str) -> None:
        writer = QueueWriter(self.log_queue)
        try:
            with contextlib.redirect_stdout(writer), contextlib.redirect_stderr(writer):
                if mode == "live":
                    duration = parse_duration(duration_text)
                    print("正在解析直播音频流...")
                    stream_url, title = resolve_stream_url(raw_url, None)
                    DOWNLOADS_DIR.mkdir(exist_ok=True)
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_path = DOWNLOADS_DIR / f"{title}_{stamp}.mp3"
                    print(f"开始录制直播音频 {duration} 秒：{output_path}")
                    record_audio(stream_url, output_path, duration)
                    print(f"完成：{output_path.resolve()}")
                else:
                    duration = parse_video_duration(duration_text)
                    download_video_audio(raw_url, duration)
            self.log_queue.put("\n任务完成。\n")
        except Exception as exc:
            self.log_queue.put(f"\n错误：{exc}\n")
        finally:
            self.log_queue.put("__TASK_DONE__")

    def _poll_log_queue(self) -> None:
        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if item == "__TASK_DONE__":
                self._set_running(False)
            else:
                self._append_log(item)
        self.after(100, self._poll_log_queue)


def main() -> None:
    os.chdir(APP_DIR)
    app = DouyinAudioApp()
    app.mainloop()


if __name__ == "__main__":
    main()
