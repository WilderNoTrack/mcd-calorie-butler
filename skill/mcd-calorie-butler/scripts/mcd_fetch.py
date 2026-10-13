#!/usr/bin/env python3
"""直接调用麦当劳 MCP 的只读工具，把返回原样存成文件，交给 butler.py。

为什么需要它：营养表、菜单、套餐详情的返回很长（单个几万字），让 AI 把工具结果原样抄进文件既慢又容易抄错。
这个脚本直连 https://mcp.mcd.cn 取数落盘。只允许只读工具；下单（create-order）必须由 AI 通过 MCP 连接器、
在用户确认后调用，这里不提供。

用法：python scripts/mcd_fetch.py <工具名> <输出文件> ['{"参数":"JSON"}']
  python scripts/mcd_fetch.py list-nutrition-foods ~/.mcd-calorie-butler/tmp/nutrition.txt
  python scripts/mcd_fetch.py query-meals meals.txt '{"storeCode":"1450441","orderType":1,"beType":1}'

Token 读取顺序：环境变量 MCD_MCP_TOKEN → WorkBuddy 的 ~/.workbuddy/mcp.json 里 mcd-mcp 的 Authorization。
Token 不会被打印或写入输出文件。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://mcp.mcd.cn"
READ_ONLY = {
    "now-time-info", "list-nutrition-foods", "query-nearby-stores", "query-meals", "query-meal-detail",
    "calculate-price", "query-store-coupons", "query-my-coupons", "available-coupons", "query-my-account",
    "campaign-calendar", "order-list", "query-order", "delivery-query-addresses", "delivery-query-stores",
}


def find_token() -> str:
    token = os.environ.get("MCD_MCP_TOKEN", "").strip()
    if token:
        return token
    cfg = Path.home() / ".workbuddy" / "mcp.json"
    try:
        servers = json.loads(cfg.read_text(encoding="utf-8")).get("mcpServers", {})
    except (OSError, json.JSONDecodeError):
        servers = {}
    for name, s in servers.items():
        if "mcd.cn" in str(s.get("url", "")) or name == "mcd-mcp":
            auth = (s.get("headers") or {}).get("Authorization", "")
            if auth.startswith("Bearer ") and "${" not in auth:
                return auth[len("Bearer "):].strip()
    raise SystemExit("找不到麦当劳 MCP Token：请设置环境变量 MCD_MCP_TOKEN，或先在 WorkBuddy 里配置 mcd-mcp 连接器")


class Client:
    def __init__(self, token: str):
        self.token, self.session, self.n = token, None, 0

    def post(self, payload: dict):
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(URL, json.dumps(payload).encode(), headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                self.session = r.headers.get("Mcp-Session-Id") or self.session
                body = r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            msg = {401: "Token 无效或已过期", 429: "触发限流（每分钟 600 次），稍后再试"}.get(e.code, f"HTTP {e.code}")
            raise SystemExit(f"麦当劳 MCP 请求失败：{msg}") from None
        except urllib.error.URLError as e:
            raise SystemExit(f"连不上 mcp.mcd.cn：{e.reason}") from None
        if not body.strip():
            return None
        if body.lstrip().startswith("{"):
            return json.loads(body)
        data = [l[5:].strip() for l in body.splitlines() if l.startswith("data:")]
        return json.loads(data[-1]) if data else None

    def rpc(self, method: str, params: dict) -> dict:
        self.n += 1
        msg = self.post({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params})
        if not msg or "error" in msg:
            raise SystemExit(f"{method} 出错：{(msg or {}).get('error')}")
        return msg["result"]

    def call(self, tool: str, args: dict) -> str:
        self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                "clientInfo": {"name": "mcd-calorie-butler", "version": "0.2.0"}})
        self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        res = self.rpc("tools/call", {"name": tool, "arguments": args})
        return "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    tool, out = sys.argv[1], Path(sys.argv[2]).expanduser()
    if tool not in READ_ONLY:
        print(json.dumps({"ok": False, "error": f"{tool} 不是只读工具。下单等写操作请通过 MCP 连接器、在用户确认后调用"},
                         ensure_ascii=False))
        return 2
    try:
        args = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
    except json.JSONDecodeError:
        print(json.dumps({"ok": False, "error": "参数要是 JSON，例如 '{\"storeCode\":\"1450441\"}'"}, ensure_ascii=False))
        return 2
    text = Client(find_token()).call(tool, args)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    status = {"ok": True, "tool": tool, "file": str(out), "chars": len(text)}
    i = text.find('{"success"')
    if i >= 0:
        try:
            head, _ = json.JSONDecoder().raw_decode(text[i:])
            status.update(success=head.get("success"), code=head.get("code"), message=head.get("message"))
            if head.get("success") is False:
                status["ok"] = False
        except json.JSONDecodeError:
            pass
    print(json.dumps(status, ensure_ascii=False))
    return 0 if status["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
