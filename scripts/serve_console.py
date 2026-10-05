# -*- coding: utf-8 -*-
"""系统控制台静态服务（多线程，避免并行加载 187 张队徽时单线程丢连接）。

用法:
    python scripts/serve_console.py [端口] [目录]
默认: 端口 8591, 目录 <项目根>/docs/console
"""
from __future__ import annotations

import functools
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8591
DIRECTORY = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "docs" / "console"


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # 静默：避免控制台刷日志


def main() -> int:
    if not DIRECTORY.is_dir():
        print(f"目录不存在: {DIRECTORY}")
        return 1
    handler = functools.partial(Handler, directory=str(DIRECTORY))
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    httpd.daemon_threads = True
    print(f"控制台服务: http://127.0.0.1:{PORT}  (目录 {DIRECTORY})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    os.chdir(DIRECTORY)
    raise SystemExit(main())
