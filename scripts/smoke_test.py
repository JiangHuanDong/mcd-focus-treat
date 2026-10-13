#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smoke_test.py — 麦当劳 MCP 连通性与工具清单冒烟测试

用法：
    python scripts/smoke_test.py                 # 握手 + 列出全部工具
    python scripts/smoke_test.py --dump out.json # 并把工具 schema 导出为 JSON

需要环境变量 MCD_MCP_TOKEN；可选 MCD_PROXY 控制代理（见 mcd_client.py）
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcd_client import McdMcpClient, McpError  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="麦当劳 MCP 冒烟测试")
    ap.add_argument("--dump", default="", help="将 tools/list 结果导出为 JSON 文件")
    args = ap.parse_args()

    client = McdMcpClient()
    init = client.initialize() or {}
    info = init.get("serverInfo", {}) if isinstance(init, dict) else {}
    print(f"[OK] 已握手: server={info.get('name')} version={info.get('version')} "
          f"protocol={init.get('protocolVersion')}")

    tools = client.list_tools()
    print(f"[OK] 工具数量: {len(tools)}")
    for t in tools:
        print("  -", t.get("name"))

    # 顺手验证一个零成本只读工具
    try:
        now = client.call_tool_text("now-time-info", {})
        print("[OK] now-time-info ->", now.strip()[:120])
    except McpError as e:
        print("[WARN] now-time-info 调用失败:", e)

    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as f:
            json.dump(tools, f, ensure_ascii=False, indent=2)
        print(f"[OK] 工具 schema 已导出 -> {args.dump}")


if __name__ == "__main__":
    try:
        main()
    except McpError as e:
        print("[FAIL]", e)
        sys.exit(1)
