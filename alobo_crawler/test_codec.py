#!/usr/bin/env python3
"""TEST 1 - offline, khong can mang, khong can token.

Kiem tra: decrypt/encrypt round-trip, redact PII, shape(), va giai ma
envelope that neu ban da luu duoc mot cai (--file envelope.json).

    python test_codec.py
    python test_codec.py --file captures/....raw.json
"""
import argparse
import json
import sys

import alobo_codec as C

OK, FAIL = "  [OK]", "  [FAIL]"
_fails = 0


def check(name, cond, detail=""):
    global _fails
    print(f"{OK if cond else FAIL} {name}{(' - ' + detail) if detail and not cond else ''}")
    if not cond:
        _fails += 1


def main():
    C.KEY = C._SELFTEST_KEY  # test doc lap voi .env
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", help="file JSON chua envelope that de thu giai ma")
    args = ap.parse_args()

    print("== key ==")
    check("KEY dai 32 byte (AES-256)", len(C.KEY) == 32, f"dang la {len(C.KEY)}")

    print("\n== round-trip AES-256-CBC + PKCS7 ==")
    payload = {
        "status": True,
        "data": {
            "courts": [
                {"id": "c1", "name": "San 1",
                 "bookings": [{"start": "18:00", "end": "19:00", "status": "booked",
                               "guest_name": "Nguyen Van A", "guest_phone": "0900000000"}]}
            ]
        },
    }
    env = C.encrypt(payload)
    check("encrypt() ra dung hinh envelope", C.is_envelope(env), json.dumps(env)[:80])
    back = C.decrypt(env)
    check("decrypt(encrypt(x)) == x", back == payload)

    print("\n== envelope hong thi bao loi tu te ==")
    try:
        C.decrypt(C.encrypt(payload, key=b"x" * 32))
        check("key sai -> DecryptError", False, "khong nem loi")
    except C.DecryptError as e:
        check("key sai -> DecryptError", True)
        check("thong bao loi goi y ALOBO_KEY", "ALOBO_KEY" in str(e))
    except Exception as e:
        check("key sai -> DecryptError", False, f"nem {type(e).__name__}: {e}")

    check("khong phai envelope -> tra ve nguyen xi",
          C.decrypt({"status": True}) == {"status": True})

    print("\n== redact PII ==")
    red = C.redact(back)
    bk = red["data"]["courts"][0]["bookings"][0]
    check("guest_name bi che", bk["guest_name"] == "***", repr(bk["guest_name"]))
    check("guest_phone bi che", bk["guest_phone"] == "***", repr(bk["guest_phone"]))
    check("field nghiep vu con nguyen", bk["start"] == "18:00" and bk["status"] == "booked")
    blob = json.dumps(red, ensure_ascii=False)
    check("khong con PII trong chuoi da redact",
          "Nguyen Van A" not in blob and "0900000000" not in blob)

    print("\n== redact theo ngu canh ==")
    mixed = {"courts": [{"id": "c1", "name": "San 1", "status": "active"}],
             "booker": {"name": "Tran Van B", "phone": "0911222333"}}
    r = C.redact(mixed)
    check("ten SAN giu nguyen (khong phai PII)", r["courts"][0]["name"] == "San 1",
          repr(r["courts"][0]["name"]))
    check("ten NGUOI (nam canh phone) bi che", r["booker"]["name"] == "***")
    check("phone bi che", r["booker"]["phone"] == "***")

    print("\n== shape() ==")
    sh = C.shape(back)
    shblob = json.dumps(sh, ensure_ascii=False)
    check("shape khong lam ro PII", "Nguyen Van A" not in shblob and "0900000000" not in shblob)
    check("shape giu duoc cau truc list", "list[1]" in shblob, shblob[:200])
    print(json.dumps(sh, ensure_ascii=False, indent=2))

    if args.file:
        print(f"\n== giai ma envelope that: {args.file} ==")
        try:
            raw = json.load(open(args.file, encoding="utf-8"))
        except Exception as e:
            check("doc file", False, str(e))
        else:
            env = raw.get("body", raw) if isinstance(raw, dict) else raw
            check("file la envelope (enc=true)", C.is_envelope(env),
                  f"top-level keys: {list(env)[:6] if isinstance(env, dict) else type(env)}")
            if C.is_envelope(env):
                try:
                    obj = C.decrypt(env)
                    check("giai ma OK", True)
                    print("\n--- SHAPE (da an PII) ---")
                    print(json.dumps(C.shape(obj), ensure_ascii=False, indent=2)[:4000])
                except C.DecryptError as e:
                    check("giai ma OK", False, str(e))

    print(f"\n{'TAT CA PASS' if not _fails else str(_fails) + ' TEST FAIL'}")
    return 1 if _fails else 0


if __name__ == "__main__":
    sys.exit(main())
