#!/usr/bin/env python3
"""
Local web UI for the Xiaohongshu batch fetcher.
"""

from __future__ import annotations

import json
import mimetypes
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any

from xhs_batch_fetcher import (
    NoteResult,
    download_images,
    download_videos,
    http_get,
    note_id_from_url,
    parse_note,
    unique,
    write_outputs,
)
from xhs_browser_fetcher import ensure_login_browser, fetch_with_logged_in_browser, results_as_dicts


APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
OUTPUT_ROOT = APP_DIR / "xhs_output"
ASSETS_ROOT = APP_DIR / "assets"
URL_RE = re.compile(r"https?://[^\s，。；、,;~～]+", re.IGNORECASE)


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>小红书笔记批量爬取工具</title>
  <link rel="icon" href="/assets/app_icon.png">
  <link rel="apple-touch-icon" href="/assets/app_icon.png">
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #20242c;
      --muted: #697182;
      --line: #d9dee8;
      --accent: #df3253;
      --accent-strong: #bd2642;
      --ok: #1d8f61;
      --warn: #af6a12;
      --bad: #b42318;
      --shadow: 0 18px 45px rgba(29, 35, 48, .10);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }
    .app {
      min-height: 100vh;
      display: grid;
      grid-template-rows: auto 1fr;
    }
    header {
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }
    .topbar {
      max-width: 1440px;
      margin: 0 auto;
      padding: 18px 22px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }
    .brand-icon {
      width: 54px;
      height: 54px;
      border-radius: 12px;
      box-shadow: 0 8px 20px rgba(223, 50, 83, .18);
      flex: 0 0 auto;
    }
    .brand-text { min-width: 0; }
    h1 {
      margin: 0;
      font-size: 22px;
      line-height: 1.2;
      letter-spacing: 0;
    }
    .sub {
      margin-top: 6px;
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }
    main {
      width: min(1440px, 100%);
      margin: 0 auto;
      padding: 14px 22px 36px;
      display: grid;
      grid-template-columns: 1fr;
      grid-auto-rows: max-content;
      align-content: start;
      gap: 10px;
    }
    section, aside {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .controls {
      padding: 18px;
      align-self: start;
      display: grid;
      grid-template-columns: minmax(420px, 1fr) minmax(360px, 460px);
      gap: 18px;
      align-items: start;
    }
    .control-main,
    .control-side {
      min-width: 0;
    }
    label {
      display: block;
      font-weight: 650;
      font-size: 13px;
      margin-bottom: 8px;
    }
    textarea, input {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      outline: none;
    }
    textarea {
      min-height: 112px;
      resize: vertical;
      padding: 12px;
      line-height: 1.5;
    }
    textarea:focus, input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(223,50,83,.12); }
    .grid2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    input { height: 38px; padding: 0 10px; }
    .switch-row {
      margin-top: 14px;
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--muted);
      font-size: 14px;
    }
    .switch-row input {
      width: 18px;
      height: 18px;
      accent-color: var(--accent);
    }
    .actions {
      margin-top: 14px;
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }
    button, .file-link {
      height: 40px;
      border: 0;
      border-radius: 6px;
      padding: 0 14px;
      font-weight: 700;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      white-space: nowrap;
    }
    .actions button {
      flex: 1 1 150px;
      min-width: 0;
    }
    .actions #clearBtn {
      flex: 0 0 76px;
    }
    button.primary { background: var(--accent); color: #fff; min-width: 116px; }
    button.primary:hover { background: var(--accent-strong); }
    button.secondary, .file-link { background: #eef1f6; color: var(--ink); }
    button:disabled { opacity: .58; cursor: wait; }
    .results { min-width: 0; overflow: hidden; }
    .tabbar {
      padding: 10px 18px 0;
      display: flex;
      gap: 8px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
    }
    .tab-button {
      height: 36px;
      border-radius: 6px 6px 0 0;
      border: 1px solid transparent;
      border-bottom: 0;
      background: transparent;
      color: var(--muted);
      padding: 0 14px;
      font-weight: 700;
      cursor: pointer;
    }
    .tab-button.active {
      background: #fff;
      border-color: var(--line);
      color: var(--ink);
      position: relative;
      top: 1px;
    }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }
    .summary {
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }
    .status-line { color: var(--muted); font-size: 14px; }
    .chips { display: flex; gap: 8px; flex-wrap: wrap; }
    .chip {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 9px;
      font-size: 12px;
      color: var(--muted);
      background: #fff;
    }
    .downloads {
      padding: 12px 18px;
      display: none;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
      border-bottom: 1px solid var(--line);
    }
    .downloads.show { display: flex; }
    .download-help {
      color: var(--muted);
      font-size: 13px;
      flex-basis: 100%;
    }
    .history {
      padding: 12px 18px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfe;
    }
    .history-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 10px;
    }
    .history-list {
      display: grid;
      gap: 8px;
      max-height: 420px;
      overflow: auto;
    }
    .history-item {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: center;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }
    .history-title {
      font-weight: 700;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .history-meta {
      color: var(--muted);
      font-size: 12px;
      margin-top: 3px;
    }
    .history-snippet {
      color: #4d5566;
      font-size: 13px;
      line-height: 1.45;
      margin-top: 6px;
      max-width: 920px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .history-empty {
      color: var(--muted);
      font-size: 13px;
      padding: 8px 0;
    }
    .table-wrap { overflow: auto; max-height: calc(100vh - 260px); }
    table {
      width: 100%;
      min-width: 1240px;
      border-collapse: collapse;
      font-size: 13px;
    }
    th, td {
      text-align: left;
      border-bottom: 1px solid var(--line);
      padding: 11px 12px;
      vertical-align: top;
    }
    th {
      position: sticky;
      top: 0;
      background: #fbfcfe;
      z-index: 1;
      color: #4d5566;
      font-size: 12px;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      min-width: 58px;
      justify-content: center;
      border-radius: 999px;
      padding: 4px 8px;
      font-weight: 700;
      font-size: 12px;
    }
    .ok { color: var(--ok); background: rgba(29,143,97,.11); }
    .manual { color: #295d94; background: rgba(53,97,167,.12); }
    .empty { color: var(--warn); background: rgba(175,106,18,.12); }
    .blocked, .failed { color: var(--bad); background: rgba(180,35,24,.10); }
    .url {
      color: #3561a7;
      max-width: 260px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      display: block;
    }
    .title-cell {
      min-width: 240px;
      max-width: 340px;
      font-weight: 650;
      line-height: 1.45;
    }
    .link-cell {
      min-width: 72px;
    }
    .link-cell .row-actions {
      margin-top: 0;
    }
    .media-cell {
      width: 82px;
      min-width: 82px;
      white-space: nowrap;
    }
    .media-cell .muted {
      display: inline-block;
      white-space: nowrap;
    }
    .error-note {
      margin-top: 6px;
      color: var(--bad);
      font-size: 12px;
      line-height: 1.35;
    }
    .content {
      max-width: 560px;
      color: #3d4554;
      line-height: 1.45;
    }
    .stats-cell {
      min-width: 84px;
      white-space: nowrap;
      line-height: 1.65;
    }
    .muted { color: var(--muted); }
    .empty-state {
      padding: 58px 22px;
      color: var(--muted);
      text-align: center;
    }
    .row-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 8px;
    }
    .mini-link, .mini-button {
      height: 30px;
      min-height: 30px;
      box-sizing: border-box;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: #fff;
      color: #3561a7;
      padding: 0 9px;
      font-weight: 700;
      font-size: 12px;
      text-decoration: none;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      line-height: 1;
    }
    .mini-button:hover, .mini-link:hover { border-color: #b9c6dc; }
    .modal {
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 18px;
      background: rgba(24, 29, 39, .48);
      z-index: 10;
    }
    .modal.show { display: flex; }
    .dialog {
      width: min(720px, 100%);
      max-height: min(760px, calc(100vh - 36px));
      overflow: auto;
      background: var(--panel);
      border-radius: 8px;
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      padding: 18px;
    }
    .dialog h2 {
      margin: 0 0 12px;
      font-size: 18px;
      letter-spacing: 0;
    }
    .dialog textarea { min-height: 130px; }
    .image-dialog { width: min(1040px, 100%); }
    .image-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
      gap: 12px;
      margin-top: 12px;
    }
    .video-grid {
      grid-template-columns: 1fr;
    }
    .image-item {
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #f8fafc;
    }
    .image-item img {
      display: block;
      width: 100%;
      aspect-ratio: 1;
      object-fit: cover;
      background: #eef1f6;
    }
    .video-player {
      display: block;
      width: 100%;
      max-height: 520px;
      background: #10131a;
    }
    .image-item a {
      display: block;
      padding: 8px;
      color: #3561a7;
      font-size: 12px;
      text-decoration: none;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .dialog .field { margin-top: 12px; }
    .dialog .help {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
      margin-bottom: 12px;
    }
    .dialog-actions {
      display: flex;
      justify-content: flex-end;
      gap: 10px;
      margin-top: 16px;
    }
    @media (max-width: 860px) {
      main { grid-template-columns: 1fr; padding: 12px; gap: 10px; }
      .topbar { padding: 16px; align-items: flex-start; }
      .controls { grid-template-columns: 1fr; }
      .grid2 { grid-template-columns: 1fr; }
      .table-wrap { max-height: none; }
      textarea { min-height: 220px; }
    }
  </style>
</head>
<body>
  <div class="app">
    <header>
      <div class="topbar">
        <div class="brand">
          <img class="brand-icon" src="/assets/app_icon.png" alt="">
          <div class="brand-text">
            <h1>小红书笔记批量爬取工具</h1>
            <div class="sub">批量爬取笔记内容，自动下载图片/视频，并导出表格和文档。</div>
          </div>
        </div>
        <div class="chips">
          <span class="chip">CSV 表格</span>
          <span class="chip">JSONL 数据</span>
          <span class="chip">Markdown 文档</span>
        </div>
      </div>
    </header>
    <main>
      <aside class="controls">
        <div class="control-main">
          <label for="links">笔记链接</label>
          <textarea id="links" placeholder="每行一个链接，例如：https://www.xiaohongshu.com/explore/xxxxxxxx"></textarea>
        </div>
        <div class="control-side">
          <div class="grid2">
            <div>
              <label for="delay">间隔秒数</label>
              <input id="delay" type="number" min="0" step="0.5" value="2">
              <div class="sub">每条链接之间抓取间隔时长。</div>
            </div>
            <div>
              <label for="timeout">超时秒数</label>
              <input id="timeout" type="number" min="3" step="1" value="20">
              <div class="sub">单条链接抓取最多等待时长。</div>
            </div>
          </div>
          <div class="actions">
            <button id="loginBrowserBtn" class="secondary" type="button">打开登录浏览器</button>
            <button id="browserRunBtn" class="primary" type="button">开始爬取</button>
            <button id="clearBtn" class="secondary" type="button">清空</button>
          </div>
        </div>
      </aside>
      <section class="results">
        <div class="tabbar">
          <button id="detailTab" class="tab-button active" type="button">详情</button>
          <button id="historyTab" class="tab-button" type="button">历史记录</button>
        </div>
        <div id="detailPanel" class="tab-panel active">
          <div class="summary">
            <div>
              <strong id="summaryTitle">等待任务</strong>
              <div id="statusLine" class="status-line">粘贴链接后点击开始爬取。</div>
            </div>
            <div class="chips">
              <span id="countOk" class="chip">成功 0</span>
              <span id="countBlocked" class="chip">受限 0</span>
              <span id="countFailed" class="chip">失败 0</span>
            </div>
          </div>
          <div id="downloads" class="downloads"></div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>状态</th>
                  <th class="title-cell">标题</th>
                  <th>博主/时间</th>
                  <th>互动</th>
                  <th>正文</th>
                  <th>图片</th>
                  <th>视频</th>
                  <th>链接</th>
                </tr>
              </thead>
              <tbody id="tbody">
                <tr><td colspan="8"><div class="empty-state">还没有结果。</div></td></tr>
              </tbody>
            </table>
          </div>
        </div>
        <div id="historyPanel" class="tab-panel">
          <div class="history">
            <div class="history-head">
              <strong>历史记录</strong>
              <button id="refreshHistoryBtn" class="secondary" type="button">刷新</button>
            </div>
            <div id="historyList" class="history-list">
              <div class="history-empty">暂无历史</div>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>
  <div id="manualModal" class="modal" aria-hidden="true">
    <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="manualTitle">
      <h2 id="manualTitle">手动补录</h2>
      <div class="help">用于处理受限笔记：在浏览器或 App 里正常打开后，把你能看到的标题、正文、图片链接填到这里，再重新导出。</div>
      <div class="field">
        <label for="manualTitleInput">标题</label>
        <input id="manualTitleInput" type="text">
      </div>
      <div class="field">
        <label for="manualContentInput">正文</label>
        <textarea id="manualContentInput"></textarea>
      </div>
      <div class="field">
        <label for="manualImagesInput">图片链接</label>
        <textarea id="manualImagesInput" placeholder="每行一个图片链接"></textarea>
      </div>
      <div class="dialog-actions">
        <button id="manualCancelBtn" class="secondary" type="button">取消</button>
        <button id="manualSaveBtn" class="primary" type="button">保存补录</button>
      </div>
    </div>
  </div>
  <div id="imageModal" class="modal" aria-hidden="true">
    <div class="dialog image-dialog" role="dialog" aria-modal="true" aria-labelledby="imageTitle">
      <h2 id="imageTitle">图片预览</h2>
      <div id="imageHelp" class="help"></div>
      <div id="imageGrid" class="image-grid"></div>
      <div class="dialog-actions">
        <button id="imageCloseBtn" class="secondary" type="button">关闭</button>
      </div>
    </div>
  </div>
  <div id="videoModal" class="modal" aria-hidden="true">
    <div class="dialog image-dialog" role="dialog" aria-modal="true" aria-labelledby="videoTitle">
      <h2 id="videoTitle">视频文件</h2>
      <div id="videoHelp" class="help"></div>
      <div id="videoGrid" class="image-grid video-grid"></div>
      <div class="dialog-actions">
        <button id="videoCloseBtn" class="secondary" type="button">关闭</button>
      </div>
    </div>
  </div>
  <script>
    const $ = (id) => document.getElementById(id);
    const loginBrowserBtn = $("loginBrowserBtn");
    const browserRunBtn = $("browserRunBtn");
    const links = $("links");
    const tbody = $("tbody");
    const downloads = $("downloads");
    const historyList = $("historyList");
    const detailTab = $("detailTab");
    const historyTab = $("historyTab");
    const detailPanel = $("detailPanel");
    const historyPanel = $("historyPanel");
    let currentResults = [];
    let editingIndex = -1;

    $("clearBtn").addEventListener("click", () => {
      links.value = "";
      renderResults([]);
      switchTab("detail");
      setSummary("等待任务", "粘贴链接后点击开始爬取。", []);
      downloads.classList.remove("show");
      downloads.innerHTML = "";
    });
    $("refreshHistoryBtn").addEventListener("click", loadHistoryList);
    detailTab.addEventListener("click", () => switchTab("detail"));
    historyTab.addEventListener("click", () => {
      switchTab("history");
      loadHistoryList();
    });
    historyList.addEventListener("click", (event) => {
      const button = event.target.closest("[data-history-id]");
      if (button) loadHistoryRun(button.dataset.historyId || "");
    });

    loginBrowserBtn.addEventListener("click", async () => {
      loginBrowserBtn.disabled = true;
      setSummary("正在打开登录浏览器", "请在新打开的 Chrome 窗口里扫码登录小红书。", currentResults);
      try {
        const res = await fetch("/api/browser-start", { method: "POST" });
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || "浏览器启动失败");
        setSummary("登录浏览器已打开", payload.message || "扫码登录完成后，回到这里点“开始爬取”。", currentResults);
        renderLoginLinks(payload);
      } catch (err) {
        setSummary("浏览器启动失败", err.message || String(err), currentResults);
      } finally {
        loginBrowserBtn.disabled = false;
      }
    });

    browserRunBtn.addEventListener("click", async () => {
      const items = extractUrls(links.value);
      if (!items.length) {
        setSummary("没有链接", "请先粘贴至少一个笔记链接。", []);
        return;
      }
      browserRunBtn.disabled = true;
      browserRunBtn.textContent = "爬取中";
      renderResults([]);
      setSummary("爬取中", `正在用浏览器爬取 ${items.length} 条链接...`, []);
      downloads.classList.remove("show");
      downloads.innerHTML = "";
      try {
        const res = await fetch("/api/browser-fetch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            links: items,
            delay: Number($("delay").value || 0),
            timeout: Number($("timeout").value || 25),
            download_images: true
          })
        });
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || "爬取失败");
        currentResults = payload.results || [];
        renderResults(currentResults);
        switchTab("detail");
        setSummary("爬取完成", payload.message || "结果已导出。", currentResults);
        renderDownloads(payload.files || {});
        loadHistoryList();
      } catch (err) {
        setSummary("爬取失败", err.message || String(err), currentResults);
      } finally {
        browserRunBtn.disabled = false;
        browserRunBtn.textContent = "开始爬取";
      }
    });

    tbody.addEventListener("click", (event) => {
      const manualButton = event.target.closest("[data-action='manual']");
      if (manualButton) {
        openManualEditor(Number(manualButton.dataset.index));
        return;
      }
      const copyButton = event.target.closest("[data-action='copy']");
      if (copyButton) {
        copyLink(copyButton.dataset.url || "");
        return;
      }
      const imagesButton = event.target.closest("[data-action='images']");
      if (imagesButton) {
        openImageViewer(Number(imagesButton.dataset.index));
        return;
      }
      const videosButton = event.target.closest("[data-action='videos']");
      if (videosButton) {
        openVideoViewer(Number(videosButton.dataset.index));
        return;
      }
      const openButton = event.target.closest("[data-action='open']");
      if (openButton) {
        openExternalLink(openButton.dataset.url || "");
      }
    });

    $("manualCancelBtn").addEventListener("click", closeManualEditor);
    $("manualModal").addEventListener("click", (event) => {
      if (event.target.id === "manualModal") closeManualEditor();
    });
    $("imageCloseBtn").addEventListener("click", closeImageViewer);
    $("imageModal").addEventListener("click", (event) => {
      if (event.target.id === "imageModal") closeImageViewer();
    });
    $("videoCloseBtn").addEventListener("click", closeVideoViewer);
    $("videoModal").addEventListener("click", (event) => {
      if (event.target.id === "videoModal") closeVideoViewer();
    });
    $("manualSaveBtn").addEventListener("click", async () => {
      if (editingIndex < 0 || !currentResults[editingIndex]) return;
      const item = currentResults[editingIndex];
      item.title = $("manualTitleInput").value.trim();
      item.content = $("manualContentInput").value.trim();
      item.images = extractUrls($("manualImagesInput").value);
      item.status = "manual";
      item.error = "";
      closeManualEditor();
      renderResults(currentResults);
      setSummary("已补录", "正在重新导出补录后的结果...", currentResults);
      await exportCurrentResults();
    });

    function setSummary(title, line, results) {
      $("summaryTitle").textContent = title;
      $("statusLine").textContent = line;
      const counts = results.reduce((acc, item) => {
        acc[item.status] = (acc[item.status] || 0) + 1;
        return acc;
      }, {});
      $("countOk").textContent = `成功 ${(counts.ok || 0) + (counts.manual || 0)}`;
      $("countBlocked").textContent = `受限 ${counts.blocked || 0}`;
      $("countFailed").textContent = `失败 ${(counts.failed || 0) + (counts.empty || 0)}`;
    }

    function switchTab(tab) {
      const showHistory = tab === "history";
      detailTab.classList.toggle("active", !showHistory);
      historyTab.classList.toggle("active", showHistory);
      detailPanel.classList.toggle("active", !showHistory);
      historyPanel.classList.toggle("active", showHistory);
    }

    async function loadHistoryList() {
      try {
        const res = await fetch("/api/history");
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || "历史记录读取失败");
        const runs = payload.runs || [];
        historyList.innerHTML = runs.length
          ? runs.map((run) => `
              <div class="history-item">
                <div>
                  <div class="history-title">${escapeHtml(run.title || formatHistoryTitle(run.id))}</div>
                  <div class="history-meta">${escapeHtml(run.count || 0)} 条 · 成功 ${escapeHtml(run.ok || 0)} · 失败 ${escapeHtml(run.failed || 0)} · ${escapeHtml(formatHistoryTitle(run.id))}</div>
                  ${run.snippet ? `<div class="history-snippet">${escapeHtml(run.snippet)}</div>` : ""}
                </div>
                <button class="mini-button" type="button" data-history-id="${escapeHtml(run.id)}">载入</button>
              </div>
            `).join("")
          : '<div class="history-empty">暂无历史</div>';
      } catch (err) {
        historyList.innerHTML = '<div class="history-empty">历史读取失败</div>';
      }
    }

    async function loadHistoryRun(runId) {
      try {
        const res = await fetch(`/api/history-load?id=${encodeURIComponent(runId)}`);
        const payload = await res.json();
        if (!res.ok) throw new Error(payload.error || "历史记录载入失败");
        currentResults = payload.results || [];
        renderResults(currentResults);
        switchTab("detail");
        setSummary("已载入历史", payload.message || "历史结果已载入。", currentResults);
        renderDownloads(payload.files || {});
      } catch (err) {
        setSummary("历史载入失败", err.message || String(err), currentResults);
      }
    }

    function renderDownloads(files) {
      const entries = [
        ["下载 CSV 表格", files.csv, "notes.csv"],
        ["下载 JSONL 数据", files.jsonl, "notes.jsonl"],
        ["查看 Markdown 文档", files.markdown, ""]
      ].filter(([, href]) => href);
      downloads.innerHTML = `
        <div class="download-help">结果文件：CSV 给 Excel/WPS，JSONL 给程序处理，Markdown 是每篇笔记的可读文档。</div>
        ${entries.map(([label, href, filename]) => `<a class="file-link" href="${href}" ${filename ? `download="${filename}"` : ""}>${label}</a>`).join("")}
      `;
      downloads.classList.toggle("show", entries.length > 0);
    }

    function renderLoginLinks(payload) {
      const loginUrl = payload.login_url || "https://www.xiaohongshu.com";
      const debugUrl = payload.debug_url || "";
      downloads.innerHTML = `
        <a class="file-link" href="${escapeHtml(loginUrl)}" target="_blank">打开小红书登录页</a>
        ${debugUrl ? `<button class="secondary" type="button" data-copy-login="${escapeHtml(debugUrl)}">复制登录地址</button>` : ""}
      `;
      downloads.classList.add("show");
      const copyBtn = downloads.querySelector("[data-copy-login]");
      if (copyBtn) copyBtn.addEventListener("click", () => copyLink(copyBtn.dataset.copyLogin || ""));
    }

    function renderResults(results) {
      currentResults = results;
      if (!results.length) {
        tbody.innerHTML = `<tr><td colspan="8"><div class="empty-state">还没有结果。</div></td></tr>`;
        return;
      }
      tbody.innerHTML = results.map((item, index) => {
        const status = escapeHtml(item.status || "");
        const title = escapeHtml(item.title || item.note_id || "未解析到标题");
        const content = escapeHtml(trim(item.content || "", 130));
        const imageCount = (item.images || []).length;
        const videoCount = (item.videos || []).length;
        const error = escapeHtml(item.error || "");
        const finalUrl = escapeHtml(item.final_url || item.source_url || "");
        const author = escapeHtml(item.author || "");
        const publishTime = escapeHtml(item.publish_time || "");
        const stats = `
          <div>赞 ${escapeHtml(item.likes || "-")}</div>
          <div>藏 ${escapeHtml(item.collects || "-")}</div>
          <div>评 ${escapeHtml(item.comments || "-")}</div>
        `;
        const actionHtml = `<div class="row-actions">
          <button class="mini-button" type="button" data-action="open" data-url="${finalUrl}">打开</button>
          ${item.status === "blocked" || item.status === "failed" || item.status === "empty" ? `<button class="mini-button" type="button" data-action="manual" data-index="${index}">补录</button>` : ""}
        </div>`;
        return `<tr>
          <td><span class="badge ${status}">${status}</span></td>
          <td class="title-cell">${title}</td>
          <td><div>${author || '<span class="muted">无</span>'}</div><div class="muted">${publishTime || ''}</div></td>
          <td class="stats-cell">${stats}</td>
          <td><div class="content">${content || '<span class="muted">无</span>'}</div></td>
          <td class="media-cell">
            ${imageCount ? `<button class="mini-button" type="button" data-action="images" data-index="${index}">${imageCount}张图</button>` : '<span class="muted">0图</span>'}
          </td>
          <td class="media-cell">${videoCount ? `<button class="mini-button" type="button" data-action="videos" data-index="${index}">${videoCount}个视频</button>` : '<span class="muted">0视频</span>'}</td>
          <td class="link-cell">${actionHtml}${error ? `<div class="error-note">${error}</div>` : ""}</td>
        </tr>`;
      }).join("");
    }

    function openManualEditor(index) {
      const item = currentResults[index];
      if (!item) return;
      editingIndex = index;
      $("manualTitleInput").value = item.title || "";
      $("manualContentInput").value = item.content || "";
      $("manualImagesInput").value = (item.images || []).join("\n");
      $("manualModal").classList.add("show");
      $("manualModal").setAttribute("aria-hidden", "false");
      $("manualTitleInput").focus();
    }

    function closeManualEditor() {
      editingIndex = -1;
      $("manualModal").classList.remove("show");
      $("manualModal").setAttribute("aria-hidden", "true");
    }

    function openImageViewer(index) {
      const item = currentResults[index];
      if (!item) return;
      const images = item.images || [];
      const downloaded = item.downloaded_images || [];
      $("imageHelp").textContent = `${item.title || item.note_id || "当前笔记"} · ${images.length} 张图片`;
      $("imageGrid").innerHTML = images.length
        ? images.map((url, imageIndex) => {
            const safeUrl = escapeHtml(url);
            const localHref = localOutputHref(downloaded[imageIndex] || "");
            const previewUrl = localHref || `/image-proxy?url=${encodeURIComponent(url)}`;
            const local = downloaded[imageIndex] && !String(downloaded[imageIndex]).startsWith("FAILED ")
              ? `<a href="${escapeHtml(localHref || downloaded[imageIndex])}" target="_blank">本地文件</a>`
              : "";
            return `<div class="image-item">
              <a href="${safeUrl}" target="_blank"><img src="${escapeHtml(previewUrl)}" alt="图片 ${imageIndex + 1}" loading="lazy"></a>
              <a href="${safeUrl}" target="_blank">原图链接 ${imageIndex + 1}</a>
              ${local}
            </div>`;
          }).join("")
        : '<div class="empty-state">没有图片。</div>';
      $("imageModal").classList.add("show");
      $("imageModal").setAttribute("aria-hidden", "false");
    }

    function closeImageViewer() {
      $("imageModal").classList.remove("show");
      $("imageModal").setAttribute("aria-hidden", "true");
      $("imageGrid").innerHTML = "";
    }

    function openVideoViewer(index) {
      const item = currentResults[index];
      if (!item) return;
      const videos = item.videos || [];
      const downloaded = item.downloaded_videos || [];
      $("videoHelp").textContent = `${item.title || item.note_id || "当前笔记"} · ${videos.length} 个视频`;
      $("videoGrid").innerHTML = videos.length
        ? videos.map((url, videoIndex) => {
            const safeUrl = escapeHtml(url);
            const localHref = localOutputHref(downloaded[videoIndex] || "");
            const playableUrl = localHref || url;
            const local = downloaded[videoIndex] && !String(downloaded[videoIndex]).startsWith("FAILED ")
              ? `<a href="${escapeHtml(localHref || downloaded[videoIndex])}" target="_blank">本地视频 ${videoIndex + 1}</a>`
              : "";
            return `<div class="image-item">
              <video class="video-player" controls preload="metadata" src="${escapeHtml(playableUrl)}"></video>
              <a href="${safeUrl}" target="_blank">原视频链接 ${videoIndex + 1}</a>
              ${local || '<a href="' + safeUrl + '" target="_blank">打开视频</a>'}
            </div>`;
          }).join("")
        : '<div class="empty-state">没有视频。</div>';
      $("videoModal").classList.add("show");
      $("videoModal").setAttribute("aria-hidden", "false");
    }

    function closeVideoViewer() {
      $("videoModal").classList.remove("show");
      $("videoModal").setAttribute("aria-hidden", "true");
      $("videoGrid").innerHTML = "";
    }

    function localOutputHref(path) {
      if (!path || String(path).startsWith("FAILED ")) return "";
      const marker = "/xhs_output/";
      const index = String(path).indexOf(marker);
      return index >= 0 ? `/output/${String(path).slice(index + marker.length)}` : "";
    }

    async function exportCurrentResults() {
      const res = await fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ results: currentResults })
      });
      const payload = await res.json();
      if (!res.ok) {
        setSummary("导出失败", payload.error || "补录内容保存失败。", currentResults);
        return;
      }
      setSummary("补录已保存", payload.message || "已重新导出。", currentResults);
      renderDownloads(payload.files || {});
    }

    async function copyLink(url) {
      if (!url) return;
      try {
        await navigator.clipboard.writeText(url);
        setSummary("链接已复制", "可以粘贴到浏览器或小红书 App 中打开。", currentResults);
      } catch (err) {
        setSummary("复制失败", url, currentResults);
      }
    }

    function openExternalLink(url) {
      if (!url) return;
      const opened = window.open(url, "_blank", "noopener,noreferrer");
      if (!opened) {
        setSummary("新窗口被拦截", "请点“复制链接”，粘贴到浏览器或小红书 App 中打开。", currentResults);
      }
    }

    function trim(value, max) {
      return value.length > max ? value.slice(0, max - 1) + "..." : value;
    }

    function extractUrls(value) {
      const matches = value.match(/https?:\/\/[^\s，。；、,;~～]+/gi) || [];
      return [...new Set(matches.map((url) => url.trim()))];
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[char]));
    }

    function formatHistoryTitle(id) {
      const match = String(id).match(/^(\d{8})-(\d{6})(?:-(.+))?$/);
      if (!match) return id;
      const date = `${match[1].slice(0, 4)}-${match[1].slice(4, 6)}-${match[1].slice(6, 8)}`;
      const time = `${match[2].slice(0, 2)}:${match[2].slice(2, 4)}:${match[2].slice(4, 6)}`;
      const suffix = match[3] ? ` · ${match[3]}` : "";
      return `${date} ${time}${suffix}`;
    }

    loadHistoryList();
  </script>
</body>
</html>
"""


def fetch_batch(links: list[str], delay: float, timeout: float, download: bool, out_dir: Path) -> list[NoteResult]:
    results: list[NoteResult] = []
    cleaned_links = extract_urls_from_items(links)
    for index, link in enumerate(cleaned_links, start=1):
        try:
            body, final_url, status_code = http_get(link, timeout=timeout)
            result = parse_note(link, body, final_url, status_code)
            if download and result.images:
                download_images(result, out_dir, timeout=timeout)
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
        if index < len(cleaned_links) and delay > 0:
            time.sleep(delay)
    write_outputs(results, out_dir)
    return results


def extract_urls_from_items(items: list[Any]) -> list[str]:
    urls: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        matches = URL_RE.findall(item)
        if matches:
            urls.extend(match.rstrip(").]】》'\"") for match in matches)
        elif item.strip().lower().startswith(("http://", "https://")):
            urls.append(item.strip())
    return unique(urls)


class XhsWebHandler(SimpleHTTPRequestHandler):
    server_version = "XhsBatchUI/1.0"

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib API name.
        if self.path in {"/", "/index.html"}:
            data = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            return
        if self.path.startswith("/output/"):
            self.serve_output_file(self.path.removeprefix("/output/"), head_only=True)
            return
        if self.path.startswith("/assets/"):
            self.serve_asset_file(self.path.removeprefix("/assets/"), head_only=True)
            return
        self.send_error(404, "Not found")

    def do_GET(self) -> None:  # noqa: N802 - stdlib API name.
        if self.path in {"/", "/index.html"}:
            self.send_html(INDEX_HTML)
            return
        if self.path.startswith("/api/history-load"):
            self.handle_history_load()
            return
        if self.path == "/api/history":
            self.handle_history_list()
            return
        if self.path.startswith("/image-proxy"):
            self.serve_proxy_image()
            return
        if self.path.startswith("/output/"):
            self.serve_output_file(self.path.removeprefix("/output/"))
            return
        if self.path.startswith("/assets/"):
            self.serve_asset_file(self.path.removeprefix("/assets/"))
            return
        self.send_error(404, "Not found")

    def do_POST(self) -> None:  # noqa: N802 - stdlib API name.
        if self.path == "/api/browser-start":
            self.handle_browser_start()
            return
        if self.path == "/api/browser-fetch":
            self.handle_browser_fetch()
            return
        if self.path == "/api/export":
            self.handle_export()
            return
        if self.path != "/api/fetch":
            self.send_error(404, "Not found")
            return
        try:
            payload = self.read_json()
            links = payload.get("links") or []
            if not isinstance(links, list) or not links:
                self.send_json({"error": "请提供至少一个链接。"}, status=400)
                return
            links = extract_urls_from_items(links)
            if not links:
                self.send_json({"error": "没有从输入内容里识别到 http 或 https 链接。"}, status=400)
                return
            delay = clamp_float(payload.get("delay", 2), 0, 30)
            timeout = clamp_float(payload.get("timeout", 20), 3, 120)
            download = payload.get("download_images", True) is not False
            run_id = time.strftime("%Y%m%d-%H%M%S")
            out_dir = OUTPUT_ROOT / run_id
            results = fetch_batch(links, delay=delay, timeout=timeout, download=download, out_dir=out_dir)
            files = {
                "csv": f"/output/{run_id}/notes.csv",
                "jsonl": f"/output/{run_id}/notes.jsonl",
                "markdown": f"/output/{run_id}/markdown/",
            }
            self.send_json(
                {
                    "message": f"已处理 {len(results)} 条，文件保存在 {out_dir}",
                    "results": [asdict(result) for result in results],
                    "files": files,
                }
            )
        except Exception as exc:  # noqa: BLE001 - return a readable UI error.
            self.send_json({"error": str(exc)}, status=500)

    def handle_browser_start(self) -> None:
        try:
            debug_url = ensure_login_browser()
            self.send_json(
                {
                    "message": "登录浏览器已打开。扫码登录小红书后，回到工具页点击“开始爬取”。",
                    "debug_url": debug_url,
                    "login_url": "https://www.xiaohongshu.com",
                }
            )
        except Exception as exc:  # noqa: BLE001 - return a readable UI error.
            self.send_json({"error": str(exc)}, status=500)

    def handle_browser_fetch(self) -> None:
        try:
            payload = self.read_json()
            links = payload.get("links") or []
            if not isinstance(links, list) or not links:
                self.send_json({"error": "请提供至少一个链接。"}, status=400)
                return
            links = extract_urls_from_items(links)
            if not links:
                self.send_json({"error": "没有从输入内容里识别到 http 或 https 链接。"}, status=400)
                return
            delay = clamp_float(payload.get("delay", 1.5), 0, 30)
            timeout = clamp_float(payload.get("timeout", 25), 5, 120)
            download = payload.get("download_images", True) is not False
            run_id = time.strftime("%Y%m%d-%H%M%S-browser")
            out_dir = OUTPUT_ROOT / run_id
            results = fetch_with_logged_in_browser(links, delay=delay, timeout=timeout)
            if download:
                for result in results:
                    if result.images:
                        download_images(result, out_dir, timeout=timeout)
                    if result.videos:
                        download_videos(result, out_dir, timeout=timeout)
            write_outputs(results, out_dir)
            self.send_json(
                {
                    "message": f"浏览器辅助爬取 {len(results)} 条，文件保存在 {out_dir}",
                    "results": results_as_dicts(results),
                    "files": {
                        "csv": f"/output/{run_id}/notes.csv",
                        "jsonl": f"/output/{run_id}/notes.jsonl",
                        "markdown": f"/output/{run_id}/markdown/",
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001 - return a readable UI error.
            self.send_json({"error": str(exc)}, status=500)

    def handle_export(self) -> None:
        try:
            payload = self.read_json()
            raw_results = payload.get("results") or []
            if not isinstance(raw_results, list) or not raw_results:
                self.send_json({"error": "没有可导出的结果。"}, status=400)
                return
            results = [note_result_from_dict(item) for item in raw_results if isinstance(item, dict)]
            if not results:
                self.send_json({"error": "结果格式不正确。"}, status=400)
                return
            run_id = time.strftime("%Y%m%d-%H%M%S-manual")
            out_dir = OUTPUT_ROOT / run_id
            write_outputs(results, out_dir)
            self.send_json(
                {
                    "message": f"已重新导出 {len(results)} 条，文件保存在 {out_dir}",
                    "files": {
                        "csv": f"/output/{run_id}/notes.csv",
                        "jsonl": f"/output/{run_id}/notes.jsonl",
                        "markdown": f"/output/{run_id}/markdown/",
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001 - return a readable UI error.
            self.send_json({"error": str(exc)}, status=500)

    def handle_history_list(self) -> None:
        try:
            runs = []
            if OUTPUT_ROOT.exists():
                for path in OUTPUT_ROOT.iterdir():
                    if not path.is_dir() or not (path / "notes.jsonl").exists():
                        continue
                    results = read_results_jsonl(path / "notes.jsonl")
                    first = next((item for item in results if item.title or item.content or item.source_url), None)
                    ok_count = sum(1 for item in results if item.status in {"ok", "manual"})
                    failed_count = len(results) - ok_count
                    title = (first.title if first else "") or (first.content if first else "") or path.name
                    snippet_parts = []
                    if first and first.author:
                        snippet_parts.append(f"博主：{first.author}")
                    if first and first.content:
                        snippet_parts.append(first.content)
                    elif first and first.source_url:
                        snippet_parts.append(first.source_url)
                    runs.append(
                        {
                            "id": path.name,
                            "label": f"{path.name} · {len(results)} 条",
                            "count": len(results),
                            "ok": ok_count,
                            "failed": failed_count,
                            "title": trim_text(title, 42),
                            "snippet": trim_text(" · ".join(snippet_parts), 110),
                            "mtime": path.stat().st_mtime,
                        }
                    )
            runs.sort(key=lambda item: item["mtime"], reverse=True)
            self.send_json({"runs": runs[:50]})
        except Exception as exc:  # noqa: BLE001 - return a readable UI error.
            self.send_json({"error": str(exc)}, status=500)

    def handle_history_load(self) -> None:
        try:
            parsed = urllib.parse.urlparse(self.path)
            run_id = (urllib.parse.parse_qs(parsed.query).get("id") or [""])[0]
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id):
                self.send_json({"error": "历史记录 ID 不合法。"}, status=400)
                return
            out_dir = (OUTPUT_ROOT / run_id).resolve()
            if not str(out_dir).startswith(str(OUTPUT_ROOT.resolve())) or not (out_dir / "notes.jsonl").exists():
                self.send_json({"error": "历史记录不存在。"}, status=404)
                return
            results = read_results_jsonl(out_dir / "notes.jsonl")
            self.send_json(
                {
                    "message": f"已载入 {run_id}，共 {len(results)} 条。",
                    "results": [asdict(result) for result in results],
                    "files": {
                        "csv": f"/output/{run_id}/notes.csv",
                        "jsonl": f"/output/{run_id}/notes.jsonl",
                        "markdown": f"/output/{run_id}/markdown/",
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001 - return a readable UI error.
            self.send_json({"error": str(exc)}, status=500)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8") or "{}")

    def send_html(self, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def serve_output_file(self, relative: str, head_only: bool = False) -> None:
        target = (OUTPUT_ROOT / relative).resolve()
        if not str(target).startswith(str(OUTPUT_ROOT.resolve())) or not target.exists():
            self.send_error(404, "Not found")
            return
        if target.is_dir():
            entries = sorted(target.iterdir())
            body = "<!doctype html><meta charset='utf-8'><title>输出文件</title><ul>"
            for entry in entries:
                href = self.path.rstrip("/") + "/" + entry.name
                body += f"<li><a href='{href}'>{entry.name}</a></li>"
            body += "</ul>"
            self.send_html(body)
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        file_size = target.stat().st_size
        range_header = self.headers.get("Range", "")
        start = 0
        end = file_size - 1
        status = 200
        if range_header.startswith("bytes="):
            match = re.fullmatch(r"(\d*)-(\d*)", range_header.removeprefix("bytes="))
            if not match:
                self.send_error(416, "Invalid range")
                return
            if match.group(1):
                start = int(match.group(1))
            if match.group(2):
                end = int(match.group(2))
            if not match.group(1) and match.group(2):
                suffix = int(match.group(2))
                start = max(0, file_size - suffix)
                end = file_size - 1
            if start > end or start >= file_size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return
            end = min(end, file_size - 1)
            status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        if not content_type.startswith(("text/html", "video/", "image/")):
            self.send_header("Content-Disposition", f'attachment; filename="{target.name}"')
        self.send_header("Content-Length", str(length))
        self.end_headers()
        if head_only:
            return
        with target.open("rb") as file:
            file.seek(start)
            remaining = length
            while remaining > 0:
                chunk = file.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def serve_asset_file(self, relative: str, head_only: bool = False) -> None:
        target = (ASSETS_ROOT / relative).resolve()
        if not str(target).startswith(str(ASSETS_ROOT.resolve())) or not target.exists() or target.is_dir():
            self.send_error(404, "Not found")
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "max-age=86400")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head_only:
            self.wfile.write(data)

    def serve_proxy_image(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        url = (params.get("url") or [""])[0]
        if not url.startswith(("http://", "https://")):
            self.send_error(400, "Bad image URL")
            return
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
                    ),
                    "Referer": "https://www.xiaohongshu.com/",
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
                content_type = response.headers.get("Content-Type") or "image/jpeg"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "max-age=3600")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:  # noqa: BLE001 - image preview should fail visibly.
            self.send_error(502, f"Image proxy failed: {exc}")

    def log_message(self, format: str, *args: Any) -> None:
        return


def clamp_float(value: Any, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = minimum
    return max(minimum, min(maximum, parsed))


def trim_text(value: str, max_len: int) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    return value if len(value) <= max_len else value[: max_len - 1] + "..."


def note_result_from_dict(item: dict[str, Any]) -> NoteResult:
    def str_value(key: str) -> str:
        value = item.get(key, "")
        return value if isinstance(value, str) else ""

    def list_value(key: str) -> list[str]:
        value = item.get(key, [])
        if not isinstance(value, list):
            return []
        return [entry for entry in value if isinstance(entry, str)]

    return NoteResult(
        source_url=str_value("source_url"),
        final_url=str_value("final_url"),
        note_id=str_value("note_id") or note_id_from_url(str_value("final_url") or str_value("source_url")),
        status=str_value("status") or "manual",
        title=str_value("title"),
        content=str_value("content"),
        author=str_value("author"),
        publish_time=str_value("publish_time"),
        likes=str_value("likes"),
        comments=str_value("comments"),
        collects=str_value("collects"),
        shares=str_value("shares"),
        images=list_value("images"),
        downloaded_images=list_value("downloaded_images"),
        videos=list_value("videos"),
        downloaded_videos=list_value("downloaded_videos"),
        error=str_value("error"),
    )


def read_results_jsonl(path: Path) -> list[NoteResult]:
    results: list[NoteResult] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        if isinstance(data, dict):
            results.append(note_result_from_dict(data))
    return results


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run the local Xiaohongshu batch fetcher UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    OUTPUT_ROOT.mkdir(exist_ok=True)
    server = HTTPServer((args.host, args.port), XhsWebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"小红书笔记批量爬取工具已启动：http://{args.host}:{args.port}")
    print("按 Ctrl+C 退出。")
    try:
        while thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n正在关闭服务...")
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
