# MCP 集成说明（MCP_INTEGRATION.md）

本文档说明「麦麦专注钟 · mcd-focus-treat」实际使用的麦当劳 MCP Server、Tool、调用流程与业务价值。

## 1. MCP Server 接入

| 项目 | 说明 |
|---|---|
| 服务 | 麦当劳中国官方 MCP Server（`mcd-mcp`） |
| 接入地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP（JSON-RPC 2.0 + SSE 响应） |
| 协议版本 | `2025-06-18` |
| 鉴权方式 | 请求头 `Authorization: Bearer <MCD_MCP_TOKEN>`（Token 由 https://open.mcd.cn/mcp 免费申请） |
| 客户端实现 | `scripts/mcd_client.py`——纯 Python 标准库自研客户端（含握手、会话管理、SSE 解析、JSON 提取），零第三方依赖 |
| 连接器配置 | `mcp-config.example.json`（脱敏示例，仅环境变量占位符） |

## 2. 使用的 Tools 清单

| Tool | 用途 | 在本项目中的位置 |
|---|---|---|
| `now-time-info` | 获取服务器时间 | 会话时间校准、展示当前时间 |
| `query-nearby-stores` | 按城市+关键词查询到店取餐门店 | 奖励引擎：定位用户门店（storeCode） |
| `query-meals` | 查询门店在售菜单（分类、编码、实时价格） | 奖励引擎：候选餐品池（110+ 商品） |
| `query-meal-detail` | 查询套餐组成与可替换项 | V2 特制功能预留 |
| `list-nutrition-foods` | 160 项餐品营养数据（能量/蛋白质/脂肪/碳水/钠/钙） | 奖励引擎：饿度匹配、热量提示 |
| `query-store-coupons` | 查询【指定门店】可用优惠券（含绑定商品编码） | 奖励引擎：券匹配与优化 |
| `query-my-coupons` | 查询用户卡包全部优惠券 | 展示与去重 |
| `available-coupons` | 查询麦麦省可领取优惠券列表 | 领券建议 |
| `auto-bind-coupons` | 一键领取麦麦省全部可领券 | 用户授权后执行（免费） |
| `query-my-account` | 查询麦积金/积分账户 | 资产展示 |
| `calculate-price` | 商品价格试算（含促销与优惠券） | **核心**：最优价验证、takeWayCode 来源 |
| `create-order` | 创建订单 | `--place` 用户确认后下单（付款本人完成） |
| `order-list` | 历史订单 | V2 复盘功能预留 |

> 覆盖官方 35 个工具中与"点餐→结算→履约"链路相关的 13 个；

## 3. 调用流程（时序）

### 3.1 专注结算（focus finish）

```
focus.py 结算 → 得到 tier（snack/standard/deluxe/feast）
```

### 3.2 奖励推荐（reward.py，默认试算）

```
1. query-nearby-stores(city, keyword)      → 选定门店 storeCode
2. query-meals(storeCode, beType=1, orderType=1)
                                           → 候选餐品池（名称/现价/原价）
3. query-store-coupons(storeCode)          → 门店可用券（含绑定 productCode）
4. list-nutrition-foods()                  → 营养表（本地匹配）
5. [本地确定性算法] 按 档位预算 + 饿度 + 券 + 偏好 打分选品
6. calculate-price(items[附 couponCode/couponId])
                                           → 官方试算：原价 / 优惠 / 实付 / takeWayList
7. 输出方案（组合、省钱金额、热量、取餐方式），等待用户确认
```

### 3.3 下单（仅用户确认后）

```
create-order(storeCode, beType=1, orderType=1,
             takeWayCode, items, needTableware=false)
  → 返回订单信息与支付链接 → 用户本人完成支付
```

## 4. 关键技术要点与实测发现

1. **券的传入方式**：优惠券通过 `items[].couponCode` + `items[].couponId` 传入试算/下单接口；
   券与商品通过 `products[].productCode` 绑定，可精确匹配。
2. **自动促销**：`calculate-price` 会自动应用店内优惠（如"第二杯半价"）。
   实测：两杯饮品 ¥40 → 实付 ¥30.5，无需客户自行计算促销叠加。
3. **到店取餐流程**：`beType=1`（到店自取）场景下**不传 `beCode`**；
   下单必须携带 `takeWayCode`，取值来自 `calculate-price` 返回的
   `takeWayList[].code`（`eat-in` / `take-in-store` / `take-dt-quick`）。
4. **门店查询前置条件**：`searchType=2` 时必须提供城市 + 关键词；
   用户收藏门店为空时无法用 `searchType=1`。
5. **价格单位**：`calculate-price` 返回**分**；菜单接口返回**元（字符串）**。
   客户端已统一为"分"做算术、统一格式化展示（开发中修复过此处单位混用 bug）。
6. **限流**：官方限流 600 次/分钟；本项目单次推荐调用约 5-6 个 Tool，天然安全。

## 5. 业务价值

- **行为闭环**：把"自律（专注）"与"真实消费决策"打通——专注时长直接决定奖励预算档位，
  让点餐成为对自律的正反馈，而不是随手消费。
- **真金白银省钱**：券匹配 + 官方价格试算 + 自动促销，让每一单都吃到当前最优价。
  实测案例：小食档用"9.9元冰美式"券 → 原价 ¥22 实付 **¥12.90**（省 ¥9.1）。
- **理性点餐**：结合 160 项营养数据按"饿度"匹配热量区间，避免无意识过量摄入。
- **安全默认**：默认 dry-run 试算，只有用户明确确认才创建订单，付款完全由用户完成——
  杜绝"AI 乱花钱"。

## 6. 实测样例（真实运行输出）

案例 A · 标准档（南京河西万达店）：

```text
🎁 奖励方案 · 标准档（预算 ≤25元 · 饿度3/5）
🏪 麦当劳南京河西万达餐厅（1990095｜距离约115米）
  • 巨无霸 ×1   原价 ¥26.50  ~513kcal
💰 原价 ¥26.50  →  实付 ¥26.50
```

案例 B · 小食档 + 优惠券（省 ¥9.1）：

```text
🎁 奖励方案 · 小食档（预算 ≤15元 · 饿度2/5）
  • 麦咖啡™美式 ×1   原价 ¥11.90  [9.9元中杯冰美式]
  • 韩式烟熏芝士风味酱 ×1   原价 ¥3.00
💰 原价 ¥22.00  →  实付 ¥12.90   共省 ¥9.10
```

---

*本项目为「麦当劳程序员创意开发大赛」参赛作品，非麦当劳官方产品。
价格、供应状态与优惠信息以麦当劳官方实时结果为准。*
