"""演示页的本地服务：提供静态页面，以及 /api/estimate（用大模型估算非麦当劳食物的热量）。

API Key 只在服务端读取（环境变量 DEEPSEEK_API_KEY），不会发给浏览器。
用法：python tools/demo_server.py [端口]
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "docs"
MAX_INPUT = 200
MIN_INTERVAL = 1.5  # 同一 IP 两次估算的最短间隔（秒）

SYSTEM = (
    "你是营养估算助手。用户会用一句话描述吃了什么。把它拆成食物条目，按中国常见做法和份量估算每项的热量(kcal)和蛋白质(g)。"
    "只输出 JSON：{\"items\":[{\"name\":\"食物（含估计份量）\",\"kcal\":整数,\"protein\":整数}],\"note\":\"一句话说明估算前提\"}。"
    "描述里没提份量就按一人份常规量估算；不是食物的内容忽略；无法判断时 items 为空数组并在 note 说明。"
)


def load_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key and sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                key = winreg.QueryValueEx(k, "DEEPSEEK_API_KEY")[0]
        except OSError:
            pass
    return key


API_KEY = load_key()
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
_last: dict[str, float] = {}


def estimate(text: str) -> dict:
    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        BASE_URL + "/chat/completions", json.dumps(body).encode(),
        {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        data = json.load(resp)
    out = json.loads(data["choices"][0]["message"]["content"])
    items = [
        {"name": str(i.get("name", ""))[:40], "kcal": max(0, int(i.get("kcal", 0))), "protein": max(0, int(i.get("protein", 0)))}
        for i in out.get("items", [])[:8]
    ]
    return {"items": items, "note": str(out.get("note", ""))[:120], "model": MODEL}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):  # 不打印请求内容
        pass

    def _json(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if self.path != "/api/estimate":
            return self._json(404, {"error": "没有这个接口"})
        if not API_KEY:
            return self._json(503, {"error": "服务端没有配置 DEEPSEEK_API_KEY，暂时只能用示例"})
        ip = self.client_address[0]
        now = time.time()
        if now - _last.get(ip, 0) < MIN_INTERVAL:
            return self._json(429, {"error": "太快了，稍等一秒再试"})
        _last[ip] = now
        try:
            length = min(int(self.headers.get("Content-Length", 0)), 4096)
            text = str(json.loads(self.rfile.read(length) or b"{}").get("text", "")).strip()
        except (ValueError, json.JSONDecodeError):
            return self._json(400, {"error": "请求格式不对"})
        if not text:
            return self._json(400, {"error": "先写一句你吃了什么"})
        if len(text) > MAX_INPUT:
            return self._json(400, {"error": f"一句话就够了，最多 {MAX_INPUT} 个字"})
        try:
            return self._json(200, estimate(text))
        except urllib.error.HTTPError as e:
            return self._json(502, {"error": f"大模型服务返回 {e.code}，稍后再试"})
        except (urllib.error.URLError, TimeoutError):
            return self._json(504, {"error": "大模型服务超时，稍后再试"})
        except (KeyError, ValueError, json.JSONDecodeError):
            return self._json(502, {"error": "大模型返回的格式不对，换个说法再试"})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"演示页：http://127.0.0.1:{port}  大模型估算：{'已启用 ' + MODEL if API_KEY else '未配置 Key，仅示例'}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
