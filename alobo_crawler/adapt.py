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


def occupied_from_onetime(bookings: list, step: int = SLOT_MIN) -> list[dict]:
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
            court = court_label(sid)
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


def build_grid(occupied: list[dict], *, branch: str = "", branch_name: str = "",
               step: int = SLOT_MIN, hours=(HOURS_START, HOURS_END),
               days: list[str] | None = None) -> dict:
    """Gom occupied -> cau truc luoi cho trang heatmap."""
    courts = sorted({c["court"] for c in occupied},
                    key=lambda x: (0, int(x.split()[-1])) if x.startswith("Sân ")
                    and x.split()[-1].isdigit() else (1, x))
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
