#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reward.py — 麦麦专注钟 · 奖励引擎

根据最近一次专注的档位（或手动指定）与当前饿度，从真实门店菜单中
挑选一份"配得上这次专注"的奖励餐，自动匹配可用优惠券并试算最优价。

用法示例:
  python scripts/reward.py --city 深圳市 --keyword 万象天地
  python scripts/reward.py --store-code 1420864 --tier deluxe --hunger 4
  python scripts/reward.py ... --json          # 机器可读输出
  python scripts/reward.py ... --place         # 真实下单（生成支付链接，需自行确认）

环境变量:
  MCD_MCP_TOKEN  必需（麦当劳 MCP Token）
  MCD_PROXY      可选（direct / 代理地址）
  MCD_STATE_FILE 可选（专注状态文件位置，默认 ~/.mcd-focus-treat/state.json）
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcd_client import McdMcpClient, McpError  # noqa: E402
import focus  # noqa: E402

TIER_BUDGET = {"snack": 15, "standard": 25, "deluxe": 40, "feast": 60}
TIER_LABEL = {"snack": "小食档", "standard": "标准档", "deluxe": "豪华档", "feast": "盛宴档"}
HUNGER_KCAL = {1: (0, 300), 2: (300, 500), 3: (500, 700), 4: (700, 1000), 5: (1000, 10 ** 9)}
MAX_ITEMS = 3


def yuan(cents):
    return f"¥{cents / 100:.2f}"


# ---------- MCP 数据获取 ----------
def fetch_stores(client, city, keyword):
    obj, _ = client.call_tool_json(
        "query-nearby-stores",
        {"beType": 1, "searchType": 2, "city": city, "keyword": keyword},
    )
    if not (obj and obj.get("success")):
        raise McpError(f"门店查询失败：{(obj or {}).get('message') or '未知错误'}")
    return obj.get("data") or []


def fetch_menu(client, store_code):
    obj, _ = client.call_tool_json(
        "query-meals", {"beType": 1, "orderType": 1, "storeCode": store_code}
    )
    if not (obj and obj.get("success")):
        raise McpError(f"菜单查询失败：{(obj or {}).get('message') or '未知错误'}")
    return obj.get("data") or {}


def fetch_store_coupons(client, store_code):
    obj, _ = client.call_tool_json(
        "query-store-coupons", {"beType": 1, "orderType": 1, "storeCode": store_code}
    )
    return (obj or {}).get("data") or []


def fetch_nutrition(client):
    """餐品营养表（160 项）：productName -> {kcal, protein, ...}"""
    obj, _ = client.call_tool_json("list-nutrition-foods", {})
    data = (obj or {}).get("data")
    table = {}
    if isinstance(data, str):
        for line in data.splitlines():
            line = line.strip()
            if not line or line.startswith("[") or line.endswith(":"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 9:
                try:
                    table[parts[0]] = {
                        "kcal": float(parts[3]),
                        "protein": float(parts[4]),
                        "fat": float(parts[5]),
                        "carb": float(parts[6]),
                        "sodium": float(parts[7]),
                        "calcium": float(parts[8]),
                    }
                except ValueError:
                    continue
    return table


def match_nutrition(name, table):
    n = (name or "").replace(" ", "")
    if not n:
        return None
    if n in table:
        return table[n]
    best_key, best_val = "", None
    for k, v in table.items():
        kk = k.replace(" ", "")
        if kk and (kk in n or n in kk) and len(kk) > len(best_key):
            best_key, best_val = kk, v
    return best_val


# ---------- 选品与试算 ----------
def build_candidates(menu, store_coupons, tier, hunger, prefer, nutrition):
    budget = TIER_BUDGET[tier] * 100  # 分
    target = budget * 0.85
    kmin, kmax = HUNGER_KCAL[hunger]

    coupon_map = {}
    for cp in store_coupons:
        for p in cp.get("products") or []:
            pc = str(p.get("productCode") or "")
            if pc:
                coupon_map.setdefault(pc, cp)

    cat_of = {}
    for c in menu.get("categories") or []:
        for m in c.get("meals") or []:
            cat_of[str(m.get("code"))] = (c.get("name") or "").replace("\n", " ")

    out = []
    for code, m in (menu.get("meals") or {}).items():
        try:
            price = round(float(m.get("currentPrice") or 0) * 100)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        name = (m.get("name") or code).replace("\n", " ")
        nut = match_nutrition(name, nutrition)
        cp = coupon_map.get(str(code))

        score, notes = 0.0, []
        score += max(0.0, 1.2 - abs(price - target) / max(budget, 1))
        if price > budget * 1.15:
            score -= 0.8
        if cp:
            score += 1.0
            notes.append("有券")
        if nut:
            kcal = nut["kcal"]
            if kmin <= kcal <= kmax:
                score += 0.9
                notes.append(f"{int(kcal)}kcal")
            else:
                score += 0.2
                notes.append(f"{int(kcal)}kcal")
        else:
            score -= 0.1
        for kw in prefer:
            if kw and (kw in name or kw in cat_of.get(str(code), "")):
                score += 0.8
                notes.append(f"偏好:{kw}")
                break
        out.append({
            "code": str(code), "name": name, "price": price,
            "cat": cat_of.get(str(code), ""), "coupon": cp,
            "score": round(score, 3), "notes": notes, "nutrition": nut,
        })
    out.sort(key=lambda x: (-x["score"], x["price"]))
    return out


def choose_items(candidates, budget):
    if not candidates:
        return []
    picked = [dict(candidates[0])]
    total = picked[0]["price"]
    for c in candidates[1:]:
        if len(picked) >= MAX_ITEMS:
            break
        if total + c["price"] <= budget:
            picked.append(dict(c))
            total += c["price"]
    return picked


def calc_price(client, store_code, items):
    payload = []
    for it in items:
        row = {"productCode": it["code"], "quantity": 1}
        if it.get("coupon"):
            row["couponCode"] = it["coupon"].get("couponCode")
            row["couponId"] = it["coupon"].get("couponId")
        payload.append(row)
    obj, _ = client.call_tool_json(
        "calculate-price",
        {"beType": 1, "orderType": 1, "storeCode": store_code,
         "items": payload, "needTableware": False},
    )
    if not (obj and obj.get("success")):
        raise McpError(f"价格试算失败：{(obj or {}).get('message') or '未知错误'}")
    return obj.get("data") or {}, payload


def place_order(client, store_code, payload_items, take_way):
    obj, _ = client.call_tool_json(
        "create-order",
        {"beType": 1, "orderType": 1, "storeCode": store_code,
         "takeWayCode": take_way, "items": payload_items, "needTableware": False},
    )
    if not (obj and obj.get("success")):
        raise McpError(f"下单失败：{(obj or {}).get('message') or '未知错误'}")
    return obj.get("data") or {}


# ---------- 主流程 ----------
def resolve_tier(requested):
    if requested and requested != "auto":
        return requested, None
    state = focus.load_state()
    last = None
    for s in state.get("sessions", []):
        if s.get("status") == "done" and s.get("ended_at"):
            if last is None or s["ended_at"] > last["ended_at"]:
                last = s
    if last:
        return last.get("tier") or "standard", last
    return "standard", None


def main(argv=None):
    focus._ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="麦麦专注钟 · 奖励引擎")
    ap.add_argument("--city", default="", help="城市名（如 深圳市）")
    ap.add_argument("--keyword", default="", help="位置关键词（如 万象天地）")
    ap.add_argument("--store-code", default="", help="直接指定门店编码，跳过门店搜索")
    ap.add_argument("--tier", default="auto", choices=["auto", "snack", "standard", "deluxe", "feast"])
    ap.add_argument("--hunger", type=int, default=3, choices=[1, 2, 3, 4, 5], help="饿度 1-5")
    ap.add_argument("--prefer", action="append", default=[], help="偏好关键词，可多次：--prefer 咖啡 --prefer 鸡")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--place", action="store_true", help="真实下单（生成支付链接，付款自行完成）")
    ap.add_argument("--take-way", default="take-in-store",
                    choices=["eat-in", "take-in-store", "take-dt-quick"],
                    help="取餐方式：堂食/外带/得来速（仅 --place 时生效）")
    args = ap.parse_args(argv)

    client = McdMcpClient()
    client.initialize()

    tier, last_session = resolve_tier(args.tier)

    # 门店
    store = None
    if args.store_code:
        store = {"storeName": f"自选门店 {args.store_code}", "storeCode": args.store_code, "distance": ""}
    else:
        if not (args.city or args.keyword):
            print("[!] 请提供 --city/--keyword 搜索门店，或直接用 --store-code 指定门店")
            return 2
        stores = fetch_stores(client, args.city, args.keyword)
        if not stores:
            print("[!] 没有找到门店，请调整城市/关键词")
            return 1
        store = stores[0]
    store_code = str(store.get("storeCode"))

    menu = fetch_menu(client, store_code)
    coupons = fetch_store_coupons(client, store_code)
    nutrition = fetch_nutrition(client)

    candidates = build_candidates(menu, coupons, tier, args.hunger, args.prefer, nutrition)
    if args.prefer:
        matched = [c for c in candidates if any(f"偏好:{kw}" in c["notes"] for kw in args.prefer)]
        if matched:
            candidates = matched + [c for c in candidates if c not in matched]
    picked = choose_items(candidates, TIER_BUDGET[tier] * 100)
    if not picked:
        print("[!] 没有挑到合适的餐品")
        return 1

    price_data, payload = calc_price(client, store_code, picked)

    result = {
        "ok": True,
        "tier": {"key": tier, "label": TIER_LABEL[tier], "budget": TIER_BUDGET[tier]},
        "tier_source": (f"最近一次专注：{last_session.get('credited_min')}分钟"
                        if last_session else "手动/默认"),
        "store": {"name": store.get("storeName"), "code": store_code, "distance": store.get("distance")},
        "items": [{
            "code": it["code"], "name": it["name"], "price": it["price"],
            "coupon_title": (it.get("coupon") or {}).get("title"),
            "kcal": (it.get("nutrition") or {}).get("kcal"),
            "cat": it.get("cat"),
        } for it in picked],
        "original_price": price_data.get("originalPrice"),
        "final_price": price_data.get("price"),
        "discount": price_data.get("discount"),
        "take_way_list": price_data.get("takeWayList"),
        "alternatives": [{
            "name": c["name"], "price": c["price"],
            "coupon_title": (c.get("coupon") or {}).get("title"), "notes": c["notes"],
        } for c in candidates[0:6] if c not in picked][:4],
        "place_payload_items": payload,
        "notes": ["价格与供应状态以麦当劳官方实时结果为准；本工具非麦当劳官方产品，仅供参考。"],
    }

    if args.place:
        order = place_order(client, store_code, payload, args.take_way)
        result["order"] = order

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # ---- 人话版输出 ----
    print(f"🎁 奖励方案 · {result['tier']['label']}（预算 ≤{result['tier']['budget']}元 · 饿度{args.hunger}/5）")
    print(f"   {result['tier_source']}")
    dist = f"｜距离约{store.get('distance')}米" if store.get("distance") else ""
    print(f"🏪 {store.get('storeName')}（{store_code}{dist}）")
    print("─" * 46)
    for it in result["items"]:
        tail = f"  [{it['coupon_title']}]" if it["coupon_title"] else ""
        kcal = f"  ~{int(it['kcal'])}kcal" if it["kcal"] else ""
        print(f"  • {it['name']} ×1   原价 {yuan(it['price'])}{tail}{kcal}")
    print("─" * 46)
    op = price_data.get("originalPrice") or 0
    fp = price_data.get("price") or 0
    dc = price_data.get("discount") or 0
    print(f"💰 原价 {yuan(op)}  →  实付 {yuan(fp)}   共省 {yuan(dc)}")
    kcals = [it["kcal"] for it in result["items"] if it["kcal"]]
    if kcals:
        print(f"🔥 参考热量：约 {int(sum(kcals))} kcal（数据仅供参考）")
    if result["take_way_list"]:
        ways = " / ".join(f"{w.get('title')}（{w.get('code')}）" for w in result["take_way_list"])
        print(f"🥡 取餐方式：{ways}")
    if result["alternatives"]:
        print("▼ 备选：")
        for a in result["alternatives"]:
            tail = f" [{a['coupon_title']}]" if a["coupon_title"] else ""
            print(f"   - {a['name']}  {yuan(a['price'])}{tail}")
    if not dc and not any(it["coupon_title"] for it in result["items"]):
        print("💡 提示：你的卡包里暂无可用于本单的券；先把麦麦省的券领了再试，可能更省。")
    if args.place:
        order = result.get("order") or {}
        print("🧾 已下单！订单号：", order.get("orderId") or order.get("orderNo") or order)
        link = order.get("payUrl") or order.get("paymentUrl") or order.get("payLink")
        if link:
            print("💳 支付链接：", link)
    else:
        print("（试算模式。确认下单加 --place；付款由你本人完成）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except McpError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
