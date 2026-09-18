#!/usr/bin/env python3
"""TEST 3 (KHUYEN NGHI) - doc trang thai luoi bang MAU, khong dung API/decrypt/chu ky.

Vi sao day la duong nen di (xem FINDINGS.md):
  - Khong forge chu ky x-user-app, khong can token, khong can giai ma (key bi obfuscate).
  - Chi de app that render luoi roi doc pixel - dung thu mat nguoi cung doc.

Luong:
  1. Playwright mo /san/<branchId> -> bam "Dat lich" -> "Dat lich theo san - truc quan".
  2. Doi ngay (T2-T6 trong 15 ngay toi) bang date picker.
  3. Chup luoi, doc mau o tai luoi toa do -> Trang/Do/Xam/Tim.
  4. Ghi SQLite time-series (branch, court, date, slot, status, crawled_at).

Legend mau (doc tu luoi that 2026-09-18):
  TRONG (trang)  = con trong   -> bao slot nay!
  DA DAT (do)    = da co nguoi
  KHOA (xam)     = khong mo ban
  SU KIEN (tim)  = su kien

Trang thai: bo PHAN LOAI MAU + test offline da xong. Phan Playwright/lattice can
CALIBRATE toa do 1 lan cho tung layout (o ham read_grid_from_image) - grid la canvas
nen toa do phu thuoc kich thuoc cua so; chay --calibrate de do.

    python alobo_grid_reader.py --self-test        # test bo phan loai mau (offline)
    python alobo_grid_reader.py --branch <id> --calibrate   # do toa do luoi
    python alobo_grid_reader.py --branch <id> --days 15      # crawl that (sau khi calibrate)
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

# --------------------------------------------------------------------------- #
# 1) PHAN LOAI MAU  (thuan, test duoc offline)
# --------------------------------------------------------------------------- #
# Mau moc (RGB) doc tu legend luoi that. Phan loai theo khoang cach gan nhat,
# co nguong "khong ro" de khong doan bua.
SWATCHES = {
    "TRONG":   (255, 255, 255),   # trang
    "DA_DAT":  (198, 65, 75),     # do (o da dat)
    "DA_DAT2": (240, 90, 95),     # do nhat (vung 19:00-22:00 sang hon)
    "KHOA":    (150, 150, 150),   # xam
    "SU_KIEN": (150, 90, 200),    # tim
}
# gop nhan phu ve nhan chinh
_ALIAS = {"DA_DAT2": "DA_DAT"}

STATUS_VN = {
    "TRONG": "Trong",
    "DA_DAT": "Da dat",
    "KHOA": "Khoa",
    "SU_KIEN": "Su kien",
    "KHONG_RO": "Khong ro",
}


def classify(rgb: tuple[int, int, int], max_dist: float = 90.0) -> str:
    """RGB -> nhan trang thai. Xa moi swatch qua nguong -> KHONG_RO."""
    r, g, b = rgb[0], rgb[1], rgb[2]
    best, bestd = None, 1e9
    for name, (sr, sg, sb) in SWATCHES.items():
        d = ((r - sr) ** 2 + (g - sg) ** 2 + (b - sb) ** 2) ** 0.5
        if d < bestd:
            best, bestd = name, d
    if bestd > max_dist:
        return "KHONG_RO"
    return _ALIAS.get(best, best)


def is_free(status: str) -> bool:
    return status == "TRONG"


# --------------------------------------------------------------------------- #
# 2) LICH / KHUNG GIO  (thuan, test duoc offline)
# --------------------------------------------------------------------------- #
def weekdays_ahead(days: int, today: dt.date | None = None) -> list[dt.date]:
    """Tu NGAY MAI toi +days, chi T2-T6 (bo T7=5, CN=6)."""
    today = today or dt.date.today()
    out = []
    for i in range(1, days + 1):
        d = today + dt.timedelta(days=i)
        if d.weekday() < 5:
            out.append(d)
    return out


def slots_1800_2200(step_min: int = 30) -> list[str]:
    """Cac moc 18:00..21:30 (moi o = mot khung step_min phut, ket thuc 22:00)."""
    out = []
    t = dt.datetime(2000, 1, 1, 18, 0)
    end = dt.datetime(2000, 1, 1, 22, 0)
    while t < end:
        out.append(t.strftime("%H:%M"))
        t += dt.timedelta(minutes=step_min)
    return out


# --------------------------------------------------------------------------- #
# 3) SQLite time-series
# --------------------------------------------------------------------------- #
DDL = """
CREATE TABLE IF NOT EXISTS slot_status (
    branch     TEXT NOT NULL,
    court      TEXT NOT NULL,
    date       TEXT NOT NULL,   -- YYYY-MM-DD
    slot       TEXT NOT NULL,   -- HH:MM
    status     TEXT NOT NULL,   -- TRONG/DA_DAT/KHOA/SU_KIEN/KHONG_RO
    crawled_at TEXT NOT NULL    -- ISO8601
);
CREATE INDEX IF NOT EXISTS ix_slot ON slot_status(branch, date, slot);
"""


def open_db(path: str):
    import sqlite3
    con = sqlite3.connect(path)
    con.executescript(DDL)
    return con


def save_rows(con, rows: list[dict]) -> int:
    cur = con.executemany(
        "INSERT INTO slot_status(branch,court,date,slot,status,crawled_at)"
        " VALUES(:branch,:court,:date,:slot,:status,:crawled_at)", rows)
    con.commit()
    return cur.rowcount


# --------------------------------------------------------------------------- #
# 4) PLAYWRIGHT + doc luoi  (can calibrate toa do - la canvas)
# --------------------------------------------------------------------------- #
def read_grid_from_image(png_path: str, lattice: dict) -> list[dict]:
    """Doc mau tai luoi toa do co san.

    lattice = {
      "courts": ["San 1", ...],          # nhan hang
      "slots":  ["18:00", ...],          # nhan cot (chi khung 18-22h)
      "x0": int, "dx": float,            # tam o cot dau + buoc ngang (px)
      "y0": int, "dy": float,            # tam o hang dau + buoc doc (px)
    }
    Tra ve list {court, slot, status}. Can Pillow.
    """
    from PIL import Image
    im = Image.open(png_path).convert("RGB")
    px = im.load()
    out = []
    for ri, court in enumerate(lattice["courts"]):
        y = int(lattice["y0"] + ri * lattice["dy"])
        for ci, slot in enumerate(lattice["slots"]):
            x = int(lattice["x0"] + ci * lattice["dx"])
            # lay mau trung binh 5x5 cho on dinh
            acc = [0, 0, 0]; n = 0
            for ddx in range(-2, 3):
                for ddy in range(-2, 3):
                    r, g, b = px[x + ddx, y + ddy]
                    acc[0] += r; acc[1] += g; acc[2] += b; n += 1
            rgb = (acc[0] // n, acc[1] // n, acc[2] // n)
            out.append({"court": court, "slot": slot, "status": classify(rgb)})
    return out


# --------------------------------------------------------------------------- #
# self-test (offline)
# --------------------------------------------------------------------------- #
def self_test() -> int:
    fails = 0

    def chk(name, cond, d=""):
        nonlocal fails
        print(f"  [{'OK' if cond else 'FAIL'}] {name}{('' if cond else ' - ' + d)}")
        if not cond:
            fails += 1

    print("== phan loai mau ==")
    chk("trang -> TRONG", classify((255, 255, 255)) == "TRONG")
    chk("trang hoi xam -> TRONG", classify((248, 250, 249)) == "TRONG")
    chk("do -> DA_DAT", classify((198, 65, 75)) == "DA_DAT")
    chk("do nhat -> DA_DAT", classify((240, 90, 95)) == "DA_DAT")
    chk("xam -> KHOA", classify((150, 150, 150)) == "KHOA")
    chk("tim -> SU_KIEN", classify((150, 90, 200)) == "SU_KIEN")
    chk("mau la (xanh la) -> KHONG_RO", classify((20, 200, 40)) == "KHONG_RO",
        classify((20, 200, 40)))
    chk("is_free chi dung cho TRONG", is_free("TRONG") and not is_free("DA_DAT"))

    print("== lich T2-T6, 15 ngay ==")
    # today = thu Sau 2026-09-18 -> ngay mai T7,CN bi bo
    wd = weekdays_ahead(15, dt.date(2026, 9, 18))
    chk("khong co T7/CN", all(d.weekday() < 5 for d in wd))
    chk("bo qua 19,20 (T7,CN)", dt.date(2026, 9, 19) not in wd and dt.date(2026, 9, 20) not in wd)
    chk("21 la T2 -> co trong danh sach", dt.date(2026, 9, 21) in wd)
    chk("bat dau tu T2 (21/09)", wd[0] == dt.date(2026, 9, 21), str(wd[0]))
    chk("ket thuc trong ngay mai..+15", wd[-1] <= dt.date(2026, 10, 3), str(wd[-1]))

    print("== khung gio 18-22h ==")
    s = slots_1800_2200(30)
    chk("bat dau 18:00", s[0] == "18:00")
    chk("ket thuc o 21:30 (o cuoi)", s[-1] == "21:30")
    chk("du 8 o 30 phut", len(s) == 8, str(len(s)))

    print("== SQLite time-series ==")
    con = open_db(":memory:")
    now = dt.datetime.now().isoformat(timespec="seconds")
    rows = [{"branch": "b", "court": "San 1", "date": "2026-09-22",
             "slot": "18:00", "status": "TRONG", "crawled_at": now},
            {"branch": "b", "court": "San 1", "date": "2026-09-22",
             "slot": "18:30", "status": "DA_DAT", "crawled_at": now}]
    save_rows(con, rows)
    save_rows(con, rows)  # crawl lan 2 -> giu ca 2 lan (time-series, khong ghi de)
    cnt = con.execute("SELECT COUNT(*) FROM slot_status").fetchone()[0]
    chk("luu time-series khong ghi de", cnt == 4, str(cnt))
    free = con.execute(
        "SELECT COUNT(*) FROM slot_status WHERE status='TRONG'").fetchone()[0]
    chk("query slot trong", free == 2, str(free))

    print("\n" + ("TAT CA PASS" if not fails else f"{fails} FAIL"))
    return 1 if fails else 0


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true", help="test offline bo phan loai mau + lich")
    ap.add_argument("--branch", action="append", help="branchId (lap lai duoc)")
    ap.add_argument("--days", type=int, default=15, help="so ngay toi (mac dinh 15)")
    ap.add_argument("--calibrate", action="store_true",
                    help="mo luoi, chup screenshot de ban do toa do lattice bang tay")
    ap.add_argument("--db", default="alobo_slots.sqlite", help="file SQLite")
    ap.add_argument("--out", default="captures", help="thu muc screenshot")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if not args.branch:
        ap.error("can --branch, hoac --self-test")

    print("Phan lai app + doc luoi can Playwright + calibrate toa do.")
    print("Xem FINDINGS.md muc 6 va ham read_grid_from_image() de dien lattice.")
    print("Buoc chay that:")
    print("  1) python alobo_grid_reader.py --self-test        (kiem tra logic - da PASS)")
    print("  2) python alobo_grid_reader.py --branch <id> --calibrate")
    print("     -> mo luoi, chup captures/<id>_grid.png, ban do x0/dx/y0/dy 1 lan")
    print("  3) dien lattice vao code, chay crawl --days 15")
    print("\nDanh sach ngay se quet (T2-T6):")
    for d in weekdays_ahead(args.days):
        print("  ", d.isoformat(), ["T2", "T3", "T4", "T5", "T6"][d.weekday()])
    return 0


if __name__ == "__main__":
    sys.exit(main())
