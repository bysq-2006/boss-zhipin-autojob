# -*- coding: utf-8 -*-
"""BOSS直聘: UIA 拉列表(+通勤) / 按序号拟人点击立即沟通。"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from _ctypes import COMError
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import uiautomation as auto

import helper

HERE = os.path.dirname(os.path.abspath(__file__))
LAST_LIST = os.path.join(HERE, "last_list.json")
PUA = re.compile(r"[\ue000-\uf8ff]")
AREA_RE = re.compile(r"(成都|成都市).{0,2}[\u4e00-\u9fff]+区")
# BOSS 薪资数字用私用区字体, e031=0 ... e03a=9
PUA_ZERO = 0xE031

auto.SetGlobalSearchTimeout(3.0)


def setup_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if reconf is not None:
            try:
                reconf(encoding="utf-8")
            except Exception:
                pass


def emit(payload: Any, code: int = 0) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    sys.stdout.flush()
    raise SystemExit(code)


def pause(lo: float, hi: float) -> None:
    time.sleep(random.uniform(lo, hi))


def nlpause(base: float = 0.05) -> None:
    """多数很快, 偶尔顿一下, 避免每次一样长。"""
    u = random.random()
    if u < 0.65:
        time.sleep(base * random.uniform(0.2, 0.55))
    elif u < 0.9:
        time.sleep(base * random.uniform(0.55, 0.95))
    else:
        time.sleep(base * random.uniform(0.95, 1.5))


def clamp_wait(raw) -> float:
    try:
        sec = float(raw)
    except (TypeError, ValueError):
        sec = 0.0
    if sec < 0:
        return 0.0
    if sec > 3.0:
        return 3.0
    return sec


def wait_before_start(raw) -> None:
    sec = clamp_wait(raw)
    if sec > 0:
        time.sleep(sec)


def ease_move(x: int, y: int) -> None:
    """先快后慢移到目标, 路径上加小扰动, 终点不乱飘。"""
    try:
        cx, cy = auto.GetCursorPos()
    except Exception:
        auto.SetCursorPos(int(x), int(y))
        return
    dx, dy = x - cx, y - cy
    dist = (dx * dx + dy * dy) ** 0.5
    if dist < 4:
        auto.SetCursorPos(int(x), int(y))
        return
    steps = max(5, min(14, int(dist / 110)))
    for i in range(1, steps + 1):
        t = i / float(steps)
        e = 1.0 - (1.0 - t) ** 3
        fade = 1.0 - t
        wig = fade * fade * random.uniform(-10.0, 10.0)
        nx = cx + dx * e + wig
        ny = cy + dy * e + wig * random.uniform(-0.35, 0.35)
        auto.SetCursorPos(int(nx), int(ny))
        time.sleep(0.002 + t * t * 0.01)
    auto.SetCursorPos(int(x), int(y))


def clean_text(s: str) -> str:
    return PUA.sub("", s or "").strip()


def decode_boss_digits(s: str) -> str:
    out = []
    for ch in s or "":
        o = ord(ch)
        if PUA_ZERO <= o <= PUA_ZERO + 9:
            out.append(str(o - PUA_ZERO))
        else:
            out.append(ch)
    return "".join(out)


def parse_salary_fields(raw: str) -> Tuple[str, int]:
    t = decode_boss_digits(raw)
    m = re.search(r"(\d+)\s*[-~—–]\s*(\d+)\s*元/天", t)
    if m:
        return m.group(0), int(m.group(1))
    m = re.search(r"(\d+)\s*[-~—–]\s*(\d+)\s*元/月", t)
    if m:
        return m.group(0), int(round(int(m.group(1)) / 22.0))
    m = re.search(r"(\d+)\s*[-~—–]\s*(\d+)\s*[kK]", t)
    if m:
        return m.group(0), int(round(int(m.group(1)) * 1000 / 22.0))
    return "", 0


def _edge_windows():
    root = auto.GetRootControl()
    out = []
    for win in root.GetChildren():
        name = win.Name or ""
        cls = win.ClassName or ""
        if cls == "Chrome_WidgetWin_1" and "Edge" in name:
            out.append(win)
    return out


def find_boss_window():
    ranked = []
    for win in _edge_windows():
        name = win.Name or ""
        score = 0
        if "BOSS直聘" in name:
            score += 10
        if "zhipin" in name.lower():
            score += 5
        if "成都招聘" in name:
            score += 3
        if score:
            ranked.append((score, win))
    if ranked:
        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked[0][1]
    # 当前前台标签不是 BOSS, 但同一个 Edge 里可能有 BOSS 标签
    for win in _edge_windows():
        if find_boss_tab(win) is not None:
            return win
    return None


def find_boss_tab(win):
    hits = []

    def rec(c, d: int) -> None:
        if d > 12 or hits:
            return
        name = c.Name or ""
        if c.ControlTypeName == "TabItemControl" and "BOSS直聘" in name:
            hits.append(c)
            return
        for k in children(c):
            rec(k, d + 1)

    rec(win, 0)
    return hits[0] if hits else None


def ensure_boss_page(win):
    name = win.Name or ""
    if "BOSS直聘" in name:
        return True
    tab = find_boss_tab(win)
    if tab is None:
        return False
    human_invoke(tab, 0.05, 0.12)
    pause(0.08, 0.12)
    return True


def activate(win) -> None:
    try:
        win.SetActive()
    except Exception:
        pass
    pause(0.08, 0.12)


def find_document(win):
    found = []

    def rec(c, d: int) -> None:
        if d > 22:
            return
        name = c.Name or ""
        try:
            r = c.BoundingRectangle
            w = r.width()
        except Exception:
            w = 0
        if c.ControlTypeName == "DocumentControl" and "BOSS直聘" in name and w > 400:
            found.append(c)
            return
        try:
            kids = c.GetChildren()
        except Exception:
            return
        for k in kids:
            rec(k, d + 1)

    rec(win, 0)
    return found[0] if found else None


def children(ctrl) -> list:
    try:
        return list(ctrl.GetChildren())
    except Exception:
        return []


def walk(ctrl, max_d: int, d: int = 0):
    yield d, ctrl
    if d >= max_d:
        return
    for ch in children(ctrl):
        yield from walk(ch, max_d, d + 1)


def parse_card(item) -> Dict[str, Any]:
    title = ""
    company = ""
    area = ""
    tags: List[str] = []
    salary = ""
    for _d, c in walk(item, 4):
        name = clean_text(c.Name or "")
        cls = c.ClassName or ""
        ctype = c.ControlTypeName
        if cls == "job-name" and name and not title:
            title = name
        elif cls == "boss-info" and name and not company:
            company = name
        elif ctype == "TextControl" and "·" in name and ("区" in name or "成都" in name):
            if not area or name.count("·") >= area.count("·"):
                area = name
        elif ctype in ("ListItemControl", "TextControl") and name:
            if name in tags:
                pass
            elif re.match(r"^\d+天/周$", name) or re.match(r"^\d+个月$", name):
                tags.append(name)
            elif name in ("本科", "大专", "硕士", "博士", "高中", "学历不限", "经验不限", "应届生", "在校生"):
                tags.append(name)
        if not salary:
            sal, _lo = parse_salary_fields(c.Name or "")
            if sal:
                salary = sal
    if not salary:
        salary, _lo = parse_salary_fields(item.Name or "")
    _label, salary_min = parse_salary_fields(salary or item.Name or "")
    if not title:
        raw = clean_text(item.Name or "")
        title = re.split(r"\d|元", raw, maxsplit=1)[0].strip(" |")[:40]
    try:
        r = item.BoundingRectangle
        box = [r.left, r.top, r.right, r.bottom]
        visible = r.height() > 40 and r.width() > 200 and r.bottom > 150 and r.top < 1500
    except Exception:
        box = [0, 0, 0, 0]
        visible = False
    return {
        "title": title,
        "company": company,
        "area": area,
        "tags": tags,
        "salary": salary,
        "salary_min": salary_min,
        "visible": visible,
        "rect": box,
    }


def collect_cards(doc) -> list:
    cards = []
    for _d, c in walk(doc, 8):
        if c.ControlTypeName == "ListItemControl" and (c.ClassName or "") == "job-card-box":
            cards.append(c)
    return cards


def area_to_address(area: str) -> str:
    a = (area or "").replace("·", "").replace(" ", "")
    if a.startswith("成都") and not a.startswith("成都市"):
        a = "成都市" + a[2:]
    return a


def enrich_commute(jobs: List[Dict[str, Any]]) -> None:
    cfg = helper.load_config()
    cache = helper.load_cache()
    uniq: Dict[str, Dict[str, Any]] = {}
    for job in jobs:
        addr = area_to_address(job.get("area") or "")
        job["address"] = addr
        if not addr:
            job["commute_status"] = "REJECT"
            job["commute_min"] = 0
            job["distance_km"] = 0
            job["commute_reason"] = "卡片无区域"
            continue
        if addr not in uniq:
            uniq[addr] = helper.cmd_commute(addr, cfg, cache)
        cm = uniq[addr]
        job["commute_status"] = cm.get("status", "REJECT")
        job["commute_min"] = cm.get("commute_min", 0)
        job["distance_km"] = cm.get("distance_km", 0)
        job["commute_reason"] = cm.get("reason", "")


def snapshot_jobs(doc) -> Tuple[list, List[Dict[str, Any]]]:
    ctrls = collect_cards(doc)
    jobs = []
    for i, ctrl in enumerate(ctrls):
        info = parse_card(ctrl)
        info["i"] = i
        jobs.append(info)
    return ctrls, jobs


def stable_snapshot(win, attempts: int = 3) -> Tuple[Any, list, List[Dict[str, Any]]]:
    """Reacquire the Edge accessibility tree when a UIA proxy goes stale."""
    attempts = max(1, int(attempts))
    for attempt in range(attempts):
        try:
            doc = find_document(win)
            if not doc:
                return None, [], []
            ctrls, jobs = snapshot_jobs(doc)
            return doc, ctrls, jobs
        except COMError:
            if attempt + 1 < attempts:
                time.sleep(0.15 * (attempt + 1))
    return None, [], []


def job_key(j: Dict[str, Any]) -> str:
    return "%s\t%s" % ((j.get("company") or "").strip(), (j.get("title") or "").strip())


def public_job(j: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "i": j["i"],
        "title": j["title"],
        "company": j["company"],
        "area": j.get("area", ""),
        "tags": j.get("tags") or [],
        "salary": j.get("salary", ""),
        "salary_min": j.get("salary_min", 0),
        "visible": j.get("visible", False),
        "address": j.get("address", ""),
        "commute_min": j.get("commute_min", 0),
        "distance_km": j.get("distance_km", 0),
        "commute_status": j.get("commute_status", ""),
        "commute_reason": j.get("commute_reason", ""),
    }


def save_last(jobs: List[Dict[str, Any]]) -> None:
    slim = [{k: j[k] for k in ("i", "title", "company", "area") if k in j} for j in jobs]
    with open(LAST_LIST, "w", encoding="utf-8") as fh:
        json.dump({"ts": time.time(), "jobs": slim}, fh, ensure_ascii=False, indent=2)


def load_last() -> List[Dict[str, Any]]:
    if not os.path.isfile(LAST_LIST):
        return []
    try:
        with open(LAST_LIST, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("jobs") or []
    except Exception:
        return []


def parse_after(raw) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return -1


def cmd_list(args: argparse.Namespace) -> None:
    wait_before_start(getattr(args, "wait", 0))
    after = parse_after(getattr(args, "after", -1))
    win = find_boss_window()
    if not win:
        emit({"error": "找不到 BOSS直聘 窗口(Edge)"}, 2)
    activate(win)
    if not ensure_boss_page(win):
        emit({"error": "Edge 里没有 BOSS直聘 标签"}, 2)
    doc, _ctrls, jobs = stable_snapshot(win)
    if not doc:
        emit({"error": "页面 UI Automation 暂时不可用, 请保持 BOSS 标签页可见"}, 2)
    if not jobs:
        emit({"error": "未扫到 job-card-box", "window": win.Name}, 2)
    enrich_commute(jobs)
    save_last(jobs)
    rec = recorded_keys()
    out_jobs = []
    skipped = 0
    for j in jobs:
        if int(j["i"]) <= after:
            skipped += 1
            continue
        if job_key(j) in rec:
            skipped += 1
            continue
        out_jobs.append(public_job(j))
    emit(
        {
            "window": win.Name,
            "after": after,
            "scanned": len(jobs),
            "skipped": skipped,
            "count": len(out_jobs),
            "jobs": out_jobs,
        }
    )


def find_named(root, exact: str, ctype: Optional[str] = None):
    hits = []

    def rec(c, d: int) -> None:
        if d > 40 or len(hits) >= 8:
            return
        name = c.Name or ""
        if name == exact and (ctype is None or c.ControlTypeName == ctype):
            hits.append(c)
            return
        for k in children(c):
            rec(k, d + 1)

    rec(root, 0)
    return hits


def human_invoke(ctrl, lo: float = 0.03, hi: float = 0.08) -> bool:
    r = None
    x = y = None
    try:
        r = ctrl.BoundingRectangle
        x = r.xcenter() + random.randint(-5, 5)
        y = r.ycenter() + random.randint(-4, 4)
        x = max(r.left + 4, min(r.right - 4, x))
        y = max(r.top + 4, min(r.bottom - 4, y))
    except Exception:
        pass
    if x is not None and r is not None and r.width() > 0:
        try:
            ease_move(x, y)
        except Exception:
            pass
    nlpause((lo + hi) / 2)
    try:
        pat = ctrl.GetInvokePattern()
        if pat:
            pat.Invoke()
            return True
    except Exception:
        pass
    try:
        return bool(ctrl.Click())
    except Exception:
        return False


def wait_named(root, exact: str, ctype: str, timeout: float = 6.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        hits = find_named(root, exact, ctype)
        if hits:
            return hits[0]
        time.sleep(0.08)
    return None


def _in_view(ctrl, doc) -> bool:
    try:
        r = ctrl.BoundingRectangle
        v = doc.BoundingRectangle
        return r.height() > 20 and r.top >= v.top + 70 and r.bottom <= v.bottom - 30
    except Exception:
        return False


def _park_on_list(doc, ctrl=None) -> None:
    try:
        v = doc.BoundingRectangle
        if ctrl is not None:
            r = ctrl.BoundingRectangle
            mx = r.xcenter() if r.width() > 40 else v.left + 280
        else:
            mx = v.left + 280
        my = v.top + int(v.height() * 0.52)
        ease_move(int(mx), int(my))
    except Exception:
        pass


def _wheel_burst(down: bool, ticks: int) -> None:
    fn = auto.WheelDown if down else auto.WheelUp
    interval = 0.008 + random.uniform(0.0, 0.006)
    fn(max(1, ticks), interval=interval, waitTime=0.0)


def jitter_scroll_to(ctrl, doc) -> bool:
    """先快后慢滚到目标。有实际滚轮则返回 True, 调用方须等 0.1s 再点。"""
    _park_on_list(doc, ctrl)
    if _in_view(ctrl, doc):
        return False
    scrolled = False
    for _ in range(22):
        try:
            r = ctrl.BoundingRectangle
            v = doc.BoundingRectangle
        except Exception:
            break
        if _in_view(ctrl, doc):
            break
        remain = abs(r.top - (v.top + v.height() * 0.42))
        down = r.top > (v.top + v.height() * 0.55)
        if remain > 500:
            ticks = random.choice((5, 6, 7, 8))
        elif remain > 220:
            ticks = random.choice((3, 4, 5))
        elif remain > 90:
            ticks = random.choice((2, 2, 3))
        else:
            ticks = 1
        ticks = max(1, ticks + random.choice((-1, 0, 0, 1)))
        _wheel_burst(down, ticks)
        scrolled = True
        if remain > 220:
            time.sleep(random.uniform(0.008, 0.02))
        else:
            time.sleep(random.uniform(0.02, 0.045))
    return scrolled


def jitter_scroll_list_down(doc, ctrls: list) -> None:
    park = ctrls[-1] if ctrls else None
    _park_on_list(doc, park)
    bursts = random.choice((3, 4, 5))
    for i in range(bursts):
        t = i / float(max(1, bursts - 1))
        ticks = int(6 - t * 4) + random.choice((-1, 0, 0, 1))
        _wheel_burst(True, max(1, ticks))
        time.sleep(0.008 + t * 0.03)


def match_card(jobs_now: List[Dict[str, Any]], ctrls, pick_i: int, last: List[Dict[str, Any]]):
    if 0 <= pick_i < len(ctrls):
        want = None
        for row in last:
            if row.get("i") == pick_i:
                want = row
                break
        if want:
            for j, c in zip(jobs_now, ctrls):
                if j.get("title") == want.get("title") and j.get("company") == want.get("company"):
                    return c, j
        return ctrls[pick_i], jobs_now[pick_i]
    return None, None


def append_record(job: Dict[str, Any], ok: bool, note: str) -> None:
    cfg = helper.load_config()
    path = cfg.get("RECORD_FILE") or os.path.join(HERE, "投递记录.txt")
    line = "%s\t%s\t%s\t%s\t%s\n" % (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        job.get("company", ""),
        job.get("title", ""),
        "OK" if ok else "FAIL",
        note,
    )
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        with open(os.path.join(HERE, "投递记录.txt"), "a", encoding="utf-8") as fh:
            fh.write(line)


def recorded_blob() -> str:
    cfg = helper.load_config()
    chunks = []
    for path in (cfg.get("RECORD_FILE"), os.path.join(HERE, "投递记录.txt")):
        if path and os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    chunks.append(fh.read())
            except Exception:
                pass
    return "\n".join(chunks)


def recorded_keys() -> set:
    keys = set()
    for line in recorded_blob().splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            keys.add("%s\t%s" % (parts[1].strip(), parts[2].strip()))
    return keys


def auto_pick(
    jobs: List[Dict[str, Any]], count: int, min_daily: int, seen: set
) -> List[int]:
    cfg = helper.load_config()
    excludes = [x.strip() for x in cfg.get("EXCLUDE_KEYWORDS", "").split(",") if x.strip()]
    keywords = [x.strip() for x in cfg.get("JOB_KEYWORDS", "").split(",") if x.strip()]
    picks = []
    for j in jobs:
        title = j.get("title") or ""
        company = j.get("company") or ""
        key = job_key(j)
        blob = "%s %s %s" % (title, company, " ".join(j.get("tags") or []))
        if key in seen:
            continue
        if j.get("commute_status") != "PASS":
            continue
        if int(j.get("salary_min") or 0) < min_daily:
            continue
        if keywords and not any(k.lower() in blob.lower() for k in keywords):
            continue
        if any(k and k in blob for k in excludes):
            continue
        picks.append(int(j["i"]))
        if len(picks) >= count:
            break
    return picks


def run_chat(picks: List[int]) -> Dict[str, Any]:
    win = find_boss_window()
    if not win:
        return {"error": "找不到 BOSS直聘 窗口"}
    activate(win)
    if not ensure_boss_page(win):
        return {"error": "Edge 里没有 BOSS直聘 标签"}
    last = load_last()
    results = []
    for n, idx in enumerate(picks):
        if n:
            nlpause(0.05)
        doc, ctrls, jobs_now = stable_snapshot(win)
        if not doc:
            results.append({"i": idx, "ok": False, "note": "页面 UI Automation 暂时不可用"})
            continue
        ctrl, job = match_card(jobs_now, ctrls, idx, last)
        if ctrl is None:
            results.append({"i": idx, "ok": False, "note": "找不到对应卡片"})
            continue
        if jitter_scroll_to(ctrl, doc):
            time.sleep(0.1)
        if not human_invoke(ctrl):
            results.append({"i": idx, "ok": False, "title": job.get("title"), "note": "选中卡片失败"})
            continue
        nlpause(0.05)
        chat_btn = wait_named(win, "立即沟通", "HyperlinkControl", 2.5)
        if not chat_btn:
            results.append({"i": idx, "ok": False, "title": job.get("title"), "note": "没有立即沟通"})
            continue
        nlpause(0.04)
        if not human_invoke(chat_btn):
            results.append({"i": idx, "ok": False, "title": job.get("title"), "note": "立即沟通 Invoke 失败"})
            continue
        stay = wait_named(win, "留在此页", "HyperlinkControl", 2.5)
        if stay:
            nlpause(0.04)
            human_invoke(stay)
            nlpause(0.04)
            append_record(job, True, "立即沟通")
            results.append({"i": idx, "ok": True, "title": job.get("title"), "company": job.get("company")})
        else:
            append_record(job, False, "已点沟通但无留在此页")
            results.append({"i": idx, "ok": False, "title": job.get("title"), "note": "无留在此页弹窗"})
    return {"picked": picks, "results": results}


def cmd_chat(args: argparse.Namespace) -> None:
    wait_before_start(getattr(args, "wait", 0))
    raw = (args.pick or "").strip()
    if not raw:
        emit({"error": "用法: zhipin_win.py chat --pick 0,2,5"}, 2)
    picks = []
    for part in raw.replace(" ", ",").split(","):
        if part.strip().isdigit():
            picks.append(int(part.strip()))
    if not picks:
        emit({"error": "pick 为空"}, 2)
    emit(run_chat(picks))


def cmd_apply(args: argparse.Namespace) -> None:
    wait_before_start(getattr(args, "wait", 0))
    try:
        count = int(args.count)
    except (TypeError, ValueError):
        count = 20
    after = parse_after(getattr(args, "after", -1))
    cfg = helper.load_config()
    try:
        min_daily = int(args.min_daily if args.min_daily is not None else cfg.get("MIN_DAILY_SALARY", "90"))
    except ValueError:
        min_daily = 90
    win = find_boss_window()
    if not win:
        emit({"error": "找不到 BOSS直聘 窗口(Edge)"}, 2)
    activate(win)
    if not ensure_boss_page(win):
        emit({"error": "Edge 里没有 BOSS直聘 标签"}, 2)
    seen = recorded_keys()
    selected: List[Dict[str, Any]] = []
    all_results: List[Dict[str, Any]] = []
    ok_n = 0
    stale = 0
    scanned_max = 0
    while ok_n < count and stale < 5:
        doc, ctrls, jobs = stable_snapshot(win)
        if not doc:
            stale += 1
            time.sleep(0.1)
            continue
        if not jobs:
            stale += 1
            jitter_scroll_list_down(doc, ctrls)
            time.sleep(0.1)
            continue
        scanned_max = max(scanned_max, len(jobs))
        enrich_commute(jobs)
        save_last(jobs)
        for j in jobs:
            if int(j["i"]) <= after:
                k = job_key(j)
                if k.strip("\t"):
                    seen.add(k)
        need = count - ok_n
        picks = auto_pick(jobs, need, min_daily, seen)
        if picks:
            stale = 0
            for j in jobs:
                if int(j["i"]) in picks:
                    selected.append(public_job(j))
                    seen.add(job_key(j))
            chat_res = run_chat(picks)
            batch = chat_res.get("results") or []
            all_results.extend(batch)
            for r in batch:
                k = "%s\t%s" % ((r.get("company") or "").strip(), (r.get("title") or "").strip())
                if k.strip("\t"):
                    seen.add(k)
                if r.get("ok"):
                    ok_n += 1
            after = max(after, max(picks))
        else:
            stale += 1
        if ok_n >= count:
            break
        jitter_scroll_list_down(doc, ctrls)
        time.sleep(0.1)
    emit(
        {
            "min_daily": min_daily,
            "after": after,
            "listed": scanned_max,
            "ok": ok_n,
            "selected": [
                {
                    "i": j["i"],
                    "title": j["title"],
                    "company": j["company"],
                    "salary": j.get("salary"),
                    "salary_min": j.get("salary_min"),
                    "commute_min": j.get("commute_min"),
                }
                for j in selected
            ],
            "results": all_results,
        }
    )


def main() -> None:
    setup_stdio()
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")
    p_list = sub.add_parser("list")
    p_list.add_argument("--after", default="-1", help="只显示 i 大于该值的卡, 上面的视为已看过")
    p_list.add_argument("--wait", default="0", help="开始前等待秒数, 最大 3")
    p_chat = sub.add_parser("chat")
    p_chat.add_argument("--pick", default="", help="逗号分隔的 i, 对应 list 的序号")
    p_chat.add_argument("--wait", default="0", help="开始前等待秒数, 最大 3")
    p_apply = sub.add_parser("apply")
    p_apply.add_argument("--count", default="20")
    p_apply.add_argument("--min-daily", default=None)
    p_apply.add_argument("--after", default="-1", help="只处理 i 大于该值的卡")
    p_apply.add_argument("--wait", default="0", help="开始前等待秒数, 最大 3")
    args = p.parse_args()
    if args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "chat":
        cmd_chat(args)
    elif args.cmd == "apply":
        cmd_apply(args)
    else:
        emit(
            {
                "error": "用法: zhipin_win.py list [--after 10] [--wait 1.2] | chat --pick 0,2,5 [--wait 0.8] | apply --count 20 --min-daily 90 --after 10 --wait 1.7",
            },
            2,
        )


if __name__ == "__main__":
    main()
