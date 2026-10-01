#!/usr/bin/env python3
"""Đẩy dữ liệu sân trống lên web (webhook) sau mỗi lượt cào.

Gửi đúng đầu ra load_data() — thứ heatmap local đang hiển thị — lên
POST {PUSH_URL} kèm Authorization: Bearer {PUSH_TOKEN}.

Cấu hình trong .env (cạnh file này) hoặc biến môi trường:
    PUSH_URL=https://caulong-web.vercel.app/api/courts
    PUSH_TOKEN=<trùng với CRAWLER_TOKEN đặt trên Vercel>

Chạy tay:  python push_web.py
scheduler.py tự gọi sau mỗi lượt cào; thiếu cấu hình thì bỏ qua, lỗi mạng thì
chỉ in cảnh báo — KHÔNG bao giờ làm hỏng lượt cào.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
try:
    sys.stdout.reconfigure(errors="replace")   # in ✓/✗ ra log/pipe trên Windows không được làm sập
except Exception:
    pass


def _env(name: str) -> str:
    v = os.environ.get(name)
    if v:
        return v.strip()
    p = HERE / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, val = line.split("=", 1)
                if k.strip() == name:
                    return val.strip().strip('"').strip("'")
    return ""


def compact(payload: dict) -> dict:
    """Nén occupied: list object {court,date,slot,status} → mỗi sân × ngày một chuỗi,
    1 ký tự / khung giờ ('.' = trống, 'a','b',… = chỉ số trong occ_codes).
    ~15 lần nhẹ hơn. Ô nằm ngoài danh sách slots (hiếm) giữ nguyên ở occ_extra.
    Trang courts.html giải nén ngược lại nên phần vẽ heatmap không đổi gì."""
    out = dict(payload)
    out["branches"] = []
    for g in payload.get("branches", []):
        g = dict(g)
        slots = g.get("slots") or []
        idx = {s: i for i, s in enumerate(slots)}
        codes, rows, extra = [], {}, []
        for c in g.get("occupied", []):
            i = idx.get(c.get("slot"))
            if i is None or set(c) - {"court", "date", "slot", "status"}:
                extra.append(c)
                continue
            st = c.get("status") or "booked"
            if st not in codes:
                codes.append(st)
            row = rows.setdefault(c["court"], {}).setdefault(c["date"], ["."] * len(slots))
            row[i] = chr(ord("a") + codes.index(st))
        g["occ_codes"] = codes
        g["occ"] = {ct: {d: "".join(r) for d, r in ds.items()} for ct, ds in rows.items()}
        g["occ_extra"] = extra
        g.pop("occupied", None)
        out["branches"].append(g)
    out["format"] = "compact1"
    return out


def push() -> bool:
    url, token = _env("PUSH_URL"), _env("PUSH_TOKEN")
    if not url or not token:
        print("   [push] bỏ qua: chưa đặt PUSH_URL / PUSH_TOKEN trong .env")
        return False
    sys.path.insert(0, str(HERE))
    from server import load_data            # cùng hàm heatmap local đang dùng
    payload = compact(load_data(str(HERE / "data")))
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + token,
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"   [push] ✓ {r.status} {r.read().decode('utf-8', 'replace')[:120]}"
                  f" · {len(body) // 1024}KB")
            return True
    except urllib.error.HTTPError as e:
        print(f"   [push] ✗ HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:200]}")
    except Exception as e:
        print(f"   [push] ✗ {e}")
    return False


if __name__ == "__main__":
    sys.exit(0 if push() else 1)
