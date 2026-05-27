# 抖音直播音频下载

这个脚本会让你输入抖音直播或抖音视频链接和下载时长，只保存音频为 MP3。

## 准备

已创建虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

脚本会优先使用系统里的 `ffmpeg`；如果没有安装系统版，会自动使用虚拟环境依赖 `imageio-ffmpeg` 自带的 ffmpeg。

## 使用

统一入口：

```powershell
python .\app.py
```

然后输入：

- `1` 下载抖音直播音频
- `2` 提取抖音视频音频

交互输入：

```powershell
python .\download_douyin_live_audio.py
```

直接传参：

```powershell
python .\download_douyin_live_audio.py "https://live.douyin.com/xxxx" 10m
```

时长格式：

- `10` 表示 10 分钟
- `90s` 表示 90 秒
- `10m` 表示 10 分钟
- `1h30m` 表示 1 小时 30 分钟

如果直播间需要登录，可以尝试读取浏览器 cookies：

```powershell
python .\download_douyin_live_audio.py "https://live.douyin.com/xxxx" 10m --cookies-from-browser edge
```

输出文件默认保存在 `downloads` 目录。

## 视频音频

```powershell
python .\download_douyin_video_audio.py "https://v.douyin.com/xxxx/" all
```

视频模式下，时长输入 `all` 表示提取整条视频音频。
