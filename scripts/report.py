#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report.py — 麦麦专注钟 · 战报与段位卡片

用法:
  python scripts/report.py                 # 终端战报
  python scripts/report.py --svg out.svg   # 生成可分享的 SVG 战报卡片
  python scripts/report.py --json          # 机器可读输出

数据来源：focus.py 的本地状态文件（默认 ~/.mcd-focus-treat/state.json）
"""
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import focus  # noqa: E402

DAY_FMT = "%Y-%m-%d %H:%M:%S"


def _d(s):
    try:
        return datetime.strptime(s.get("ended_at") or "", DAY_FMT).date()
    except ValueError:
        return None


def gather_stats(state=None):
    state = state if state is not None else focus.load_state()
    done = [s for s in state.get("sessions", []) if s.get("status") == "done"]
    abandoned = [s for s in state.get("sessions", []) if s.get("status") == "abandoned"]

    total_min = sum(s.get("credited_min", 0) for s in done)
    today = datetime.now().date()
    today_min = sum(s.get("credited_min", 0) for s in done if _d(s) == today)
    week_min = sum(s.get("credited_min", 0) for s in done
                   if _d(s) and _d(s) >= today - timedelta(days=6))

    days_set = {_d(s) for s in done if _d(s)}
    streak = 0
    cursor = today if today in days_set else today - timedelta(days=1)
    while cursor in days_set:
        streak += 1
        cursor -= timedelta(days=1)

    last7 = []
    for i in range(6, -1, -1):
        dd = today - timedelta(days=i)
        last7.append({
            "date": dd.strftime("%m/%d"),
            "min": sum(s.get("credited_min", 0) for s in done if _d(s) == dd),
        })

    hours = total_min / 60.0
    thresholds = [0, 5, 20, 50, 100, 200]
    names = ["见习麦苗", "铜牌薯条", "白银麦辣", "黄金巨无霸", "铂金麦门", "麦门大师"]
    cur_i = 0
    for i, t in enumerate(thresholds):
        if hours >= t:
            cur_i = i
    if cur_i >= len(thresholds) - 1:
        progress, next_name, next_need = 1.0, None, 0
    else:
        lo, hi = thresholds[cur_i], thresholds[cur_i + 1]
        progress = (hours - lo) / (hi - lo)
        next_name = names[cur_i + 1]
        next_need = round((hi - hours) * 60)

    return {
        "total_min": total_min,
        "total_hours": round(hours, 2),
        "today_min": today_min,
        "week_min": week_min,
        "streak_days": streak,
        "sessions_done": len(done),
        "sessions_abandoned": len(abandoned),
        "level_index": cur_i,
        "level_name": names[cur_i],
        "level_progress": round(progress, 4),
        "next_level": next_name,
        "next_need_min": next_need,
        "last7": last7,
    }


# ---------- SVG 卡片 ----------
def svg_card(st, path):
    RED, YEL, INK, MUT = "#DA291C", "#FFC72C", "#3A2E2A", "#A08C84"
    W, H = 900, 720
    today_s = datetime.now().strftime("%Y-%m-%d")

    bars = []
    maxm = max([x["min"] for x in st["last7"]] + [1])
    bw, gap, x0, base = 64, 34, 90, 655
    for i, item in enumerate(st["last7"]):
        bh = int(80 * item["min"] / maxm)
        x = x0 + i * (bw + gap)
        fill = YEL if item["min"] > 0 else "#F1E4DD"
        bars.append(f'<rect x="{x}" y="{base - bh}" width="{bw}" height="{max(bh, 5)}" rx="9" fill="{fill}"/>')
        bars.append(f'<text x="{x + bw / 2}" y="{base + 30}" text-anchor="middle" font-size="18" fill="{MUT}">{item["date"]}</text>')
        if item["min"]:
            bars.append(f'<text x="{x + bw / 2}" y="{base - bh - 10}" text-anchor="middle" font-size="17" fill="{INK}">{int(item["min"])}</text>')

    pills = [
        ("今日", f"{st['today_min']} 分钟"),
        ("近7天", f"{st['week_min']} 分钟"),
        ("连续", f"{st['streak_days']} 天"),
        ("完成", f"{st['sessions_done']} 段"),
    ]
    pill_svg, px = [], 90
    for label, val in pills:
        pill_svg.append(f'<rect x="{px}" y="325" width="175" height="76" rx="16" fill="#FFFFFF" stroke="#F2DCD2"/>')
        pill_svg.append(f'<text x="{px + 20}" y="357" font-size="18" fill="{MUT}">{label}</text>')
        pill_svg.append(f'<text x="{px + 20}" y="389" font-size="26" font-weight="bold" fill="{INK}">{val}</text>')
        px += 195

    barw = 720
    fillw = max(6, int(barw * st["level_progress"]))
    if st["next_level"]:
        lv_caption = f'距离【{st["next_level"]}】还需专注 {st["next_need_min"]} 分钟'
    else:
        lv_caption = "已达成最高段位 · 麦门大师"

    num_txt = f"{st['total_hours']}"
    unit_x = 60 + int(len(num_txt) * 46) + 14

    svg = f'''<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" font-family="'PingFang SC','Microsoft YaHei',sans-serif">
<rect width="{W}" height="{H}" fill="#FFF7F3"/>
<rect x="0" y="0" width="{W}" height="140" fill="{RED}"/>
<text x="60" y="66" font-size="24" fill="#FFD9CE">专注换犒劳 · Focus, then treat</text>
<text x="60" y="116" font-size="42" font-weight="bold" fill="#FFFFFF">麦麦专注战报</text>
<text x="{W - 60}" y="66" font-size="20" fill="#FFD9CE" text-anchor="end">{today_s}</text>
<text x="{W - 60}" y="116" font-size="20" fill="#FFD9CE" text-anchor="end">mcd-focus-treat</text>
<text x="60" y="205" font-size="22" fill="{MUT}">累计专注</text>
<text x="60" y="290" font-size="74" font-weight="bold" fill="{RED}">{num_txt}</text>
<text x="{unit_x}" y="290" font-size="28" fill="{INK}">小时</text>
{"".join(pill_svg)}
<text x="90" y="460" font-size="24" fill="{INK}" font-weight="bold">段位：{st["level_name"]}</text>
<text x="810" y="460" font-size="18" fill="{MUT}" text-anchor="end">{lv_caption}</text>
<rect x="90" y="476" width="{barw}" height="22" rx="11" fill="#F1E4DD"/>
<rect x="90" y="476" width="{fillw}" height="22" rx="11" fill="{YEL}"/>
<text x="90" y="545" font-size="20" fill="{MUT}">最近 7 天</text>
{"".join(bars)}
<text x="60" y="708" font-size="15" fill="{MUT}">由 mcd-focus-treat 生成 · 非麦当劳官方产品 · 数据为本地统计</text>
</svg>
'''
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    ET.fromstring(svg)  # XML 合法性校验
    return path


# ---------- 终端输出 ----------
def print_text(st):
    print("📮 麦麦专注战报")
    print("─" * 40)
    print(f"累计专注 {st['total_hours']} 小时 ｜ 今日 {st['today_min']} 分钟 ｜ 近7天 {st['week_min']} 分钟")
    print(f"连续专注 {st['streak_days']} 天 ｜ 完成 {st['sessions_done']} 段 ｜ 放弃 {st['sessions_abandoned']} 段")
    print(f"段位：{st['level_name']}（进度 {st['level_progress'] * 100:.1f}%）")
    if st["next_level"]:
        print(f"      距离【{st['next_level']}】还需 {st['next_need_min']} 分钟")
    spark = " ".join(f"{x['date']}:{int(x['min'])}" for x in st["last7"])
    print(f"最近7天分钟数：{spark}")


def main(argv=None):
    focus._ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="麦麦专注钟 · 战报生成器")
    ap.add_argument("--svg", default="", help="输出 SVG 卡片路径")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    st = gather_stats()
    if args.json:
        print(json.dumps(st, ensure_ascii=False, indent=2))
    else:
        print_text(st)
    if args.svg:
        svg_card(st, args.svg)
        print(f"🖼️ 战报卡片已生成：{args.svg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
