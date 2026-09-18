#!/usr/bin/env python3
"""Chuyen du lieu get_onetime_bookings (da giai ma) -> luoi trang thai chuan hoa.

SHAPE THAT cua get_onetime_bookings.json (list booking 1 ngay):
  [
    {
      "id": "...", "time": "2026-09-19T14:00:00.000", "duration": 120,
      "services": [
        {"serviceId": "san_2", "startTime": "2026-09-19T14:00:00.000",
         "duration": 120, "price": ..., "amount": ..., "branchServiceType": "core"}
      ],
      "type": "groupOneTime", "status": 1, "totalPrice": ...
    }, ...
  ]

Mot service = mot san (serviceId) bi dat tu startTime, keo dai `duration` phut.
Con lai trong gio hoat dong = TRONG (free).

Adapter cung nhan dinh dang da chuan hoa cua chinh no (dict co "occupied") de
tron du lieu mau + du lieu that. KHONG dung key/API - chi doc JSON co san.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

# PII co the co trong response that -> khong bao gio doc/giu.
# Adapter chi lay serviceId/thoi gian/duration nen tu nhien khong dinh PII.

SLOT_MIN = 30
HOURS_START = "06:00"
HOURS_END = "22:00"
FOCUS = {"start": "18:00", "end": "22:00", "weekdays_only": True}
WD_VN = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]


def court_label(service_id: str) -> str:
    """'san_2' -> 'Sân 2'. Giu nguyen neu khong khop mau."""
    s = str(service_id)
    if s.lower().startswith("san_") and s[4:].isdigit():
        return f"Sân {int(s[4:])}"
    return s


def _slots(start: str, end: str, step: int) -> list[str]:
    out, t = [], dt.datetime.strptime(start, "%H:%M")
    e = dt.datetime.strptime(end, "%H:%M")
    while t < e:
        out.append(t.strftime("%H:%M"))
        t += dt.timedelta(minutes=step)
    return out


def _covered_slots(start_iso: str, duration_min: int, step: int) -> tuple[str, list[str]]:
    """(date, [HH:MM,...]) cac o step-phut ma booking nay chiem."""
    t = dt.datetime.fromisoformat(start_iso.replace("Z", ""))
    # canh ve luoi step phut
    base = t.replace(minute=(t.minute // step) * step, second=0, microsecond=0)
    n = max(1, (duration_min + step - 1) // step)
    slots = [(base + dt.timedelta(minutes=step * i)).strftime("%H:%M") for i in range(n)]
    return t.date().isoformat(), slots


def court_name_map(cores_doc) -> dict:
    """cores doc -> {serviceId: ten hien thi}. Dung de booking/lock khop ten cores."""
    cores = (cores_doc.get("cores") if isinstance(cores_doc, dict) else cores_doc) or []
    m = {}
    for c in cores:
        if isinstance(c, dict) and c.get("id"):
            m[c["id"]] = c.get("name") or court_label(c["id"])
    return m


def _court(sid, court_map):
    if court_map and sid in court_map:
        return court_map[sid]
    return court_label(sid)


def court_sport_map(cores_doc) -> dict:
    """cores doc -> {ten_san: 'pickleball'|'badminton'} theo `setting`/ten."""
    cores = (cores_doc.get("cores") if isinstance(cores_doc, dict) else cores_doc) or []
    out = {}
    for c in cores:
        if isinstance(c, dict) and c.get("id"):
            nm = c.get("name") or court_label(c["id"])
            blob = (str(c.get("setting", "")) + " " + str(nm)).lower()
            out[nm] = "pickleball" if "pick" in blob else "badminton"
    return out


def occupied_from_onetime(bookings: list, step: int = SLOT_MIN, court_map: dict | None = None) -> list[dict]:
    """List booking -> list {court,date,slot,status='booked'} (da khu trung lap)."""
    seen, out = set(), []
    for bk in bookings:
        if not isinstance(bk, dict):
            continue
        services = bk.get("services") or []
        # phong khi khong co services: dung truong cap booking
        if not services and bk.get("time"):
            services = [{"serviceId": bk.get("serviceId", "?"),
                         "startTime": bk["time"], "duration": bk.get("duration", step)}]
        for sv in services:
            sid = sv.get("serviceId", "?")
            start = sv.get("startTime") or sv.get("time")
            dur = int(sv.get("duration") or step)
            if not start:
                continue
            court = _court(sid, court_map)
            date, slots = _covered_slots(start, dur, step)
            for sl in slots:
                key = (court, date, sl)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"court": court, "date": date, "slot": sl, "status": "booked"})
    return out


def _is_normalized(doc: Any) -> bool:
    return isinstance(doc, dict) and ("occupied" in doc or "cells" in doc)


def adapt_doc(doc: Any, step: int = SLOT_MIN) -> list[dict]:
    """Nhan raw list HOAC dict da chuan hoa -> list o KHONG-trong."""
    if _is_normalized(doc):
        cells = doc.get("occupied") or doc.get("cells") or []
        norm = []
        for c in cells:
            norm.append({"court": court_label(c["court"]) if str(c["court"]).startswith("san_")
                         else c["court"],
                         "date": c["date"], "slot": c["slot"],
                         "status": c.get("status", "booked")})
        return norm
    if isinstance(doc, dict) and isinstance(doc.get("data"), list):
        doc = doc["data"]   # phong khi bi boc {status, data:[...]}
    if isinstance(doc, list):
        return occupied_from_onetime(doc, step)
    return []


def courts_from_cores(doc) -> list[dict]:
    """cores doc -> [{'id','name'}] cac san status=1, theo priority."""
    cores = doc.get("cores") if isinstance(doc, dict) else None
    if not cores:
        return []
    active = [c for c in cores if c.get("status", 1) == 1 and c.get("id")]
    active.sort(key=lambda c: c.get("priority", 999))
    return [{"id": c["id"], "name": c.get("name") or court_label(c["id"])} for c in active]


def locked_from_lockyards(doc, step: int = SLOT_MIN, court_map: dict | None = None) -> list[dict]:
    """lock_yards doc (list lock) -> cac o status='locked'.

    Moi lock: {startTime, endTime, servicesId:[san..], frequency, skipDates}.
    frequency rong -> khoa dung ngay cua startTime. frequency co gia tri
    (weekday) -> ap cho moi ngay khop weekday trong khoang start..+8 tuan,
    tru skipDates. (Best-effort; du lieu thuc te dang gap frequency rong.)
    """
    locks = doc if isinstance(doc, list) else (doc.get("data") if isinstance(doc, dict) else [])
    out, seen = [], set()
    for lk in locks or []:
        if not isinstance(lk, dict):
            continue
        start, end = lk.get("startTime"), lk.get("endTime")
        courts = lk.get("servicesId") or lk.get("services") or lk.get("courts") or []
        if not start or not end or not courts:
            continue
        try:
            s_dt = dt.datetime.fromisoformat(str(start).replace("Z", ""))
            e_dt = dt.datetime.fromisoformat(str(end).replace("Z", ""))
        except ValueError:
            continue
        skip = set(lk.get("skipDates") or [])
        freq = lk.get("frequency") or []
        # tap ngay ap dung
        dates = []
        if not freq:
            dates = [s_dt.date()]
        else:
            wdays = {int(x) for x in freq if isinstance(x, int) or str(x).isdigit()}
            for i in range((8 * 7)):  # 8 tuan toi
                d = s_dt.date() + dt.timedelta(days=i)
                if d.weekday() in wdays:
                    dates.append(d)
        dur_min = int((e_dt - s_dt).total_seconds() // 60)
        for d in dates:
            if d.isoformat() in skip:
                continue
            base = s_dt.replace(minute=(s_dt.minute // step) * step, second=0, microsecond=0)
            n = max(1, (dur_min + step - 1) // step)
            for i in range(n):
                sl = (base + dt.timedelta(minutes=step * i)).strftime("%H:%M")
                for cid in courts:
                    court = _court(cid, court_map)
                    key = (court, d.isoformat(), sl)
                    if key not in seen:
                        seen.add(key)
                        out.append({"court": court, "date": d.isoformat(),
                                    "slot": sl, "status": "locked"})
    return out


def _num(x):
    try:
        return int(round(float(x)))
    except (TypeError, ValueError):
        return None


def _hhmm(x):
    if not x:
        return None
    s = str(x)
    if "T" in s:
        s = s.split("T", 1)[1]
    return s[:5] if len(s) >= 5 and s[2] == ":" else None


def _daynorm(x):
    """-> list weekday 0=T2..6=CN (JSON-safe), hoac None (moi ngay)."""
    if x in (None, "", [], "all"):
        return None
    if isinstance(x, str):
        m = {"weekday": [0, 1, 2, 3, 4], "weekdays": [0, 1, 2, 3, 4],
             "weekend": [5, 6], "weekends": [5, 6]}
        return m.get(x.lower())
    if isinstance(x, (list, set, tuple)):
        out = set()
        for v in x:
            if isinstance(v, int):
                out.add(v % 7)
            elif str(v).isdigit():
                out.add(int(v) % 7)
        return sorted(out) or None
    return None


# Cac key co the gap cho khung gia trong products (best-effort, chinh khi co sample)
_PRICE_LIST_KEYS = ("prices", "priceByTime", "timeFrames", "priceFrames", "frames",
                    "priceConfig", "timePrices", "priceList")
_PRICE_FLAT_KEYS = ("price", "pricePerHour", "amount", "unitPrice", "value", "cost")


def name_from_branch(doc) -> str | None:
    """get_branch doc -> ten chi nhanh. Ne '***' (bi redact), fallback nameEn."""
    if isinstance(doc, dict):
        d = doc.get("data") if isinstance(doc.get("data"), dict) else doc
        for k in ("name", "nameEn", "branchName", "title"):
            v = d.get(k)
            if v and v != "***":
                return v
    return None


def _time_range(s):
    """'17:00-22:00' / '5:00-8:00' -> ('17:00','22:00'). None neu hong."""
    if not s or "-" not in str(s):
        return None, None
    a, b = str(s).split("-", 1)

    def fix(t):
        t = t.strip()
        if ":" not in t:
            return None
        h, m = t.split(":", 1)
        try:
            return f"{int(h):02d}:{int(m):02d}"
        except ValueError:
            return None
    return fix(a), fix(b)


def _dow_range(s):
    """'1-5'->[0..4] (T2-T6); '6-7'->[5,6]; '12345'->[0..4]; None=moi ngay.
    1=T2..7=CN -> 0=T2..6=CN."""
    if not s:
        return None
    s = str(s)
    nums = []
    if "-" in s:
        a, b = s.split("-", 1)
        if a.isdigit() and b.isdigit():
            nums = list(range(int(a), int(b) + 1))
    else:
        nums = [int(c) for c in s if c.isdigit()]
    days = sorted({(n - 1) % 7 for n in nums if 1 <= n <= 7})
    return days or None


def prices_from_core_types(doc, cores_doc=None) -> dict:
    """get_core_types -> {ten_san: [{start,end,price,days}]}. Dung priceOneTime.

    Shape that (ALOBO): list core_type, moi cai co `targets` (dict); moi target co
    `specialPrice`[] voi time='HH:MM-HH:MM', dateRangeWeek='1-5', priceOneTime.
    San <- cores co `setting` == target-key (hoac core_type id).
    """
    types = doc if isinstance(doc, list) else (
        doc.get("data") if isinstance(doc, dict) and isinstance(doc.get("data"), list) else [])
    cores = (cores_doc.get("cores") if isinstance(cores_doc, dict) else cores_doc) or []
    by_setting: dict[str, list] = {}
    all_courts = []
    for c in cores:
        if isinstance(c, dict) and c.get("id"):
            nm = c.get("name") or court_label(c["id"])
            all_courts.append(nm)
            by_setting.setdefault(str(c.get("setting", "")), []).append(nm)

    def target_rules(tg):
        rules = []
        for sp in tg.get("specialPrice") or []:
            if not isinstance(sp, dict):
                continue
            st, en = _time_range(sp.get("time"))
            pr = _num(sp.get("priceOneTime"))
            if pr is None:
                pr = _num(sp.get("price"))
            if pr is None or not st:
                continue
            rules.append({"start": st, "end": en or "24:00", "price": pr,
                          "days": _dow_range(sp.get("dateRangeWeek"))})
        if not rules:
            base = _num(tg.get("priceOneTime")) or _num(tg.get("price"))
            if base:
                rules = [{"start": "00:00", "end": "24:00", "price": base, "days": None}]
        return rules

    out: dict[str, list] = {}
    single = len(types) == 1
    for t in types:
        if not isinstance(t, dict):
            continue
        targets = t.get("targets") or {}
        for tkey, tg in (targets.items() if isinstance(targets, dict) else []):
            if not isinstance(tg, dict):
                continue
            rules = target_rules(tg)
            if not rules:
                continue
            courts = by_setting.get(str(tkey)) or by_setting.get(str(t.get("id"))) or []
            if not courts and single and len(targets) == 1:
                courts = all_courts
            for ct in (courts or ["*"]):
                out.setdefault(ct, []).extend(rules)
        # neu type khong co targets nhung co gia phang
        if not targets:
            base = _num(t.get("normalPriceOneTime")) or _num(t.get("normalPrice"))
            if base:
                for ct in (all_courts or ["*"]):
                    out.setdefault(ct, []).append({"start": "00:00", "end": "24:00",
                                                   "price": base, "days": None})
    return out


def prices_from_products(doc) -> dict:
    """products doc -> {ten_san: [ {start,end,price,days} ]}.  '*' = ap moi san.

    Phong thu nhieu shape. Neu khong nhan ra -> {} (UI se an gia). Khi co sample
    that, chinh key trong _PRICE_LIST_KEYS / _PRICE_FLAT_KEYS / court-ref o duoi.
    """
    items = None
    if isinstance(doc, dict):
        items = doc.get("products") or doc.get("data") or doc.get("items")
    if items is None and isinstance(doc, list):
        items = doc
    out: dict[str, list] = {}
    for p in items or []:
        if not isinstance(p, dict):
            continue
        cid = (p.get("serviceId") or p.get("coreId") or p.get("core_id")
               or p.get("courtId") or p.get("id") or "*")
        court = court_label(cid) if str(cid).startswith("san_") else ("*" if cid == "*" else str(cid))
        rules = []
        for key in _PRICE_LIST_KEYS:
            v = p.get(key)
            if isinstance(v, list) and v:
                for fr in v:
                    if not isinstance(fr, dict):
                        continue
                    pr = _num(fr.get("price") or fr.get("amount") or fr.get("value") or fr.get("cost"))
                    if pr is None:
                        continue
                    rules.append({
                        "start": _hhmm(fr.get("startTime") or fr.get("start") or fr.get("from")) or "00:00",
                        "end": _hhmm(fr.get("endTime") or fr.get("end") or fr.get("to")) or "24:00",
                        "price": pr,
                        "days": _daynorm(fr.get("dayOfWeek") or fr.get("days")
                                         or fr.get("dayType") or fr.get("frequency")),
                    })
                if rules:
                    break
        if not rules:
            for key in _PRICE_FLAT_KEYS:
                pr = _num(p.get(key))
                if pr is not None:
                    rules.append({"start": "00:00", "end": "24:00", "price": pr, "days": None})
                    break
        if rules:
            out.setdefault(court, []).extend(rules)
    return out


def price_at(prices: dict, court: str, weekday: int, slot: str):
    """Tra gia 1 khung: uu tien rule dung san, else '*'. None neu khong co."""
    for key in (court, "*"):
        for r in prices.get(key, []):
            if (r["days"] is None or weekday in r["days"]) and r["start"] <= slot < r["end"]:
                return r["price"]
    return None


def merge_status(*cell_lists) -> list[dict]:
    """Gop nhieu list o, uu tien: booked > locked > event (booked de len tren).

    Neu mot o vua booked vua locked -> hien 'booked' (co nguoi giu). O chi locked
    -> 'locked' (mo nhung khoa, cho mo de rinh)."""
    prio = {"booked": 3, "event": 2, "locked": 1, "free": 0}
    best = {}
    for lst in cell_lists:
        for c in lst:
            k = (c["court"], c["date"], c["slot"])
            if prio.get(c["status"], 0) >= prio.get(best.get(k, {}).get("status", "free"), 0):
                best[k] = c
    return list(best.values())


def build_grid(occupied: list[dict], *, branch: str = "", branch_name: str = "",
               step: int = SLOT_MIN, hours=(HOURS_START, HOURS_END),
               days: list[str] | None = None,
               courts_override: list[str] | None = None) -> dict:
    """Gom occupied -> cau truc luoi cho trang heatmap.

    courts_override: danh sach ten san theo thu tu (tu cores) - dung de hien du
    ca san khong co booking, va dung ten/thu tu that."""
    # sort theo NHOM ten + SO: 'C.Lông 1', 'C.Lông 2'... roi 'Pick 7','Pick 8'...
    def _key(x):
        m = re.match(r"^(.*?)(\d+)\s*$", str(x))
        return (m.group(1).strip().lower(), int(m.group(2))) if m else (str(x).lower(), 0)
    found = {c["court"] for c in occupied}
    courts = sorted(found | set(courts_override or []), key=_key)
    if days is None:
        days = sorted({c["date"] for c in occupied})
    day_objs = []
    for d in days:
        wd = dt.date.fromisoformat(d).weekday()
        day_objs.append({"date": d, "weekday": WD_VN[wd], "is_weekend": wd >= 5})
    return {
        "branch": branch,
        "branch_name": branch_name or branch,
        "slot_minutes": step,
        "hours": {"start": hours[0], "end": hours[1]},
        "slots": _slots(hours[0], hours[1], step),
        "focus": FOCUS,
        "courts": courts,
        "days": day_objs,
        "occupied": occupied,   # con lai (trong gio) = free
    }


if __name__ == "__main__":
    import json
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "data/get_onetime_bookings.json"
    doc = json.load(open(path, encoding="utf-8"))
    occ = adapt_doc(doc)
    grid = build_grid(occ, branch_name="(test)")
    print(f"occupied cells: {len(occ)}")
    print("courts:", grid["courts"])
    print("days:", [d["date"] for d in grid["days"]])
    # dem o trong trong khung 18-22h
    focus_slots = [s for s in grid["slots"] if "18:00" <= s < "22:00"]
    occ_set = {(c["court"], c["date"], c["slot"]) for c in occ}
    free = sum(1 for ct in grid["courts"] for d in grid["days"]
               for s in focus_slots if (ct, d["date"], s) not in occ_set)
    print(f"o TRONG 18-22h: {free} / {len(grid['courts'])*len(grid['days'])*len(focus_slots)}")
