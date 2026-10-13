# 麦麦专注钟 · mcd-focus-treat

> **专注换犒劳 —— 专注每一段，犒劳每一餐。**

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)
[![MCP](https://img.shields.io/badge/%E9%BA%A6%E5%BD%93%E5%8A%B3%20MCP-13%20tools-red)](https://open.mcd.cn/mcp)

<img src="https://cdn.jsdelivr.net/gh/JiangHuanDong/mcd-focus-treat@main/docs/assets/report-card.png" width="760" alt="麦麦专注战报卡片示例">

一段专注结束，按你的**专注时长**和**饿度**，从麦当劳真实门店菜单里挑一份配得上你努力的奖励餐：
自动匹配优惠券、叠加店内促销、用官方价格接口试算最优价；确认后一键下单（到店自取）。
累计专注解锁「麦门段位」，生成可分享的战报卡片。

- **真实数据**：门店、菜单、价格、优惠券全部来自**麦当劳官方 MCP**（35 个工具中本项目使用 13 个）
- **零依赖**：纯 Python 标准库，`python scripts/xxx.py` 直接运行
- **不会乱花钱**：默认试算模式；下单必须你本人确认，付款你本人完成
- **双向省钱**：券匹配 + 官方试算 + 自动促销，每一单都吃到当前最优价

> 本项目为「麦当劳程序员创意开发大赛」参赛作品，由 **WorkBuddy** 智能体全程开发（见 [workbuddy.md](workbuddy.md)），**非麦当劳官方产品**。

---

## 核心闭环

```text
        开始专注              到点结算               选品 + 券优化
   ┌───────────────┐    ┌───────────────┐    ┌───────────────────┐
   │ focus start   │ →  │ focus finish  │ →  │     reward.py     │
   │ 25/45/90 分钟  │    │ 生成奖励档位   │    │ 真实菜单/真实券/   │
   └───────────────┘    └───────────────┘    │ 官方价格试算       │
           ↑                                 └─────────┬─────────┘
           │                                           │ 确认后（可选）
           │           战报卡片 / 段位升级               ↓
           └──────────── report.py ←──────────── 一键下单（到店自取）
```

## 快速开始

### 0. 环境要求

Python 3.8+，**无需安装任何第三方包**。

### 1. 申请麦当劳 MCP Token（免费，30 秒）

前往 <https://open.mcd.cn/mcp> → 手机号登录 → 右上角「控制台」→ 激活 → 复制 Token。

### 2. 配置环境变量

```bash
# macOS / Linux
export MCD_MCP_TOKEN="你的 Token"

# Windows PowerShell
$env:MCD_MCP_TOKEN = "你的 Token"
```

（可选）`MCD_PROXY` 控制代理：`direct` 表示不走代理，其他值为代理地址。

### 3. 三步体验

```bash
# ① 连通自检（应看到 35 个工具就位）
python scripts/smoke_test.py

# ② 开始一段 45 分钟专注，到点结算
python scripts/focus.py start 45 --tag "写周报"
python scripts/focus.py finish

# ③ 让它推荐奖励餐（试算，不会真的下单）
python scripts/reward.py --city 南京市 --keyword 建邺区

# ④ 生成战报卡片（可分享）
python scripts/report.py --svg report.svg
```

## 真实运行效果

### 奖励推荐（真实试算）

```text
🎁 奖励方案 · 标准档（预算 ≤25元 · 饿度3/5）
   最近一次专注：45分钟
🏪 麦当劳南京河西万达餐厅（1990095｜距离约115米）
────────────────────────────────────────────
  • 巨无霸 ×1   原价 ¥26.50  ~513kcal
────────────────────────────────────────────
💰 原价 ¥26.50  →  实付 ¥26.50
🥡 取餐方式：堂食（eat-in） / 外带（take-in-store）
```

用上优惠券后（麦麦省「9.9元中杯冰美式」）：

```text
🎁 奖励方案 · 小食档（预算 ≤15元 · 饿度2/5）
  • 麦咖啡™美式 ×1   原价 ¥11.90  [9.9元中杯冰美式]
  • 韩式烟熏芝士风味酱 ×1   原价 ¥3.00
💰 原价 ¥22.00  →  实付 ¥12.90   共省 ¥9.10
```

### 专注结算

```text
🍟 专注开始（写周报）！计划 45 分钟，预计 15:30 结束。
🎉 专注完成！本次 45 分钟
   奖励档位：标准档（建议预算 ≤ 25 元）
   今日 75 分钟 ｜ 累计 370 分钟 ｜ 段位：铜牌薯条
```

### 战报卡片

`python scripts/report.py --svg report.svg` 生成上方示例的分享卡片（SVG 矢量，直接发群/朋友圈）。

## 命令速查

| 命令 | 说明 | 常用参数 |
|---|---|---|
| `python scripts/focus.py start <分钟>` | 开始专注 | `--tag 标签`、`--json` |
| `python scripts/focus.py finish` | 结算并生成奖励档位 | `--force`（不足 60% 强制结算） |
| `python scripts/reward.py` | 推荐奖励餐（试算） | `--city/--keyword`、`--store-code`、`--hunger 1-5`、`--prefer 咖啡`、`--json` |
| `python scripts/reward.py --place` | 真实下单（返回支付链接） | `--take-way eat-in/take-in-store/take-dt-quick` |
| `python scripts/report.py` | 战报与段位 | `--svg 输出.svg`、`--json` |
| `python scripts/smoke_test.py` | 连通性自检 | `--dump tools.json` |

## 奖励档位与段位体系

| 专注时长 | 奖励档位 | 建议预算 |
|---|---|---|
| < 30 分钟 | 小食档 | ≤ 15 元 |
| 30–59 分钟 | 标准档 | ≤ 25 元 |
| 60–119 分钟 | 豪华档 | ≤ 40 元 |
| ≥ 120 分钟 | 盛宴档 | ≤ 60 元 |

| 段位 | 累计专注 |
|---|---|
| 见习麦苗 | < 5 小时 |
| 铜牌薯条 | 5–20 小时 |
| 白银麦辣 | 20–50 小时 |
| 黄金巨无霸 | 50–100 小时 |
| 铂金麦门 | 100–200 小时 |
| 麦门大师 | 200 小时+ |

## 在 WorkBuddy 中使用（推荐玩法）

1. 打开 WorkBuddy → 左侧边栏「专家·技能·连接器」→「连接器」页签
2. 右上角「自定义连接器」→ 配置 MCP → 粘贴 [mcp-config.example.json](mcp-config.example.json) 的内容（替换 Token）
3. 之后即可在对话里直接使用：

```text
你：我要专注 45 分钟写周报
（到点后）你：结算，然后帮我看看奖励点什么
你：确认下单
```

详细技能定义见 [SKILL.md](SKILL.md)。

## 项目结构

```text
mcd-focus-treat/
├── SKILL.md                  # WorkBuddy 技能定义
├── scripts/
│   ├── mcd_client.py         # 麦当劳 MCP 客户端（纯标准库：握手/SSE/会话）
│   ├── focus.py              # 专注状态机（六段位）
│   ├── reward.py             # 奖励引擎（选品/券优化/试算/下单）
│   ├── report.py             # 战报与段位卡片（SVG）
│   └── smoke_test.py         # 连通性自检
├── docs/                     # GitHub Pages 演示页
├── mcp-config.example.json   # 连接器配置示例（仅环境变量占位符）
├── MCP_INTEGRATION.md        # MCP 工具清单与调用流程（大赛要求）
├── workbuddy.md              # WorkBuddy 开发过程存档（大赛要求）
└── CONTEST_DECLARATION.md    # 大赛参赛声明（官方原文）
```

## 技术设计

- **确定性计算 + 智能编排**：价格、券匹配、选品全部用确定性代码；模型只负责理解你的话和编排命令——金额必须可复现、可核验。
- **安全默认**：全链路 dry-run 优先，`--place` 必须显式触发；下单前必报实付金额。
- **零依赖**：MCP 的 Streamable HTTP / SSE / JSON-RPC 全部用标准库实现，可在任意环境开箱运行。
- **隐私优先**：状态存本机（`~/.mcd-focus-treat/state.json`），无服务端；Token 只存环境变量。
- 更多细节见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。

## FAQ

**Q：会真的花钱/下单吗？**
不会。默认是试算模式（只计算、不创建订单）；只有你明确说"下单"后才会创建订单，且付款链接需要你本人完成支付。

**Q：支持麦乐送（外卖）吗？**
当前主推"到店自取"链路；麦乐送需要有已保存的配送地址（麦当劳侧配置）后可扩展。

**Q：数据准确吗？**
门店、菜单、价格、优惠券均为门店实时数据；营养数据来自官方营养库，仅供参考，不作为医疗或营养建议。

**Q：Token 安全吗？**
Token 仅通过环境变量读取，绝不写入仓库、日志或任何文件；本项目所有提交内容均通过占位符引用。

## 参赛信息

- 参赛活动：麦当劳程序员创意开发大赛（McDonald's Developer Innovation Challenge）
- 开发工具：腾讯 WorkBuddy（全过程存档见 [workbuddy.md](workbuddy.md)）
- 本仓库为参赛作品，非麦当劳官方产品；价格与供应状态以麦当劳官方渠道实时结果为准。

## License

[MIT](LICENSE)
