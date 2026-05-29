#!/usr/bin/env python3
"""
Desktop launcher for the Xiaohongshu batch crawler.

It starts the local web UI and opens it in an embedded desktop window when
pywebview is available. A browser fallback is kept for development machines
without the desktop WebView dependency.
"""

from __future__ import annotations

import socket
import threading
import tkinter as tk
import sys
import webbrowser
from http.server import HTTPServer
from pathlib import Path

from xhs_web_app import OUTPUT_ROOT, XhsWebHandler


APP_NAME = "小红书笔记批量爬取工具"


class LocalServer:
    def __init__(self) -> None:
        self.server: HTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.url = ""

    def start(self) -> str:
        if self.server:
            return self.url
        OUTPUT_ROOT.mkdir(exist_ok=True)
        port = find_free_port(8765)
        self.server = HTTPServer(("127.0.0.1", port), XhsWebHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{port}"
        return self.url

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None


def run_embedded_app() -> bool:
    try:
        import webview
    except Exception:
        return False

    server = LocalServer()
    url = server.start()
    icon_path = resource_path("assets/app_icon.png")
    window_options = {
        "title": APP_NAME,
        "url": url,
        "width": 1320,
        "height": 880,
        "min_size": (980, 680),
    }
    if icon_path.exists():
        window_options["background_color"] = "#f6f7f9"
    webview.create_window(**window_options)
    try:
        webview.start()
    finally:
        server.stop()
    return True


class DesktopLauncher:
    def __init__(self) -> None:
        self.local_server = LocalServer()
        self.url = ""

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("420x220")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.stop_and_close)
        self.set_window_icon()

        self.status = tk.StringVar(value="正在启动服务...")
        self.url_text = tk.StringVar(value="")

        tk.Label(self.root, text=APP_NAME, font=("Arial", 18, "bold")).pack(pady=(24, 8))
        tk.Label(self.root, textvariable=self.status, fg="#586174").pack()
        tk.Label(self.root, textvariable=self.url_text, fg="#3561a7").pack(pady=(4, 16))

        buttons = tk.Frame(self.root)
        buttons.pack()
        tk.Button(buttons, text="打开界面", width=12, command=self.open_ui).grid(row=0, column=0, padx=6)
        tk.Button(buttons, text="停止并退出", width=12, command=self.stop_and_close).grid(row=0, column=1, padx=6)

        self.root.after(100, self.start_server)

    def start_server(self) -> None:
        self.url = self.local_server.start()
        self.status.set("服务已启动")
        self.url_text.set(self.url)
        self.open_ui()

    def set_window_icon(self) -> None:
        try:
            icon_path = resource_path("assets/app_icon.png")
            if icon_path.exists():
                self.icon_image = tk.PhotoImage(file=str(icon_path))
                self.root.iconphoto(True, self.icon_image)
        except Exception:
            return

    def open_ui(self) -> None:
        if self.url:
            webbrowser.open(self.url)

    def stop_and_close(self) -> None:
        self.local_server.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def find_free_port(preferred: int) -> int:
    for port in [preferred, *range(8766, 8799)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("没有可用端口。")


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


if __name__ == "__main__":
    if not run_embedded_app():
        DesktopLauncher().run()
