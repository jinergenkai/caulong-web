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
import glob
import json
import os
import posixpath
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import adapt

HERE = os.path.dirname(os.path.abspath(__file__))


def branch_meta(doc, fallback_name):
    """Lay branch/branch_name neu doc la dict chuan hoa; else mac dinh."""
    if isinstance(doc, dict):
        return doc.get("branch", fallback_name), doc.get("branch_name", fallback_name)
    return fallback_name, fallback_name


def load_data(data_dir: str) -> dict:
    """Doc + adapt moi file -> gom theo branch -> list grid."""
    files = sorted(glob.glob(os.path.join(data_dir, "*.json")))
    branches: dict[str, dict] = {}
    for path in files:
        name = os.path.basename(path)
        if name.startswith("_") or name.startswith("."):
            continue
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except Exception as e:
            print(f"  [bo qua] {name}: {e}")
            continue
        occ = adapt.adapt_doc(doc)
        if not occ:
            continue
        if isinstance(doc, dict):
            # file da chuan hoa (vd sample): mang branch/ten rieng
            key = doc.get("branch", name.replace(".json", ""))
            pretty = doc.get("branch_name", key)
            days_hint = [d["date"] for d in doc["days"]] if doc.get("days") else None
        else:
            # file raw get_onetime_bookings: suy branch tu TEN FILE.
            #   <branchId>__<gi-cung-duoc>.json  -> gom theo <branchId>
            #   get_onetime_bookings.json / khac  -> branch mac dinh
            stem = name.replace(".json", "")
            if "__" in stem:
                key = stem.split("__")[0]
                pretty = key
            else:
                key = "sport_bui_thi_xuan_badminton"
                pretty = "Sân Cầu Lông Bùi Thị Xuân"
            days_hint = None  # ngay suy tu chinh du lieu (union)
        slot = branches.setdefault(key, {"branch": key, "branch_name": pretty,
                                         "occupied": [], "days_hint": days_hint})
        slot["occupied"].extend(occ)
        if days_hint:
            slot["days_hint"] = days_hint

    out = []
    for key, s in branches.items():
        # khu trung lap
        uniq = {(c["court"], c["date"], c["slot"]): c for c in s["occupied"]}
        occ = list(uniq.values())
        grid = adapt.build_grid(occ, branch=key, branch_name=s["branch_name"],
                                days=s["days_hint"])
        out.append(grid)
    out.sort(key=lambda g: g["branch_name"])
    return {"branches": out, "count": len(out)}


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

    def log_message(self, *a):
        pass  # im lang


def main():
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--data", default="data")
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

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"\n  http://{args.host}:{args.port}\n  Ctrl+C để dừng.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\ndừng.")


if __name__ == "__main__":
    main()
