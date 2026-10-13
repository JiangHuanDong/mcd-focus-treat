---
name: mcd-focus-treat
description: 麦麦专注钟——专注计时、奖励餐推荐、优惠券优化与到店自取下单。当用户提到"专注/番茄钟/学习计时/工作计时/犒劳自己/奖励餐/麦当劳点什么/帮我点麦当劳"等场景时使用。
---

# 麦麦专注钟 · mcd-focus-treat

「专注换犒劳」：完成一段专注 → 按专注时长与饿度，从麦当劳真实门店菜单里挑一份奖励餐
→ 自动匹配优惠券、用官方价格接口试算最优价 → 用户确认后一键下单。

## 前置条件

1. 已申请麦当劳 MCP Token：https://open.mcd.cn/mcp （手机号登录 → 控制台 → 激活）
2. 已配置环境变量：

```bash
# Windows PowerShell
$env:MCD_MCP_TOKEN = "你的 Token"
# macOS / Linux
export MCD_MCP_TOKEN="你的 Token"
```

（或在 WorkBuddy 的「自定义连接器」中配置 `mcp-config.example.json` 的内容，以连接器方式使用）

## 标准工作流

### 1. 开始专注

用户说"我要专注 45 分钟写周报"：

```bash
python scripts/focus.py start 45 --tag "写周报"
```

### 2. 结算专注

到点后（或用户说"完成了/结算"）：

```bash
python scripts/focus.py finish --json
```

从输出中读取本次奖励档位（snack / standard / deluxe / feast）。

### 3. 推荐奖励（试算，不下单）

```bash
python scripts/reward.py --city <城市> --keyword <地标> [--hunger 1-5] [--prefer 咖啡] [--json]
```

- 已知常用门店可加 `--store-code <门店编码>` 跳过搜索
- `--tier auto` 会自动读取最近一次专注的档位（默认行为）

向用户展示：推荐组合、原价 / 实付 / 省额、参考热量、取餐方式、备选方案。
**必须明确告知：这是试算，没有下单。**

### 4. 用户明确确认后才下单

```bash
python scripts/reward.py --store-code <门店编码> --tier <档位> --place --take-way take-in-store
```

- 下单成功会返回订单信息与支付链接，**付款由用户本人完成**
- 取餐方式：`eat-in`（堂食）/ `take-in-store`（外带）/ `take-dt-quick`（得来速）

### 5. 战报

```bash
python scripts/report.py                 # 终端战报
python scripts/report.py --svg 战报.svg   # 生成可分享的 SVG 卡片
```

## 行为准则（必须遵守）

- **默认试算，永不自动下单**；`--place` 必须得到用户明确确认（"下单/确认/买"之类的话）
- 下单前必须把**实付金额**讲清楚
- 永不展示、记录、上传 `MCD_MCP_TOKEN` 或任何凭据
- 营养与热量数据仅供参考，不做医疗或营养建议
- 价格、供应状态以麦当劳官方实时结果为准；本项目**非麦当劳官方产品**

## 文件说明

| 文件 | 用途 |
|---|---|
| `scripts/focus.py` | 专注会话状态机（start/status/finish/cancel/log/stats） |
| `scripts/reward.py` | 奖励引擎（门店/菜单/券优化/试算/下单） |
| `scripts/report.py` | 战报与段位卡片（含 SVG 生成） |
| `scripts/mcd_client.py` | 麦当劳 MCP 客户端（纯标准库，零依赖） |
| `scripts/smoke_test.py` | 连通性自检 |
| `mcp-config.example.json` | 连接器配置示例（仅环境变量占位符） |
