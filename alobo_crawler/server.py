#!/usr/bin/env python3
"""Server xem heatmap san trong - stdlib, khong can cai gi.

    python server.py            # http://127.0.0.1:8000
    python server.py --port 9000 --data data

Doc moi file data/*.json (tru file an), adapt sang luoi trang thai, tron theo
branch, phuc vu cho trang viz/index.html. KHONG API, KHONG decrypt - chi doc
JSON da giai ma san co trong thu muc data/.

Dat file get_onetime_bookings da giai ma vao data/ (moi file 1 ngay). File mau
sample_*.json co san de xem thu ngay.
"""
from __future__ import annotations

import argparse
import hmac
import ipaddress
import time
import datetime as dt
import glob
import json
import os
import posixpath
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import adapt

HERE = os.path.dirname(os.path.abspath(__file__))


def branch_meta(doc, fallback_name):
    """Lay branch/branch_name neu doc la dict chuan hoa; else mac dinh."""
    if isinstance(doc, dict):
        return doc.get("branch", fallback_name), doc.get("branch_name", fallback_name)
    return fallback_name, fallback_name


_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _dir_names() -> dict:
    try:
        d = json.load(open(DIRECTORY_PATH, encoding="utf-8"))
        return {b["id"]: b.get("name", b["id"]) for b in d.get("branches", []) if b.get("id")}
    except Exception:
        return {}


def _classify(name: str):
    """(branch_key, kind) tu ten file. kind: onetime|schedule|locks|cores."""
    stem = name.replace(".json", "")
    branch = stem.split("__")[0] if "__" in stem else "sport_bui_thi_xuan_badminton"
    suffix = stem.split("__", 1)[1] if "__" in stem else stem
    if suffix == "cores":
        return branch, "cores"
    if suffix == "core_types":
        return branch, "core_types"
    if suffix == "branch":
        return branch, "branch"
    if suffix == "locks":
        return branch, "locks"
    if suffix == "products":
        return branch, "products"
    if suffix.startswith("schedule"):
        return branch, "schedule"
    return branch, "onetime"  # ngay-cu-the hoac file don


def load_data(data_dir: str) -> dict:
    """Doc + adapt moi file -> gom theo branch (booked+locked+cores) -> list grid."""
    files = sorted(glob.glob(os.path.join(data_dir, "*.json")))
    names = _dir_names()
    branches: dict[str, dict] = {}

    def slot_for(key, pretty=None):
        return branches.setdefault(key, {"branch": key, "branch_name": pretty or names.get(key, key),
                                         "booked": [], "booking_lists": [], "lock_docs": [],
                                         "cores": None, "core_types": None, "branch_doc": None,
                                         "products": None, "days_hint": None, "dates": set()})

    for path in files:
        name = os.path.basename(path)
        if name.startswith("_") or name.startswith("."):
            continue
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except Exception as e:
            print(f"  [bo qua] {name}: {e}")
            continue

        # file da chuan hoa (sample) -> branch rieng, coi nhu 'booked' (co san status)
        if isinstance(doc, dict) and ("occupied" in doc or "cells" in doc):
            key = doc.get("branch", name.replace(".json", ""))
            s = slot_for(key, doc.get("branch_name", key))
            s["booked"].extend(adapt.adapt_doc(doc))
            if doc.get("days"):
                s["days_hint"] = [d["date"] for d in doc["days"]]
            continue

        key, kind = _classify(name)
        s = slot_for(key)
        if kind == "cores":
            s["cores"] = doc
        elif kind == "core_types":
            s["core_types"] = doc
        elif kind == "branch":
            s["branch_doc"] = doc
        elif kind == "products":
            s["products"] = doc
        elif kind == "locks":
            s["lock_docs"].append(doc)           # đặt tên sân sau khi có cores
        else:  # onetime | schedule -> booked
            body = doc.get("data") if isinstance(doc, dict) and isinstance(doc.get("data"), list) else doc
            if isinstance(body, list):
                s["booking_lists"].append(body)  # đặt tên sân sau khi có cores
            if kind == "onetime":
                m = _DATE_RE.search(name)
                if m:
                    s["dates"].add(m.group(0))   # ngay da CAO (du rong hay ban)

    window = _window_dates()   # {hôm nay .. hôm nay + N-1} — ẩn ngày đã qua / ngoài cửa sổ
    out = []
    for key, s in branches.items():
        cores = adapt.courts_from_cores(s["cores"]) if s["cores"] else []
        court_order = [c["name"] for c in cores]
        cmap = adapt.court_name_map(s["cores"]) if s["cores"] else {}
        # giờ mới đặt tên sân (đã có cores) cho booking + lock
        booked = list(s["booked"])
        for body in s["booking_lists"]:
            booked += adapt.occupied_from_onetime(body, court_map=cmap)
        locked = []
        for d in s["lock_docs"]:
            locked += adapt.locked_from_lockyards(d, court_map=cmap)
        occ = adapt.merge_status(booked, locked)
        # ngay hien thi: uu tien ngay DA CAO (onetime), else days_hint; luon
        # loc trong cua so [hom nay .. hom nay + N-1] — file ngay qua giu tren disk
        # (retention sau) nhung khong hien.
        if s["dates"]:
            days = sorted(d for d in s["dates"] if d in window)
            keep = set(days)
            occ = [c for c in occ if c["date"] in keep]   # bo cell ngoai cua so
        else:
            dh = s["days_hint"] or []
            days = [d for d in dh if d in window] or dh
        name = adapt.name_from_branch(s["branch_doc"]) or s["branch_name"]
        grid = adapt.build_grid(occ, branch=key, branch_name=name,
                                days=days, courts_override=court_order or None)
        grid["prices"] = adapt.prices_from_core_types(s["core_types"], s["cores"]) if s["core_types"] else {}
        grid["court_sport"] = adapt.court_sport_map(s["cores"]) if s["cores"] else {}
        out.append(grid)
    out.sort(key=lambda g: g["branch_name"])
    monitored = set(read_config().get("branches", []))
    for g in out:
        g["monitored"] = g["branch"] in monitored     # sân đang chọn để cào
    return {"branches": out, "count": len(out), "monitored": sorted(monitored)}


CONFIG_PATH = os.path.join(HERE, "config.json")
DIRECTORY_PATH = os.path.join(HERE, "branches_directory.json")
BRANCH_RE = re.compile(r"^[a-z0-9_\-]{2,80}$")


def read_config() -> dict:
    try:
        import scheduler
        return scheduler.load_config()
    except Exception:
        cfg = {"branches": [], "days_window": 21}
        if os.path.exists(CONFIG_PATH):
            try:
                cfg.update(json.load(open(CONFIG_PATH, encoding="utf-8")))
            except Exception:
                pass
        return cfg


def write_config(patch: dict) -> dict:
    """Ghi config.json: chỉ nhận khoá cho phép (branches, days_window). Giữ khoá khác."""
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))
    if "branches" in patch:
        bs = [b.strip() for b in patch["branches"]
              if isinstance(b, str) and BRANCH_RE.match(b.strip())]
        cfg["branches"] = list(dict.fromkeys(bs))   # khử trùng lặp, giữ thứ tự
    if "days_window" in patch:
        try:
            cfg["days_window"] = max(1, min(60, int(patch["days_window"])))
        except (TypeError, ValueError):
            raise ValueError("days_window phải là số 1–60")
        cfg.pop("days_ahead", None)                 # dọn khoá cũ nếu còn
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg


def _window_dates() -> set:
    """Tập ISO date trong cửa sổ [hôm nay .. hôm nay + N-1] theo config."""
    cfg = read_config()
    try:
        import scheduler
        return {d.isoformat() for d in scheduler.target_dates(cfg)}
    except Exception:
        today = dt.date.today()
        n = int(cfg.get("days_window", cfg.get("days_ahead", 21)) or 21)
        wd_only = cfg.get("weekdays_only", False)
        out = set()
        for i in range(max(1, min(60, n))):
            d = today + dt.timedelta(days=i)
            if wd_only and d.weekday() >= 5:
                continue
            out.add(d.isoformat())
        return out


def read_directory() -> dict:
    """Danh ba san: file bundled + branch dang theo doi + branch co du lieu."""
    entries = {}
    if os.path.exists(DIRECTORY_PATH):
        try:
            for b in json.load(open(DIRECTORY_PATH, encoding="utf-8")).get("branches", []):
                if b.get("id"):
                    entries[b["id"]] = {"id": b["id"], "name": b.get("name", b["id"]),
                                        "sport": b.get("sport", "")}
        except Exception:
            pass
    cfg = read_config()
    monitored = set(cfg.get("branches", []))
    # branch co du lieu tren dia
    payload = load_data(os.path.join(HERE, "data"))
    with_data = {g["branch"] for g in payload["branches"]}
    names = {g["branch"]: g["branch_name"] for g in payload["branches"]}
    for bid in monitored | with_data:
        if bid == "demo":
            continue
        e = entries.setdefault(bid, {"id": bid, "name": names.get(bid, bid), "sport": ""})
        if bid in names and (e["name"] == bid):
            e["name"] = names[bid]
    out = []
    for bid, e in entries.items():
        out.append({**e, "monitored": bid in monitored, "has_data": bid in with_data})
    out.sort(key=lambda x: (not x["monitored"], x["name"].lower()))
    return {"branches": out, "monitored": sorted(monitored)}


# ---------------------------------------------------------------- crawl control
LOG_PATH = os.path.join(HERE, "data", "_crawl.log")
_crawl = {"proc": None, "started": None, "started_ts": None, "finished": None,
          "returncode": None, "lock": threading.Lock()}
_auto = {"enabled": False, "interval_min": 30, "next_run": None}
WD_VN = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]


def _fmt_age(ts: float) -> str:
    if not ts:
        return "—"
    s = max(0, int(dt.datetime.now().timestamp() - ts))
    if s < 60:
        return f"{s}s trước"
    if s < 3600:
        return f"{s // 60} phút trước"
    if s < 86400:
        return f"{s // 3600} giờ trước"
    return f"{s // 86400} ngày trước"


def crawl_coverage(started_ts: float | None = None) -> dict:
    """Với mỗi branch × ngày trong cửa sổ: có file chưa + cào lúc nào (mtime).

    ``started_ts`` = mốc bắt đầu lượt cào gần nhất (nếu có). File mtime >= mốc này
    được đánh dấu ``fresh`` (vừa cào trong lượt), để phân biệt data cũ vẫn còn.
    """
    cfg = read_config()
    try:
        import scheduler
        dates = scheduler.target_dates(cfg)
    except Exception:
        today = dt.date.today()
        n = int(cfg.get("days_window", cfg.get("days_ahead", 21)) or 21)
        dates = [today + dt.timedelta(days=i) for i in range(max(1, min(60, n)))
                 if not (cfg.get("weekdays_only", False)
                         and (today + dt.timedelta(days=i)).weekday() >= 5)]
    branches = []
    for b in cfg.get("branches", []):
        days = []
        for d in dates:
            p = os.path.join(HERE, "data", f"{b}__{d.isoformat()}.json")
            ex = os.path.isfile(p)
            mt = os.path.getmtime(p) if ex else 0
            fresh = bool(started_ts and ex and mt >= started_ts)
            days.append({"date": d.isoformat(), "weekday": WD_VN[d.weekday()],
                         "has": ex, "fresh": fresh, "age": _fmt_age(mt), "mtime": mt})
        aux = {}
        for suffix in ("cores", "locks"):
            p = os.path.join(HERE, "data", f"{b}__{suffix}.json")
            aux[suffix] = {"has": os.path.isfile(p),
                           "age": _fmt_age(os.path.getmtime(p)) if os.path.isfile(p) else "—"}
        have = sum(1 for x in days if x["has"])
        fresh = sum(1 for x in days if x["fresh"])
        branches.append({"branch": b, "days": days, "aux": aux,
                         "have": have, "fresh": fresh, "total": len(days)})
    # lần cào gần nhất = file data mới nhất
    files = glob.glob(os.path.join(HERE, "data", "*.json"))
    files = [f for f in files if not os.path.basename(f).startswith(("_", "sample_"))]
    newest = max((os.path.getmtime(f) for f in files), default=0)
    return {"branches": branches, "interval_min": cfg.get("interval_min", 30),
            "days_window": window_size_cfg(cfg), "tracking": started_ts is not None,
            "started_ts": started_ts,
            "last_data_age": _fmt_age(newest), "last_data_ts": newest}


def window_size_cfg(cfg) -> int:
    try:
        import scheduler
        return scheduler.window_size(cfg)
    except Exception:
        return int(cfg.get("days_window", cfg.get("days_ahead", 21)) or 21)


def crawl_status() -> dict:
    with _crawl["lock"]:
        proc = _crawl["proc"]
        if proc is not None and proc.poll() is not None:
            _crawl["returncode"] = proc.returncode
            _crawl["finished"] = _crawl["finished"] or dt.datetime.now().isoformat(timespec="seconds")
            _crawl["proc"] = None
        running = _crawl["proc"] is not None
    log = ""
    try:
        with open(LOG_PATH, encoding="utf-8", errors="replace") as f:
            log = "".join(f.readlines()[-40:])
    except FileNotFoundError:
        pass
    return {"running": running, "started": _crawl["started"], "finished": _crawl["finished"],
            "returncode": _crawl["returncode"], "log_tail": log,
            "coverage": crawl_coverage(_crawl.get("started_ts")),
            "auto": {"enabled": _auto["enabled"], "interval_min": _auto["interval_min"],
                     "next_run": _auto["next_run"]}}


def start_crawl() -> dict:
    with _crawl["lock"]:
        if _crawl["proc"] is not None and _crawl["proc"].poll() is None:
            return {"ok": False, "error": "đang chạy rồi"}
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        logf = open(LOG_PATH, "w", encoding="utf-8")
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        _crawl["proc"] = subprocess.Popen(
            [sys.executable, os.path.join(HERE, "scheduler.py"), "--once"],
            cwd=HERE, stdout=logf, stderr=subprocess.STDOUT, env=env)
        now = dt.datetime.now()
        _crawl["started"] = now.isoformat(timespec="seconds")
        # trừ 1s để file ghi ngay đầu lượt không bị lệch mtime < started_ts
        _crawl["started_ts"] = now.timestamp() - 1
        _crawl["finished"] = None
        _crawl["returncode"] = None
    return {"ok": True}


def auto_crawl_loop(interval_min: int, crawl_now: bool = True):
    """Chạy nền: cào 1 lượt (nếu crawl_now) rồi mỗi interval_min phút cào tiếp."""
    import time
    _auto["enabled"] = True
    _auto["interval_min"] = interval_min
    if not crawl_now:
        _auto["next_run"] = (dt.datetime.now() + dt.timedelta(minutes=interval_min)).isoformat(timespec="seconds")
        time.sleep(interval_min * 60)
    while True:
        r = start_crawl()
        print(f"[auto-crawl] {dt.datetime.now():%H:%M:%S} {'bắt đầu' if r.get('ok') else r.get('error')}")
        # chờ tiến trình cào xong rồi mới tính lần kế
        while _crawl["proc"] is not None and _crawl["proc"].poll() is None:
            time.sleep(3)
        _auto["next_run"] = (dt.datetime.now() + dt.timedelta(minutes=interval_min)).isoformat(timespec="seconds")
        time.sleep(interval_min * 60)


# ---- bảo vệ khi mở server ra internet (--host 0.0.0.0) ----
# Máy trong nhà / LAN / Tailscale: dùng như cũ, không cần gì.
# Từ ngoài internet: CHỈ được gọi POST /api/crawl/run, và phải kèm
#   Authorization: Bearer <TRIGGER_TOKEN>   (mặc định = PUSH_TOKEN trong .env)
# POST /api/config (đổi danh sách sân) thì không bao giờ cho từ ngoài.
_TAILSCALE = ipaddress.ip_network("100.64.0.0/10")
PUBLIC_COOLDOWN_SEC = 120          # chặn bấm dồn từ web → né rate limit Alobo
_last_public_trigger = [0.0]


def _env(name: str) -> str:
    v = os.environ.get(name)
    if v:
        return v.strip()
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, val = line.split("=", 1)
                if k.strip() == name:
                    return val.strip().strip('"').strip("'")
    return ""


_trusted_cache: dict = {}


def _trusted_nets():
    """TRUSTED_NETS="127.0.0.0/8,192.168.1.0/24" → chỉ các mạng này được coi là "máy nhà".
    Chưa đặt → giữ hành vi cũ (mọi IP private + Tailscale).
    ⚠ Đứng sau relay/proxy (vd Linode → WireGuard → home): request internet đến với IP
    WireGuard của relay, là IP private → PHẢI đặt TRUSTED_NETS và KHÔNG gồm dải WireGuard,
    nếu không người ngoài sẽ được coi là máy nhà và bỏ qua token."""
    raw = _env("TRUSTED_NETS")
    if not raw:
        return None
    if _trusted_cache.get("raw") == raw:
        return _trusted_cache["nets"]
    nets = []
    for part in raw.split(","):
        part = part.strip()
        if part:
            try:
                nets.append(ipaddress.ip_network(part, strict=False))
            except ValueError:
                print(f"  [TRUSTED_NETS] bỏ qua giá trị sai: {part}")
    _trusted_cache.update(raw=raw, nets=nets)
    return nets


def _is_local(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if getattr(a, "ipv4_mapped", None):
        a = a.ipv4_mapped
    nets = _trusted_nets()
    if nets is not None:
        return any(a.version == n.version and a in n for n in nets)
    return a.is_loopback or a.is_private or a in _TAILSCALE


def _token_ok(header: str) -> bool:
    want = _env("TRIGGER_TOKEN") or _env("PUSH_TOKEN")
    if not want:
        return False
    given = (header or "").removeprefix("Bearer ").strip()
    return hmac.compare_digest(given.encode(), want.encode())


class Handler(BaseHTTPRequestHandler):
    data_dir = "data"

    def _send(self, code, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/data":
            try:
                payload = load_data(os.path.join(HERE, self.data_dir))
                self._send(200, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")
            return
        if path == "/api/directory":
            try:
                self._send(200, json.dumps(read_directory(), ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)}).encode(), "application/json")
            return
        if path == "/api/config":
            self._send(200, json.dumps(read_config(), ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
            return
        if path == "/api/crawl":
            self._send(200, json.dumps(crawl_status(), ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
            return
        # static: / -> viz/index.html ; /x -> viz/x
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        rel = posixpath.normpath(rel)
        if rel.startswith("..") or os.path.isabs(rel):
            self._send(403, b"forbidden", "text/plain")
            return
        full = os.path.join(HERE, "viz", rel)
        if not os.path.isfile(full):
            self._send(404, b"not found", "text/plain")
            return
        ext = os.path.splitext(full)[1]
        ctype = {".html": "text/html; charset=utf-8", ".js": "text/javascript",
                 ".css": "text/css", ".json": "application/json"}.get(ext, "application/octet-stream")
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if not _is_local(self.client_address[0]):
            # gọi từ internet (Vercel): chỉ cho kích cào, có token, có giãn cách
            if path != "/api/crawl/run" or not _token_ok(self.headers.get("Authorization", "")):
                self._send(401, json.dumps({"ok": False, "error": "không có quyền"}).encode(),
                           "application/json; charset=utf-8")
                return
            wait = PUBLIC_COOLDOWN_SEC - (time.time() - _last_public_trigger[0])
            if wait > 0:
                self._send(429, json.dumps({"ok": False, "error": f"vừa cào xong, đợi {int(wait)}s"},
                                           ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
                return
        if path == "/api/crawl/run":
            res = start_crawl()
            if res.get("ok") and not _is_local(self.client_address[0]):
                _last_public_trigger[0] = time.time()
            self._send(200 if res.get("ok") else 409,
                       json.dumps(res, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
            return
        if path != "/api/config":
            self._send(404, b"not found", "text/plain")
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
            if "branches" in body and not isinstance(body["branches"], list):
                raise ValueError("branches phải là list")
            cfg = write_config(body)
            self._send(200, json.dumps({"ok": True, "branches": cfg.get("branches", []),
                                        "days_window": cfg.get("days_window")},
                                       ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
        except Exception as e:
            self._send(400, json.dumps({"ok": False, "error": str(e)}).encode(),
                       "application/json; charset=utf-8")

    def log_message(self, *a):
        pass  # im lang


def main():
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--data", default="data")
    ap.add_argument("--crawl", action="store_true",
                    help="tự cào định kỳ ngay trong server (mỗi interval_min phút)")
    ap.add_argument("--no-crawl-now", action="store_true",
                    help="với --crawl: đợi hết 1 chu kỳ rồi mới cào lần đầu")
    args = ap.parse_args()
    Handler.data_dir = args.data

    # bao cao nhanh luc khoi dong
    payload = load_data(os.path.join(HERE, args.data))
    print(f"Nap {payload['count']} branch tu {args.data}/:")
    for g in payload["branches"]:
        fs = [s for s in g["slots"] if "18:00" <= s < "22:00"]
        occ = {(c["court"], c["date"], c["slot"]) for c in g["occupied"]}
        free = sum(1 for ct in g["courts"] for d in g["days"] for s in fs
                   if not d["is_weekend"] and (ct, d["date"], s) not in occ)
        print(f"  - {g['branch_name']}: {len(g['courts'])} sân, {len(g['days'])} ngày, "
              f"{free} ô trống 18–22h (T2–T6)")

    if args.crawl:
        interval = read_config().get("interval_min", 30)
        t = threading.Thread(target=auto_crawl_loop, args=(interval, not args.no_crawl_now),
                             daemon=True)
        t.start()
        print(f"  [auto-crawl] BẬT — cào mỗi {interval} phút"
              f"{' (lần đầu ngay)' if not args.no_crawl_now else ''}.")
    else:
        print("  [auto-crawl] TẮT — cào tay ở tab Cào dữ liệu, hoặc thêm --crawl, hoặc cron.")

    tn = _trusted_nets()
    print("  [bảo vệ] tin cậy: " + (", ".join(map(str, tn)) if tn is not None
          else "mọi IP private + Tailscale (chưa đặt TRUSTED_NETS)"))
    print("  [bảo vệ] token cho lệnh cào từ ngoài: " + ("CÓ" if (_env("TRIGGER_TOKEN") or _env("PUSH_TOKEN"))
          else "CHƯA ĐẶT → mọi lệnh từ ngoài bị từ chối"))
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"\n  http://{args.host}:{args.port}\n  Ctrl+C để dừng.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\ndừng.")


if __name__ == "__main__":
    main()
