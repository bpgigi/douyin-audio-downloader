# 抖音音频下载工具 Windows 版使用说明

## 怎么启动

解压发布包后，双击：

```text
DouyinAudioDownloader.exe
```

也可以双击：

```text
双击启动.bat
```

如果 Windows 提示安全提醒，请选择“更多信息”，再点“仍要运行”。

## 下载直播音频

1. 选择“直播音频”。
2. 粘贴抖音直播链接。
3. 填写下载时长，例如 `10s`、`10m`、`1h30m`。
4. 点击“开始下载”。

支持的直播链接示例：

```text
https://v.douyin.com/xxxx/
https://live.douyin.com/566388326775?enter_from_merge=link_share
```

也可以粘贴手机端整段分享文本。

## 提取视频音频

1. 选择“视频音频”。
2. 粘贴抖音视频链接。
3. 填写提取时长。
4. 点击“开始下载”。

视频时长可以填：

```text
all
10s
10m
1h30m
```

`all` 表示提取整条视频音频。

支持的视频链接示例：

```text
https://v.douyin.com/xxxx/
https://www.douyin.com/video/123456789
```

也可以粘贴手机端整段分享文本。

## 文件保存在哪里

音频默认保存到发布包目录里的：

```text
downloads
```

也可以在软件里点击“打开 downloads”。

## 注意事项

- 视频解析会自动调用本机 Microsoft Edge，等待二三十秒是正常的。
- 如果直播已经结束，直播音频无法下载。
- 如果视频或直播需要登录、被限制、被删除，可能无法解析。
- 输出文件是 MP3，只保存音频，不保存视频画面。
