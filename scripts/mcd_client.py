#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcd_client.py — 麦当劳 MCP 极简客户端（纯标准库实现，零依赖）

特点：
- Streamable HTTP 传输（https://mcp.mcd.cn）
- JSON-RPC 2.0 消息 + SSE(text/event-stream) 响应解析
- 会话管理（Mcp-Session-Id）
- 纯 Python 标准库，无任何第三方依赖，可直接在沙箱运行

环境变量：
- MCD_MCP_TOKEN   必需。麦当劳开放平台申请的 MCP Token
- MCD_MCP_URL     可选。默认 https://mcp.mcd.cn
- MCD_PROXY       可选。代理设置："direct"=不走代理；其他值=代理地址（如 http://127.0.0.1:10808）；
                  未设置时使用系统默认（urllib 会自动读取 http_proxy/https_proxy 环境变量）

CLI 用法：
    python mcd_client.py list                     # 列出服务端全部工具
    python mcd_client.py call <tool> '<json参数>'  # 调用工具，如：
    python mcd_client.py call now-time-info '{}'
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "https://mcp.mcd.cn"
CLIENT_NAME = "mcd-focus-treat"
CLIENT_VERSION = "0.1.0"


class McpError(Exception):
    """MCP 调用异常（网络/协议/业务错误统一封装）"""


class McdMcpClient:
    def __init__(self, token=None, url=None, timeout=30):
        self.token = (token or os.environ.get("MCD_MCP_TOKEN", "")).strip()
        if not self.token:
            raise McpError(
                "缺少 MCD_MCP_TOKEN。请前往 https://open.mcd.cn/mcp 申请 Token，"
                "并设置环境变量 MCD_MCP_TOKEN"
            )
        self.url = (url or os.environ.get("MCD_MCP_URL", DEFAULT_URL)).strip()
        self.timeout = timeout
        self.session_id = None
        self._id = 0

        proxy = os.environ.get("MCD_PROXY", "").strip()
        if proxy.lower() in ("direct", "none", "off"):
            self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        elif proxy:
            self._opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy})
            )
        else:
            self._opener = urllib.request.build_opener()  # 默认读取系统代理环境变量

    # ---------- 底层 ----------
    def _next_id(self):
        self._id += 1
        return self._id

    def _request(self, payload, expect_response=True):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + self.token,
            "User-Agent": f"{CLIENT_NAME}/{CLIENT_VERSION}",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            resp = self._opener.open(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            hint = {401: "Token 无效或已过期", 429: "请求过于频繁（限 600 次/分钟）"}.get(e.code, "")
            raise McpError(f"HTTP {e.code} {hint} {detail[:300]}".strip()) from None
        except urllib.error.URLError as e:
            raise McpError(f"网络错误: {e.reason}") from None

        sid = resp.headers.get("Mcp-Session-Id")
        if sid:
            self.session_id = sid
        if not expect_response:
            resp.read()
            return None
        raw = resp.read().decode("utf-8", "replace")
        if not raw.strip():
            return None
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "text/event-stream" in ctype:
            return self._parse_sse(raw, payload.get("id"))
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return self._parse_sse(raw, payload.get("id"))
        return self._extract(data)

    @staticmethod
    def _extract(data):
        if not isinstance(data, dict):
            return data
        if "error" in data:
            err = data["error"]
            if isinstance(err, dict):
                raise McpError(f"RPC错误 {err.get('code')}: {err.get('message')}")
            raise McpError(str(err))
        return data.get("result", data)

    @staticmethod
    def _parse_sse(text, req_id):
        events, cur = [], []
        for line in text.splitlines():
            if line.strip() == "":
                if cur:
                    events.append("\n".join(cur))
                    cur = []
            elif line.startswith("data:"):
                cur.append(line[5:].lstrip())
        if cur:
            events.append("\n".join(cur))
        for chunk in events:
            try:
                data = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("id") == req_id:
                return McdMcpClient._extract(data)
        return None

    # ---------- 协议 ----------
    def initialize(self):
        """握手：initialize + notifications/initialized"""
        proto = os.environ.get("MCD_PROTOCOL_VERSION", "2025-06-18")
        result = self._request(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": proto,
                    "capabilities": {},
                    "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
                },
            }
        )
        self._request(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            expect_response=False,
        )
        return result

    def ping(self):
        return self._request({"jsonrpc": "2.0", "id": self._next_id(), "method": "ping", "params": {}})

    def list_tools(self):
        result = self._request(
            {"jsonrpc": "2.0", "id": self._next_id(), "method": "tools/list", "params": {}}
        )
        return (result or {}).get("tools", [])

    def call_tool(self, name, arguments=None):
        return self._request(
            {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            }
        )

    def call_tool_text(self, name, arguments=None):
        """调用工具并提取文本内容（便于直接展示/解析）"""
        res = self.call_tool(name, arguments) or {}
        parts = []
        for c in res.get("content", []) or []:
            if isinstance(c, dict) and c.get("type") == "text":
                parts.append(c.get("text", ""))
        if not parts and isinstance(res, dict) and "structuredContent" in res:
            return json.dumps(res["structuredContent"], ensure_ascii=False, indent=2)
        return "\n".join(parts)

    _JSON_RE = re.compile(r'\{"success"\s*:')

    def call_tool_json(self, name, arguments=None):
        """调用工具并从返回文本中提取首个 {"success":...} JSON 对象。

        返回 (obj | None, raw_text)。麦当劳 MCP 的返回是"说明文本 + JSON"的混合体，
        业务数据藏在其中的 JSON 里。
        """
        txt = self.call_tool_text(name, arguments)
        m = self._JSON_RE.search(txt)
        if not m:
            return None, txt
        try:
            obj, _ = json.JSONDecoder().raw_decode(txt[m.start():])
            return obj, txt
        except json.JSONDecodeError:
            return None, txt


# ---------- CLI ----------
def main(argv):
    cmd = argv[1] if len(argv) > 1 else "list"
    try:
        client = McdMcpClient()
        if cmd == "list":
            init = client.initialize() or {}
            info = init.get("serverInfo", {}) if isinstance(init, dict) else {}
            proto = init.get("protocolVersion", "?") if isinstance(init, dict) else "?"
            print(f"✔ 已连接 {info.get('name', '?')} v{info.get('version', '?')} (protocol {proto})")
            tools = client.list_tools()
            print(f"工具数量: {len(tools)}")
            for t in tools:
                desc = (t.get("description") or "").replace("\n", " ")[:80]
                print(f"- {t.get('name')}: {desc}")
        elif cmd == "call":
            if len(argv) < 3:
                print("用法: python mcd_client.py call <tool> '<json参数>'")
                return 2
            tool = argv[2]
            args = json.loads(argv[3]) if len(argv) > 3 else {}
            client.initialize()
            print(client.call_tool_text(tool, args))
        else:
            print(__doc__)
            return 2
    except McpError as e:
        print(f"[ERROR] {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
