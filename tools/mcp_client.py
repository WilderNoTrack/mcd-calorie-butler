"""麦当劳 MCP Server 的最小客户端（Streamable HTTP，纯标准库）。

只在 `record` 命令里用来录制真实数据；评测本身跑在沙盒里，不碰真实账户。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_URL = "https://mcp.mcd.cn"


class MCPError(RuntimeError):
    pass


class MCPClient:
    def __init__(self, token: str | None = None, url: str = DEFAULT_URL, timeout: int = 60):
        self.token = token or os.environ.get("MCD_MCP_TOKEN", "")
        if not self.token:
            raise MCPError("缺少 MCD_MCP_TOKEN 环境变量（在 https://open.mcd.cn/mcp 申请）")
        self.url = url
        self.timeout = timeout
        self.session_id: str | None = None
        self._id = 0
        self._initialized = False

    def _post(self, payload: dict) -> dict | None:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(self.url, json.dumps(payload).encode(), headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                self.session_id = resp.headers.get("Mcp-Session-Id") or self.session_id
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise MCPError("401：MCP Token 无效或已过期") from None
            if e.code == 429:
                raise MCPError("429：触发限流（600 次/分钟），稍后再试") from None
            raise
        if not body.strip():
            return None
        if body.lstrip().startswith("{"):
            return json.loads(body)
        # SSE：取最后一条 data
        events = [line[5:].strip() for line in body.splitlines() if line.startswith("data:")]
        return json.loads(events[-1]) if events else None

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        msg = self._post({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}})
        if msg is None:
            raise MCPError(f"{method} 无响应")
        if "error" in msg:
            raise MCPError(f"{method} 出错：{msg['error']}")
        return msg["result"]

    def initialize(self) -> None:
        if self._initialized:
            return
        self._rpc("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "mcbench", "version": "0.1.0"},
        })
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._initialized = True

    def list_tools(self) -> list[dict]:
        self.initialize()
        return self._rpc("tools/list")["tools"]

    def call_text(self, name: str, arguments: dict | None = None) -> str:
        self.initialize()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        return "".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")


def original_json(text: str) -> dict | None:
    """官方大多数工具把 JSON 包在一段 Markdown 说明后面，这里把它抠出来。"""
    marker = "## Original Response"
    if marker in text:
        text = text.split(marker, 1)[1]
    start = text.find('{"success"')
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj
    except json.JSONDecodeError:
        return None


def preamble(text: str) -> str:
    """工具返回里 JSON 之前的那段字段说明，沙盒原样复用，让模型看到和真实服务一样的格式。"""
    i = text.find('{"success"')
    return text[:i] if i >= 0 else ""
