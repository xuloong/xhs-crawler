# 小红书笔记批量爬取工具

这个工具用于批量爬取小红书笔记链接，尝试解析标题、正文、图片、视频和互动数据，并导出 `CSV`、`JSONL`、`Markdown`。它不绕过登录、验证码、签名或风控；如果页面无法公开访问，会在结果里记录失败原因。

## 使用

### 图形界面

#### 桌面客户端

开发环境中可直接运行：

```bash
python3 desktop_launcher.py
```

它会启动本地服务并自动打开工具界面。后续可在 Mac 上打包成 `.app`，在 Windows 上打包成 `.exe`。
桌面客户端会优先以独立窗口打开，不再依赖外部浏览器；如果开发环境缺少 `pywebview`，会自动退回到浏览器打开。

打包前安装依赖：

```bash
python3 -m pip install -r requirements-desktop.txt
```

在目标系统上构建：

```bash
python3 scripts/build_desktop.py
```

构建产物在 `dist/` 目录。Mac 需要在 macOS 上构建，Windows 需要在 Windows 上构建。
如果没有 Windows 电脑，可以把项目上传到 GitHub，然后在 Actions 里运行 `Build Windows Client`。构建完成后，在该次运行的 Artifacts 里下载 `xhs-crawler-windows`，里面包含 Windows 客户端压缩包。

Mac 如果要分发给别人使用，建议做 Apple Developer 签名和 notarize 公证。先准备：

- Apple Developer Program 账号。
- 钥匙串里安装 `Developer ID Application` 证书。
- App 专用密码，或 App Store Connect API Key。

首次保存公证凭据：

```bash
xcrun notarytool store-credentials xhs-notary \
  --apple-id "你的 Apple ID 邮箱" \
  --team-id "你的 Team ID" \
  --password "App 专用密码"
```

然后执行签名和公证：

```bash
python3 scripts/build_desktop.py
python3 scripts/sign_notarize_macos.py
```

如果有多个证书，可以指定证书名：

```bash
APPLE_CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
python3 scripts/sign_notarize_macos.py
```

#### 本地网页

启动本地网页界面：

```bash
python3 xhs_web_app.py
```

然后打开：

```text
http://127.0.0.1:8765
```

在页面里粘贴多条链接或小红书分享文案，点击“开始爬取”。每次任务会保存到 `xhs_output/<时间>/`，识别到的图片/视频会默认下载。

如果普通爬取提示受限，可以使用浏览器辅助模式：

1. 点击“打开登录浏览器”。
2. 在新打开的 Chrome 窗口里登录小红书。
3. 回到工具页面，点击“开始爬取”。

浏览器辅助模式只读取这个已登录窗口里你能正常看到的内容，不绕过验证码、登录或平台访问限制。导出字段包含作者、发布时间、点赞数、评论数、收藏数、转发数；如果页面没有暴露对应文本，字段会留空。

### 命令行

准备一个链接文件：

```txt
https://www.xiaohongshu.com/explore/xxxxxxxx
https://xhslink.com/xxxxxx
```

运行：

```bash
python3 xhs_batch_fetcher.py --input links.txt --out xhs_output
```

同时下载图片：

```bash
python3 xhs_batch_fetcher.py --input links.txt --out xhs_output --download-images
```

也可以直接传单个链接：

```bash
python3 xhs_batch_fetcher.py --link "https://www.xiaohongshu.com/explore/xxxxxxxx"
```

## 输出

- `xhs_output/notes.csv`：适合用 Excel 打开。
- `xhs_output/notes.jsonl`：每行一条完整结构化结果。
- `xhs_output/markdown/*.md`：每篇笔记一个 Markdown 文件。
- `xhs_output/images/<note_id>/`：保存图片。
- `xhs_output/videos/<note_id>/`：保存视频。

## 说明

- 如果小红书返回登录页、验证码、安全验证或限流，工具会标记为 `blocked` 或 `failed`。
- 建议只抓取你有权保存和使用的内容，并控制频率。
- 后续可以扩展成桌面版、网页后台、Excel 导入导出、任务队列和失败重试。
