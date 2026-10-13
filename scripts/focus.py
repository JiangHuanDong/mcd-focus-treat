#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
focus.py — 麦麦专注钟 · 专注会话状态机（纯标准库，零依赖）

命令:
  start <分钟> [--tag 标签]   开始一段专注
  status                      查看当前专注/今日概览
  finish [--force]            结算当前专注，生成奖励索引（tier）
  cancel                      放弃当前专注
  log [--days N]              历史记录
  stats                       累计数据与段位

所有命令支持 --json 输出（机器可读，供 WorkBuddy / reward 引擎消费）。

状态文件: ~/.mcd-focus-treat/state.json（可用环境变量 MCD_STATE_FILE 覆盖）
"""
import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timedelta

STATE_DIR = os.path.join(os.path.expanduser("~"), ".mcd-focus-treat")
STATE_FILE = os.environ.get("MCD_STATE_FILE") or os.path.join(STATE_DIR, "state.json")

# 奖励档位：(最少专注分钟, key, 显示名, 建议价格上限/元)
TIERS = [
    (120, "feast", "盛宴档", 60),
    (60, "deluxe", "豪华档", 40),
    (30, "standard", "标准档", 25),
    (0, "snack", "小食档", 15),
]

# 段位：(累计专注小时下限, 段位名)
LEVELS = [
    (200, "麦门大师"),
    (100, "铂金麦门"),
    (50, "黄金巨无霸"),
    (20, "白银麦辣"),
    (5, "铜牌薯条"),
    (0, "见习麦苗"),
]

MIN_CREDIT_RATIO = 0.6  # 实际时长低于计划的 60% 时视为放弃（不给奖励）


# ---------- 基础 ----------
def _ensure_utf8_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def now():
    return datetime.now()


def iso(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"version": 1, "current": None, "sessions": []}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def tier_for_minutes(minutes):
    for lower, key, name, budget in TIERS:
        if minutes >= lower:
            return {"key": key, "name": name, "budget": budget}
    return {"key": "snack", "name": "小食档", "budget": 15}


def level_for_hours(hours):
    for lower, name in LEVELS:
        if hours >= lower:
            idx = [n for _, n in LEVELS].index(name)
            return {"level": len(LEVELS) - idx, "name": name}
    return {"level": 1, "name": "见习麦苗"}


def done_minutes(state):
    total = 0
    for s in state["sessions"]:
        if s.get("status") == "done":
            total += s.get("credited_min", 0)
    return total


def today_minutes(state):
    today = now().strftime("%Y-%m-%d")
    return sum(
        s.get("credited_min", 0)
        for s in state["sessions"]
        if s.get("status") == "done" and (s.get("ended_at") or "").startswith(today)
    )


# ---------- 命令 ----------
def cmd_start(args):
    state = load_state()
    if state.get("current"):
        print("[!] 已有一段专注进行中，先 finish 或 cancel 再开始新的")
        return 1
    planned = int(args.minutes)
    if planned <= 0 or planned > 600:
        print("[!] 分钟数需在 1~600 之间")
        return 1
    session = {
        "id": uuid.uuid4().hex[:8],
        "tag": args.tag or "",
        "planned_min": planned,
        "started_at": iso(now()),
        "status": "running",
    }
    state["current"] = session
    save_state(state)
    end_at = now() + timedelta(minutes=planned)
    payload = {
        "ok": True,
        "session": session,
        "ends_at": iso(end_at),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        tag = f"（{session['tag']}）" if session["tag"] else ""
        print(f"🍟 专注开始{tag}！计划 {planned} 分钟，预计 {iso(end_at)[11:16]} 结束。")
        print(f"   会话 ID: {session['id']}  |  加油，到点犒劳自己～")
    return 0


def _current_elapsed(state):
    cur = state.get("current")
    if not cur:
        return None, 0
    started = datetime.strptime(cur["started_at"], "%Y-%m-%d %H:%M:%S")
    elapsed = (now() - started).total_seconds() / 60.0
    return cur, elapsed


def cmd_status(args):
    state = load_state()
    cur, elapsed = _current_elapsed(state)
    t_min = today_minutes(state)
    total_min = done_minutes(state)
    lv = level_for_hours(total_min / 60.0)
    payload = {
        "running": bool(cur),
        "current": cur,
        "elapsed_min": round(elapsed, 1) if cur else 0,
        "remaining_min": round(cur["planned_min"] - elapsed, 1) if cur else 0,
        "today_min": t_min,
        "total_min": total_min,
        "level": lv,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if cur:
        remain = cur["planned_min"] - elapsed
        if remain > 0:
            print(f"⏳ 专注中（{cur['tag'] or '无标签'}）：已 {elapsed:.0f} 分钟，还剩约 {remain:.0f} 分钟")
        else:
            print(f"⏳ 专注中（{cur['tag'] or '无标签'}）：已超时 {abs(remain):.0f} 分钟，随时可以 finish 结算")
    else:
        print("😌 当前没有进行中的专注")
    print(f"📅 今日已专注 {t_min} 分钟 ｜ 累计 {total_min} 分钟 ｜ 段位：{lv['name']}")
    print("   小贴士：python scripts/focus.py start 25 开始一段专注")
    return 0


def cmd_finish(args):
    state = load_state()
    cur, elapsed = _current_elapsed(state)
    if not cur:
        print("[!] 没有进行中的专注")
        return 1
    planned = cur["planned_min"]
    ratio = elapsed / planned if planned else 0
    credited = round(min(elapsed, planned))
    if ratio < MIN_CREDIT_RATIO and not args.force:
        cur.update({"status": "abandoned", "ended_at": iso(now()),
                    "actual_min": round(elapsed, 1), "credited_min": 0})
        state["sessions"].append(cur)
        state["current"] = None
        save_state(state)
        print(f"💤 本次只坚持了 {elapsed:.0f}/{planned} 分钟（不足 60%），记为放弃，没有奖励。")
        print("   没关系，休息一下再来。真的想结算可用 --force。")
        return 0
    cur.update({"status": "done", "ended_at": iso(now()),
                "actual_min": round(elapsed, 1), "credited_min": credited})
    tier = tier_for_minutes(credited)
    before_lv = level_for_hours(done_minutes(state) / 60.0)
    state["sessions"].append(cur)
    state["current"] = None
    after_lv = level_for_hours(done_minutes(state) / 60.0)
    cur["tier"] = tier["key"]
    save_state(state)

    payload = {
        "ok": True,
        "session": cur,
        "tier": tier,
        "today_min": today_minutes(state),
        "total_min": done_minutes(state),
        "level": after_lv,
        "level_up": after_lv["level"] > before_lv["level"],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"🎉 专注完成！本次 {credited} 分钟（实际 {elapsed:.0f} 分钟）")
        print(f"   奖励档位：{tier['name']}（建议预算 ≤ {tier['budget']} 元）")
        print(f"   今日 {today_minutes(state)} 分钟 ｜ 累计 {done_minutes(state)} 分钟 ｜ 段位：{after_lv['name']}")
        if after_lv["level"] > before_lv["level"]:
            print(f"   ⭐ 恭喜晋级：{before_lv['name']} → {after_lv['name']}！")
        print("   下一步：让 reward 引擎帮你挑一份配得上这次专注的奖励餐～")
    return 0


def cmd_cancel(args):
    state = load_state()
    cur, elapsed = _current_elapsed(state)
    if not cur:
        print("[!] 没有进行中的专注")
        return 1
    cur.update({"status": "abandoned", "ended_at": iso(now()),
                "actual_min": round(elapsed, 1), "credited_min": 0})
    state["sessions"].append(cur)
    state["current"] = None
    save_state(state)
    print(f"🗑️ 已放弃本次专注（坚持了 {elapsed:.0f} 分钟，不计入奖励）")
    return 0


def cmd_log(args):
    state = load_state()
    cutoff = now() - timedelta(days=args.days)
    rows = []
    for s in state["sessions"]:
        ended = s.get("ended_at")
        if not ended:
            continue
        if datetime.strptime(ended, "%Y-%m-%d %H:%M:%S") >= cutoff:
            rows.append(s)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print(f"近 {args.days} 天没有记录")
        return 0
    print(f"近 {args.days} 天专注记录（{len(rows)} 段）：")
    for s in rows:
        mark = "✅" if s.get("status") == "done" else "💤"
        tag = s.get("tag") or "无标签"
        print(f"  {mark} {s.get('ended_at')}  {s.get('credited_min', 0)}分钟  [{tag}]")
    return 0


def cmd_stats(args):
    state = load_state()
    total = done_minutes(state)
    lv = level_for_hours(total / 60.0)
    done = [s for s in state["sessions"] if s.get("status") == "done"]
    days = {s["ended_at"][:10] for s in done if s.get("ended_at")}
    payload = {
        "total_min": total,
        "total_hours": round(total / 60.0, 2),
        "sessions_done": len(done),
        "active_days": len(days),
        "today_min": today_minutes(state),
        "level": lv,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"📊 累计专注 {payload['total_hours']} 小时（{len(done)} 段 / {len(days)} 天）")
    print(f"🏅 当前段位：{lv['name']}")
    print(f"📅 今日：{payload['today_min']} 分钟")
    return 0


def main(argv=None):
    _ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="麦麦专注钟 · 专注会话状态机")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("start", help="开始专注")
    p.add_argument("minutes", type=int)
    p.add_argument("--tag", default="")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("status", help="查看状态")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("finish", help="结算当前专注")
    p.add_argument("--force", action="store_true", help="不足 60%% 也强制结算")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_finish)

    p = sub.add_parser("cancel", help="放弃当前专注")
    p.set_defaults(func=cmd_cancel)

    p = sub.add_parser("log", help="历史记录")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("stats", help="累计数据与段位")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
