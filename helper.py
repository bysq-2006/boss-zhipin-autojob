# -*- coding: utf-8 -*-
"""BOSS直聘预筛: 只判断通勤。排除词/岗位/经验由 agent 自己看页面判断。stdout 一行 JSON。"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "memory.config.env")
CACHE_PATH = os.path.join(HERE, "helper.cache.json")
GEO_URL = "https://restapi.amap.com/v3/geocode/geo"
DRIVE_URL = "https://restapi.amap.com/v3/direction/driving"
HTTP_TIMEOUT = 20

# 楼栋/单元/室号等高德地理编码不认的后缀
_DETAIL_RES = [
    re.compile(r"[-—–]\s*[A-Za-z]\s*区"),
    re.compile(r"(?<![市县区])[A-Za-z]\s*区(?=\d|$)"),
    re.compile(r"[0-9一二三四五六七八九十百]+栋"),
    re.compile(r"[0-9一二三四五六七八九十百]+号楼"),
    re.compile(r"[0-9一二三四五六七八九十百]+幢"),
    re.compile(r"[0-9一二三四五六七八九十百]+单元"),
    re.compile(r"[0-9A-Za-z一二三四五六七八九十百]+座"),
    re.compile(r"[0-9一二三四五六七八九十百]+层"),
    re.compile(r"[0-9一二三四五六七八九十百]+楼"),
    re.compile(r"[0-9一二三四五六七八九十百]+室"),
    re.compile(r"第?[0-9一二三四五六七八九十百]+号"),
    re.compile(r"[-—–]\s*\d+$"),
]
_TRAIL_JUNK = re.compile(r"[\s\-—–_/\\,，.。#]+$")
_CITY_DISTRICT = re.compile(r"^(.+?市.+?区)")
_CITY = re.compile(r"^(.+?市)")


def _setup_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if reconf is not None:
            try:
                reconf(encoding="utf-8")
            except Exception:
                pass


def emit(payload: Dict[str, Any], code: int = 0) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    sys.stdout.write("\n")
    sys.stdout.flush()
    raise SystemExit(code)


def load_config(path: str = CONFIG_PATH) -> Dict[str, str]:
    cfg: Dict[str, str] = {}
    if not os.path.isfile(path):
        return cfg
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            cfg[key.strip()] = val.strip()
    return cfg


def load_cache() -> Dict[str, Any]:
    if not os.path.isfile(CACHE_PATH):
        return {"geo": {}, "drive": {}}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        data.setdefault("geo", {})
        data.setdefault("drive", {})
        return data
    except Exception:
        return {"geo": {}, "drive": {}}


def save_cache(cache: Dict[str, Any]) -> None:
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False)
    except Exception:
        pass


def http_get_json(url: str) -> Optional[Dict[str, Any]]:
    req = urllib.request.Request(url, headers={"User-Agent": "boss-zhipin-helper/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        data = json.loads(body)
        return data if isinstance(data, dict) else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None


def clean_building_details(addr: str) -> str:
    text = addr.strip()
    changed = True
    while changed:
        changed = False
        for pat in _DETAIL_RES:
            nxt = pat.sub("", text)
            if nxt != text:
                text = nxt
                changed = True
    text = _TRAIL_JUNK.sub("", text).strip()
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"[-—–]{2,}", "-", text)
    return text.strip(" -—–")


def address_candidates(addr: str) -> List[str]:
    raw = re.sub(r"\s+", " ", addr.strip())
    cleaned = clean_building_details(raw)
    out: List[str] = []

    def add(item: str) -> None:
        item = item.strip(" -—–")
        if item and item not in out:
            out.append(item)

    add(cleaned)
    add(raw)

    m_dist = _CITY_DISTRICT.search(cleaned) or _CITY_DISTRICT.search(raw)
    m_city = _CITY.search(cleaned) or _CITY.search(raw)
    if m_dist:
        district = m_dist.group(1)
        add(district)
        rest = cleaned[len(district) :].strip(" -—–") if cleaned.startswith(district) else ""
        if not rest and raw.startswith(district):
            rest = clean_building_details(raw[len(district) :]).strip(" -—–")
        if m_city and rest:
            # 成都市 + 园区/大厦名(去掉再残留的楼栋)
            rest_name = re.split(r"[\s\-—–]", rest, maxsplit=1)[0]
            rest_name = clean_building_details(rest_name)
            if rest_name:
                add(m_city.group(1) + rest_name)
    elif m_city:
        rest = cleaned[len(m_city.group(1)) :].strip(" -—–")
        if rest:
            add(m_city.group(1) + rest)

    return out


def geocode(addr: str, key: str, cache: Dict[str, Any]) -> Optional[str]:
    geo = cache.setdefault("geo", {})
    for cand in address_candidates(addr):
        if cand in geo:
            loc = geo[cand]
            if loc:
                return loc
            continue
        qs = urllib.parse.urlencode({"address": cand, "key": key})
        data = http_get_json("%s?%s" % (GEO_URL, qs))
        loc = None
        if data and str(data.get("status")) == "1":
            codes = data.get("geocodes") or []
            if codes and isinstance(codes, list) and codes[0].get("location"):
                loc = str(codes[0]["location"]).strip()
                if loc in ("", "[]"):
                    loc = None
        geo[cand] = loc
        if loc:
            save_cache(cache)
            return loc
    save_cache(cache)
    return None


def driving(
    origin: str, dest: str, key: str, cache: Dict[str, Any]
) -> Optional[Tuple[float, int]]:
    drive = cache.setdefault("drive", {})
    ck = "%s|%s" % (origin, dest)
    if ck in drive:
        hit = drive[ck]
        try:
            return float(hit["distance"]), int(hit["duration"])
        except (KeyError, TypeError, ValueError):
            pass
    qs = urllib.parse.urlencode({"origin": origin, "destination": dest, "key": key})
    data = http_get_json("%s?%s" % (DRIVE_URL, qs))
    if not data or str(data.get("status")) != "1":
        return None
    route = data.get("route") or {}
    paths = route.get("paths") or []
    if not paths:
        return None
    try:
        distance = float(paths[0]["distance"])
        duration = int(float(paths[0]["duration"]))
    except (KeyError, TypeError, ValueError):
        return None
    drive[ck] = {"distance": distance, "duration": duration}
    save_cache(cache)
    return distance, duration


def cmd_commute(company_addr: str, cfg: Dict[str, str], cache: Dict[str, Any]) -> Dict[str, Any]:
    key = cfg.get("AMAP_KEY", "")
    home = cfg.get("HOME_ADDRESS", "")
    try:
        max_min = int(float(cfg.get("MAX_COMMUTE_MINUTES", "60")))
    except ValueError:
        max_min = 60
    fail = {
        "status": "REJECT",
        "address": company_addr,
        "distance_km": 0,
        "commute_min": 0,
        "max_min": max_min,
        "reason": "无法解析公司地址",
    }
    if not key:
        fail["reason"] = "缺少 AMAP_KEY"
        return fail
    if not company_addr.strip():
        return fail
    if not home:
        fail["reason"] = "缺少 HOME_ADDRESS"
        return fail
    home_loc = geocode(home, key, cache)
    if not home_loc:
        fail["reason"] = "无法解析住址"
        return fail
    com_loc = geocode(company_addr, key, cache)
    if not com_loc:
        return fail
    routed = driving(home_loc, com_loc, key, cache)
    if not routed:
        fail["reason"] = "路径规划失败"
        return fail
    distance_m, duration_s = routed
    distance_km = round(distance_m / 1000.0, 1)
    commute_min = int(round(duration_s / 60.0))
    ok = commute_min <= max_min
    return {
        "status": "PASS" if ok else "REJECT",
        "address": company_addr,
        "distance_km": distance_km,
        "commute_min": commute_min,
        "max_min": max_min,
        "reason": "" if ok else "通勤超时",
    }


def usage() -> Dict[str, Any]:
    return {
        "status": "REJECT",
        "reason": "用法: helper.py commute <公司详细地址>",
    }


def main(argv: List[str]) -> None:
    _setup_stdio()
    if len(argv) < 2:
        emit(usage(), 2)
    cmd = argv[1].strip().lower()
    arg = " ".join(argv[2:]).strip()
    cfg = load_config()
    cache = load_cache()
    if cmd == "commute":
        if not arg:
            emit(
                {
                    "status": "REJECT",
                    "address": "",
                    "distance_km": 0,
                    "commute_min": 0,
                    "max_min": 0,
                    "reason": "缺少公司地址",
                },
                2,
            )
        emit(cmd_commute(arg, cfg, cache))
    emit(usage(), 2)


if __name__ == "__main__":
    main(sys.argv)
