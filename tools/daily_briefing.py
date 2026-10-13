#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily_briefing.py — 麦当劳程序员创意开发大赛 · 每日战况简报（服务器版）

部署（在服务器上执行）:
  mkdir -p ~/mcd-briefing && cd ~/mcd-briefing
  curl -fsSL https://gcore.jsdelivr.net/gh/JiangHuanDong/mcd-focus-treat@main/tools/daily_briefing.py -o daily_briefing.py
  echo "SENDKEY=你的SendKey" > config.env
  (crontab -l 2>/dev/null | grep -v mcd-briefing; echo "0 * * * * cd \$HOME/mcd-briefing && python3 daily_briefing.py >> briefing.log 2>&1") | crontab -
  python3 daily_briefing.py --test    # 立即测试推送

说明:
- 纯 Python 标准库，无需安装任何依赖（服务器 Python 3.6+ 即可）
- cron 每小时触发；脚本自动只在「北京时间 10 点」发送当日简报（服务器时区无关）
- 若报名审核出现结果（通过/失败），会在任意整点立即推送一次提醒
- 手动参数: --test 立即测试 / --force 立即发送完整简报 / --dry-run 只打印不发送
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.env")
STATE_PATH = os.path.join(HERE, "state.json")
UA = {"User-Agent": "mcd-daily-briefing/1.0"}

ISSUE_COMMENTS_URL = "https://api.github.com/repos/M-China/mcd-developer-innovation-challenge/issues/594/comments"
REPO_API_URL = "https://api.github.com/repos/JiangHuanDong/mcd-focus-treat"
RANKING_URLS = [
    "https://gcore.jsdelivr.net/gh/M-China/mcd-developer-innovation-challenge@main/RANKING.md",
    "https://raw.githubusercontent.com/M-China/mcd-developer-innovation-challenge/main/RANKING.md",
]

REPO_URL = "https://github.com/JiangHuanDong/mcd-focus-treat"
DEMO_URL = "https://jianghuandong.github.io/mcd-focus-treat/"

ACTION_TABLE = {
    "10-13": "项目已上线：① 自己主号点个 star ② 发给身边朋友看看（已完成可忽略）",
    "10-14": "【开闸日】发朋友圈（配项目分享卡）+ 发 2~3 个最熟的技术群",
    "10-15": "【长文日】腾讯云开发者社区 + 掘金 发布项目长文",
    "10-16": "回复前两篇的评论互动；可选发 V2EX（分享创造节点）",
    "10-17": "保温期：随手回评论即可，无硬性任务",
    "10-18": "保温期：可发一条轻内容（战报卡截图 / 省钱分享）",
    "10-19": "保温期：随手回评论即可，无硬性任务",
    "10-20": "保温期：可发一条轻内容（使用小记）",
    "10-21": "保温期：随手回评论即可，无硬性任务",
    "10-22": "保温期：可发一条轻内容（新手指引 / FAQ 分享）",
    "10-23": "保温期：随手回评论即可，无硬性任务",
    "10-24": "距截止还剩 1 天：整理素材，为明天最后一波做准备",
    "10-25": "【冲刺日】今晚 23:59 报名与排名截止！找 2~3 个技术朋友支持（星要今天点完）",
    "10-26": "【定榜日】查看最终排名；若进前 100，准备兑奖（11-14 前完成）",
}


def log(msg):
    print("[%s] %s" % (datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"), msg))


def load_config():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("SENDKEY",):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(st):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log("state 保存失败: %s" % e)


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def http_get_json(url, timeout=20):
    return json.loads(http_get(url, timeout))


def check_audit():
    """检查报名 Issue 的官方回复"""
    try:
        comments = http_get_json(ISSUE_COMMENTS_URL)
    except Exception as e:
        return {"status": "unknown", "detail": "审核状态获取失败：%s" % e}
    officials = [c for c in comments
                 if (c.get("user") or {}).get("login") == "M-China-Official"]
    if not officials:
        return {"status": "pending", "detail": "审核排队中"}
    body = officials[-1].get("body") or ""
    if "失败原因" in body and "已经报名成功" not in body:
        return {"status": "failed", "detail": body.strip()[:160]}
    if "已经报名成功" in body:
        return {"status": "passed", "detail": "报名成功（此前已通过，重复提交被忽略）"}
    if "报名成功" in body or "通过" in body:
        return {"status": "passed", "detail": body.strip()[:160]}
    return {"status": "replied", "detail": body.strip()[:160]}


def check_stars():
    try:
        return http_get_json(REPO_API_URL).get("stargazers_count")
    except Exception:
        return None


def check_ranking():
    text = None
    for url in RANKING_URLS:
        try:
            text = http_get(url)
            break
        except Exception:
            continue
    if not text:
        return None
    parsed = []
    for m in re.finditer(r"^\|\s*(\d+)\s*\|[^|\n]*\|[^|\n]*\|\s*(\d+)\s*\|\s*$", text, re.M):
        parsed.append((int(m.group(1)), int(m.group(2))))
    if not parsed:
        return None
    threshold = None
    for rank, stars in parsed:
        if rank >= 100:
            threshold = stars
            break
    if threshold is None:
        threshold = parsed[-1][1]
    return {"count": len(parsed), "top1": parsed[0][1], "threshold": threshold}


def build_message(stars, ranking, audit, test=False):
    now = datetime.now(CST)
    key = now.strftime("%m-%d")
    action = ACTION_TABLE.get(key, "保持关注即可，今天无特定行动")

    title_prefix = "【测试】" if test else ""
    if audit["status"] == "passed":
        title = "%s✅ 麦当劳大赛：报名已通过！" % title_prefix
    elif audit["status"] == "failed":
        title = "%s⚠️ 麦当劳大赛：报名需要处理" % title_prefix
    else:
        title = "%s📡 麦当劳大赛简报（%s）" % (title_prefix, now.strftime("%m/%d"))

    if stars is None:
        stars_line = "星数：获取失败（网络问题，稍后自动重试）"
    elif ranking:
        gap = max(0, ranking["threshold"] - stars)
        stars_line = "星数：**%s ⭐** ｜ 前100门槛：%s ⭐ ｜ 差距：%s ⭐（第1名 %s ⭐）" % (
            stars, ranking["threshold"], gap, ranking["top1"])
    else:
        stars_line = "星数：**%s ⭐**（榜单获取失败）" % stars

    if audit["status"] == "passed":
        audit_line = "报名审核：✅ 已通过（安心冲榜）"
    elif audit["status"] == "failed":
        audit_line = "报名审核：⚠️ 未通过 —— %s" % audit["detail"]
    elif audit["status"] == "replied":
        audit_line = "报名审核：📮 有新回复，请人工确认 —— %s" % audit["detail"]
    elif audit["status"] == "pending":
        audit_line = "报名审核：⏳ 排队中（正常，机器人审核通常很快）"
    else:
        audit_line = "报名审核：⚠️ %s" % audit["detail"]

    desp = "\n".join([
        "## 📡 麦当劳大赛战况简报（%s）" % now.strftime("%m月%d日"),
        "",
        stars_line,
        "",
        audit_line,
        "",
        "**今日行动**：%s" % action,
        "",
        "——",
        "仓库：%s" % REPO_URL,
        "演示页：%s" % DEMO_URL,
    ])
    return title, desp


def send_serverchan(config, title, desp):
    key = config.get("SENDKEY", "")
    if not key:
        raise RuntimeError("缺少 SENDKEY：请在 config.env 中配置 SENDKEY=你的SendKey")
    url = "https://sctapi.ftqq.com/%s.send" % key
    data = urllib.parse.urlencode({"title": title, "desp": desp}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        resp = json.loads(r.read().decode("utf-8", "replace"))
    return resp


def main():
    args = set(sys.argv[1:])
    dry = "--dry-run" in args
    test = "--test" in args
    force = test or ("--force" in args)

    now = datetime.now(CST)
    today = now.strftime("%Y-%m-%d")
    state = load_state()
    config = load_config()

    # 审核状态：每小时检查一次（出现结果时立即提醒）
    audit = check_audit()
    alert = False
    if audit["status"] in ("passed", "failed") and state.get("audit") != audit["status"]:
        alert = True  # 状态跃迁 → 立即推送

    if not force and not alert:
        if now.hour != 10:
            log("非发送时段（北京 %02d 点），跳过" % now.hour)
            return 0
        if state.get("last_sent") == today:
            log("今天已发送过，跳过")
            return 0

    stars = check_stars()
    ranking = check_ranking()
    log("审核=%s 星数=%s 榜单=%s" % (audit["status"], stars, ranking))

    title, desp = build_message(stars, ranking, audit, test=test)
    if test and "【测试】" not in desp:
        desp = "（这是一条测试消息，收到说明推送链路已打通）\n\n" + desp

    if dry:
        print("=== TITLE ===\n%s\n=== BODY ===\n%s" % (title, desp))
        return 0

    resp = send_serverchan(config, title, desp)
    log("推送结果: %s" % json.dumps(resp, ensure_ascii=False))
    if not (isinstance(resp, dict) and resp.get("code") == 0):
        log("推送可能失败，请检查 SendKey")
        return 1

    state["last_sent"] = today
    state["audit"] = audit["status"]
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
