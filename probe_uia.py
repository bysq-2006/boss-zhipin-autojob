# -*- coding: utf-8 -*-
"""探测 BOSS直聘 Edge 窗口的 UIA 树, 可选点击立即沟通。"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time

import uiautomation as auto

auto.SetGlobalSearchTimeout(2.0)

INTEREST = (
    "立即沟通",
    "留在此页",
    "继续沟通",
    "工作地址",
    "职位描述",
    "收藏",
    "搜索",
)


def setup_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if reconf is not None:
            try:
                reconf(encoding="utf-8")
            except Exception:
                pass


def find_boss_window():
    root = auto.GetRootControl()
    skip_cls = {"CabinetWClass", "CabinetWClass1"}
    ranked = []
    for win in root.GetChildren():
        name = win.Name or ""
        cls = win.ClassName or ""
        if cls in skip_cls:
            continue
        score = 0
        if "BOSS直聘" in name:
            score += 10
        if "zhipin.com" in name.lower() or "zhipin" in name.lower():
            score += 5
        if "成都招聘" in name:
            score += 3
        if cls == "Chrome_WidgetWin_1" and ("Edge" in name or "Chrome" in name):
            score += 1
        if score:
            ranked.append((score, win))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1] if ranked else None


def brief(ctrl, idx: int) -> dict:
    try:
        rect = ctrl.BoundingRectangle
        box = [rect.left, rect.top, rect.right, rect.bottom]
    except Exception:
        box = None
    try:
        ctype = ctrl.ControlTypeName
    except Exception:
        ctype = ""
    return {
        "i": idx,
        "type": ctype,
        "name": (ctrl.Name or "")[:200],
        "class": ctrl.ClassName or "",
        "auto_id": ctrl.AutomationId or "",
        "rect": box,
        "enabled": bool(getattr(ctrl, "IsEnabled", True)),
        "offscreen": bool(getattr(ctrl, "IsOffscreen", False)),
    }


def walk(ctrl, depth: int, max_depth: int, max_nodes: int, acc: list, interesting: list) -> None:
    if len(acc) >= max_nodes or depth > max_depth:
        return
    info = brief(ctrl, len(acc))
    acc.append({**info, "depth": depth})
    name = info["name"]
    if any(k in name for k in INTEREST) or re.search(r"\d+[-~]\d+", name):
        interesting.append(info)
    try:
        children = ctrl.GetChildren()
    except Exception:
        return
    for ch in children:
        if len(acc) >= max_nodes:
            return
        walk(ch, depth + 1, max_depth, max_nodes, acc, interesting)


def cmd_dump(args) -> None:
    win = find_boss_window()
    if not win:
        print(json.dumps({"error": "找不到 BOSS直聘 窗口"}, ensure_ascii=False))
        return
    print("WINDOW:", win.Name, "class=", win.ClassName, file=sys.stderr)
    acc: list = []
    interesting: list = []
    walk(win, 0, args.depth, args.max_nodes, acc, interesting)
    out = {
        "window": win.Name,
        "class": win.ClassName,
        "nodes": len(acc),
        "interesting": interesting[:80],
        "sample": acc[: args.sample],
        "names_nonempty": [x for x in acc if x["name"].strip()][: args.sample],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def find_by_name(win, exact: str, contains: str | None = None):
    found = []

    def rec(ctrl, depth: int) -> None:
        if depth > 40 or len(found) >= 20:
            return
        name = ctrl.Name or ""
        if exact and name == exact:
            found.append(ctrl)
        elif contains and contains in name:
            found.append(ctrl)
        try:
            children = ctrl.GetChildren()
        except Exception:
            return
        for ch in children:
            rec(ch, depth + 1)

    rec(win, 0)
    return found


def cmd_click_chat(args) -> None:
    win = find_boss_window()
    if not win:
        print(json.dumps({"error": "找不到 BOSS直聘 窗口"}, ensure_ascii=False))
        return
    try:
        win.SetActive()
    except Exception:
        pass
    time.sleep(0.3)
    btns = find_by_name(win, "立即沟通")
    print("found 立即沟通:", len(btns), file=sys.stderr)
    if not btns:
        # looser
        btns = find_by_name(win, "", contains="立即沟通")
        print("found contains 立即沟通:", len(btns), file=sys.stderr)
    if not btns:
        print(json.dumps({"error": "树里没有「立即沟通」", "window": win.Name}, ensure_ascii=False))
        return
    target = btns[0]
    info = brief(target, 0)
    print("clicking:", json.dumps(info, ensure_ascii=False), file=sys.stderr)
    ok = False
    err = ""
    try:
        ok = bool(target.Click())
    except Exception as e:
        err = str(e)
        try:
            ok = bool(target.GetInvokePattern().Invoke())
            err = ""
        except Exception as e2:
            err = err + " | invoke: " + str(e2)
    time.sleep(0.8)
    stay = find_by_name(win, "留在此页")
    stay_info = [brief(s, i) for i, s in enumerate(stay)]
    if stay and args.stay:
        try:
            stay[0].Click()
            stay_clicked = True
        except Exception as e:
            stay_clicked = False
            err = err + " | stay: " + str(e)
    else:
        stay_clicked = False
    print(
        json.dumps(
            {
                "clicked": info,
                "click_ok": ok,
                "error": err,
                "stay_found": stay_info,
                "stay_clicked": stay_clicked,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    setup_stdio()
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["dump", "chat"])
    p.add_argument("--depth", type=int, default=18)
    p.add_argument("--max-nodes", type=int, default=2500)
    p.add_argument("--sample", type=int, default=80)
    p.add_argument("--stay", action="store_true", help="点完沟通后点「留在此页」")
    args = p.parse_args()
    if args.cmd == "dump":
        cmd_dump(args)
    else:
        cmd_click_chat(args)


if __name__ == "__main__":
    main()
