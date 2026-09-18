#!/usr/bin/env python3
"""scheduler.py — lập lịch quét sân (orchestration).

Vòng: mỗi `interval_min` phút, với mỗi branch × mỗi ngày T2–T6 trong `days_ahead`
ngày tới:  fetch_raw() -> decrypt() -> redact PII -> lưu data/<branch>__<date>.json
Rồi heatmap (server.py) tự đọc.

fetch_raw() và decrypt() là stub DO BẠN VIẾT (fetch_raw.py, decrypt.py). Scheduler
chỉ điều phối + giãn nhịp theo rate limit (30 req/phút). Nếu stub chưa viết,
scheduler chạy **DRY-RUN**: in đúng những call SẼ thực hiện rồi dừng.

    python scheduler.py --once      # quét 1 lượt
    python scheduler.py             # lặp theo interval
    python scheduler.py --plan      # chỉ in kế hoạch, không gọi gì
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time

import adapt  # dùng weekday helper + redact qua alobo_codec

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CONFIG = os.path.join(HERE, "config.json")

DEFAULT_CONFIG = {
    "branches": ["sport_bui_thi_xuan_badminton"],
    "days_ahead": 15,
    "weekdays_only": True,
    "interval_min": 30,
    "delay_sec": 5,          # >=2s để dưới 30 req/phút
    "fetch_schedule_month": True,
    "fetch_lock_yards": True,
    "fetch_cores_once": True,
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG):
        cfg.update(json.load(open(CONFIG, encoding="utf-8")))
    return cfg


def target_dates(cfg, today=None) -> list[dt.date]:
    today = today or dt.date.today()
    out = []
    for i in range(1, cfg["days_ahead"] + 1):
        d = today + dt.timedelta(days=i)
        if cfg["weekdays_only"] and d.weekday() >= 5:
            continue
        out.append(d)
    return out


def build_plan(cfg) -> list[dict]:
    """Danh sách call SẼ thực hiện: {endpoint, params, out}."""
    plan = []
    dates = target_dates(cfg)
    for b in cfg["branches"]:
        if cfg.get("fetch_cores_once"):
            plan.append({"endpoint": "get_cores", "params": {"branchId": b},
                         "out": f"{b}__cores.json"})
        if cfg.get("fetch_lock_yards"):
            plan.append({"endpoint": "get_lock_yards", "params": {"branchId": b},
                         "out": f"{b}__locks.json"})
        if cfg.get("fetch_schedule_month"):
            for m in sorted({d.strftime("%Y-%m") for d in dates}):
                plan.append({"endpoint": "get_schedule_bookings",
                             "params": {"branchId": b, "month": m},
                             "out": f"{b}__schedule_{m}.json"})
        for d in dates:
            ds = d.isoformat()
            plan.append({"endpoint": "get_onetime_bookings",
                         "params": {"branchId": b, "startDate": ds, "endDate": ds},
                         "out": f"{b}__{ds}.json"})
    return plan


def _try_plugins():
    """Trả (fetch_raw, decrypt) neu ca hai da viet; else None + ly do."""
    try:
        import fetch_raw as fr
        import decrypt as dc
    except Exception as e:
        return None, f"khong import duoc plugin: {e}"
    # thu goi de biet da viet chua (stub nem NotImplementedError)
    for fn, name in ((fr.fetch_raw, "fetch_raw"), (dc.decrypt, "decrypt")):
        pass
    return (fr.fetch_raw, dc.decrypt), None


def run_pass(cfg, dry=False) -> None:
    plan = build_plan(cfg)
    print(f"[{dt.datetime.now():%H:%M:%S}] Kế hoạch: {len(plan)} call "
          f"({len(cfg['branches'])} sân × {len(target_dates(cfg))} ngày + phụ trợ)")

    if dry:
        for p in plan:
            print(f"   GET {p['endpoint']:22} {p['params']}  -> data/{p['out']}")
        est = len(plan) * cfg["delay_sec"]
        print(f"   ~{est:.0f}s/lượt với delay {cfg['delay_sec']}s "
              f"(≈{60/cfg['delay_sec']:.0f} req/phút, giới hạn 30).")
        return

    plugins, err = _try_plugins()
    fetch_raw = decrypt = None
    if plugins:
        fetch_raw, decrypt = plugins

    os.makedirs(DATA, exist_ok=True)
    done = fail = 0
    for p in plan:
        try:
            env = fetch_raw(p["endpoint"], p["params"])   # BẠN viết
            data = decrypt(env)                            # BẠN viết
            data = adapt_redact(data)                      # vứt PII trước khi ghi
            with open(os.path.join(DATA, p["out"]), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            done += 1
            print(f"   ✓ {p['out']}")
        except NotImplementedError as e:
            print(f"\n[DRY-RUN] Stub chưa viết ({e}).")
            print("   -> Viết fetch_raw.py + decrypt.py rồi chạy lại. Kế hoạch:")
            run_pass(cfg, dry=True)
            return
        except Exception as e:
            fail += 1
            print(f"   ✗ {p['out']}: {e}")
        time.sleep(cfg["delay_sec"])   # tôn trọng rate limit
    print(f"[{dt.datetime.now():%H:%M:%S}] Xong: {done} ok, {fail} lỗi. "
          f"Mở heatmap: python server.py")


def adapt_redact(data):
    """Vứt PII (guest_name/phone…) trước khi ghi ra disk."""
    try:
        import alobo_codec
        return alobo_codec.redact(data)
    except Exception:
        return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="quét 1 lượt rồi dừng")
    ap.add_argument("--plan", action="store_true", help="chỉ in kế hoạch, không gọi gì")
    args = ap.parse_args()
    cfg = load_config()

    if args.plan:
        run_pass(cfg, dry=True)
        return
    if args.once:
        run_pass(cfg)
        return
    print(f"Lặp mỗi {cfg['interval_min']} phút. Ctrl+C để dừng.")
    try:
        while True:
            run_pass(cfg)
            time.sleep(cfg["interval_min"] * 60)
    except KeyboardInterrupt:
        print("\ndừng.")


if __name__ == "__main__":
    main()
