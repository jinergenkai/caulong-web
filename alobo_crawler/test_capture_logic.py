#!/usr/bin/env python3
"""TEST 3 - offline, khong can mang, khong can playwright, khong can token.

Kiem tra phan logic thuan cua alobo_capture.py: doc query string, doi endDate,
che header bi mat, doc han token, va pipeline analyse() (envelope -> shape).

    python test_capture_logic.py
"""
import base64
import importlib
import json
import sys
import time

import alobo_codec as C

# alobo_capture import playwright kieu lazy (trong run()) nen import module
# o day khong can playwright.
cap = importlib.import_module("alobo_capture")

OK, FAIL = "  [OK]", "  [FAIL]"
_fails = 0


def check(name, cond, detail=""):
    global _fails
    print(f"{OK if cond else FAIL} {name}{(' - ' + detail) if detail and not cond else ''}")
    if not cond:
        _fails += 1


URL = ("https://user-global.alobo.vn/v2/user/branch/get_onetime_bookings"
       "?branchId=sport_sky_phu_nhuan&startDate=2026-09-19&endDate=2026-09-19")


def main():
    C.KEY = C._SELFTEST_KEY  # test doc lap voi .env
    print("== doc query string ==")
    q = cap.qs_of(URL)
    check("lay du 3 tham so", q == {"branchId": "sport_sky_phu_nhuan",
                                   "startDate": "2026-09-19",
                                   "endDate": "2026-09-19"}, json.dumps(q))

    print("\n== doi endDate (probe range) ==")
    new = cap.with_end_date(URL, "2026-10-04")
    nq = cap.qs_of(new)
    check("endDate da doi", nq["endDate"] == "2026-10-04", nq.get("endDate"))
    check("startDate giu nguyen", nq["startDate"] == "2026-09-19")
    check("branchId giu nguyen", nq["branchId"] == "sport_sky_phu_nhuan")
    check("van dung host/path", new.startswith(
        "https://user-global.alobo.vn/v2/user/branch/get_onetime_bookings?"))
    added = cap.qs_of(cap.with_end_date(
        "https://x.vn/a?branchId=b&startDate=2026-09-19", "2026-09-30"))
    check("them endDate khi URL chua co", added.get("endDate") == "2026-09-30")

    print("\n== che header bi mat ==")
    h = cap.safe_headers({
        "Authorization": "Bearer eyJhbGciOi.xxx.yyy",
        "x-user-app": "8ddfb5c3" * 8,
        "cookie": "cf_clearance=abc",
        "x-version-app": "2.10.1",
        "x-platform": "web",
    })
    blob = json.dumps(h)
    check("authorization bi che", "eyJhbGciOi" not in blob, blob)
    check("x-user-app bi che", "8ddfb5c3" not in blob, blob)
    check("cookie bi che", "cf_clearance=abc" not in blob, blob)
    check("x-version-app con doc duoc", h["x-version-app"] == "2.10.1")
    check("van biet la CO header do", "<co, len=" in h["Authorization"])

    print("\n== doc han token (chi iat/exp) ==")
    exp = int(time.time()) + 2 * 3600
    body = base64.urlsafe_b64encode(
        json.dumps({"sub": "user-123", "phone": "0900000000",
                    "iat": int(time.time()), "exp": exp}).encode()).decode().rstrip("=")
    info = cap.jwt_info(f"Bearer aaa.{body}.bbb")
    check("doc duoc exp", "exp" in info, json.dumps(info))
    check("tinh duoc so phut con lai", 110 < info.get("con_lai_phut", 0) < 125,
          str(info.get("con_lai_phut")))
    iblob = json.dumps(info)
    check("khong lam lo sub/phone trong token",
          "user-123" not in iblob and "0900000000" not in iblob, iblob)
    check("header rac -> dict rong", cap.jwt_info("Bearer rac") == {})
    check("khong co header -> dict rong", cap.jwt_info(None) == {})

    print("\n== analyse(): envelope -> shape, khong ro ri ==")
    payload = {"status": True, "data": {"bookings": [
        {"court_id": "c1", "court_name": "San 3", "date": "2026-09-19",
         "start_time": "18:00", "end_time": "19:00", "status": "PAID",
         "guest_name": "Le Thi C", "guest_phone": "0987654321"}]}}
    rec = {
        "url": URL,
        "params": cap.qs_of(URL),
        "status": 200,
        "headers": cap.safe_headers({"Authorization": "Bearer aaa.bbb.ccc",
                                     "x-version-app": "2.10.1"}),
        "body_text": json.dumps(C.encrypt(payload)),
    }
    res = cap.analyse(rec, verbose=True)
    check("khong bao loi", "error" not in res, res.get("error", ""))
    check("nhan dien enc=true", res.get("enc") is True)
    check("co shape", "shape" in res)
    rblob = json.dumps(res, ensure_ascii=False)
    check("KHONG ro ri PII ra ket qua",
          "Le Thi C" not in rblob and "0987654321" not in rblob, rblob[:300])
    check("KHONG ro ri token ra ket qua", "aaa.bbb.ccc" not in rblob)
    check("giu duoc ten san / gio (du lieu nghiep vu)",
          "San 3" in rblob and "18:00" in rblob)
    print(json.dumps(res["shape"], ensure_ascii=False, indent=2))

    print("\n== analyse(): body khong phai JSON ==")
    bad = dict(rec, body_text="<html>403 forbidden</html>")
    r2 = cap.analyse(bad, verbose=False)
    check("bao loi ro rang", "error" in r2 and "khong phai JSON" in r2["error"],
          json.dumps(r2)[:200])

    print("\n== analyse(): envelope ma hoa bang key khac ==")
    wrong = dict(rec, body_text=json.dumps(C.encrypt(payload, key=b"z" * 32)))
    r3 = cap.analyse(wrong, verbose=False)
    check("bao decrypt that bai + goi y doi key",
          "error" in r3 and "ALOBO_KEY" in r3["error"], json.dumps(r3)[:200])

    print(f"\n{'TAT CA PASS' if not _fails else str(_fails) + ' TEST FAIL'}")
    return 1 if _fails else 0


if __name__ == "__main__":
    sys.exit(main())
