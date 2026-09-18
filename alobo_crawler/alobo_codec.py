#!/usr/bin/env python3
"""Giai ma envelope cua ALOBO + vut PII. Dung chung cho moi script trong thu muc nay.

Envelope tra ve tu user-global.alobo.vn:
    {"data": "<base64 ciphertext>", "enc": true, "iv": "<base64 iv>"}
AES-256-CBC + PKCS7, key hardcode trong main.dart.js (ham gOX).
"""
import base64
import json
import os
import re
from typing import Any

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

# key gia chi de round-trip self-test (khong phai key that cua server)
_SELFTEST_KEY = b"selftest_key_32byte______________"[:32]

# === KEY doc tu bien moi truong (KHONG hardcode/commit) ================
# Build 2.10.1 dung key AES-256-CBC-PKCS7 lay runtime (obfuscate XOR trong bundle).
# Da xac dinh gia tri that (2026-09-18) va VERIFY giai duoc response that.
# De o .env, KHONG commit:  ALOBO_KEY=...
# Nap .env bang load_env() ben duoi (khong can thu vien ngoai).
def _load_dotenv(path=".env"):
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()
_KEY_STR = os.environ.get("ALOBO_KEY", "")
KEY = _KEY_STR.encode("utf-8") if _KEY_STR else None  # None -> decrypt bao loi ro


class KeyMissing(RuntimeError):
    pass

# PII tuyet doi - che o moi noi.
ALWAYS_PII = {
    "guest_name", "guest_phone", "guest_email", "guest_note",
    "customer_name", "customerName", "customer_phone", "customerPhone",
    "full_name", "fullName", "user_name", "userName", "user_id", "userId",
    "phone", "phone_number", "phoneNumber", "email", "avatar", "address",
    "created_by", "createdBy", "booking_code", "bookingCode",
}

# PII tuy ngu canh - chi che khi nam trong object CUA MOT NGUOI
# (vd "name" cua san la du lieu nghiep vu, "name" canh "phone" la ten khach).
CONTEXT_PII = {"name", "note", "notes", "description", "title", "label"}

# Dau hieu object do la cua mot nguoi.
_PERSON_HINT = {
    "guest_name", "guest_phone", "phone", "phone_number", "phoneNumber",
    "email", "customer_name", "customerName", "customer_phone", "customerPhone",
    "user_id", "userId", "booking_code", "bookingCode",
}

PII_KEYS = ALWAYS_PII | CONTEXT_PII  # giu ten cu cho tuong thich


def _is_person_obj(d: dict) -> bool:
    return any(k in d for k in _PERSON_HINT)


def _pii_here(key: str, parent: dict) -> bool:
    if key in ALWAYS_PII:
        return True
    return key in CONTEXT_PII and _is_person_obj(parent)


class DecryptError(RuntimeError):
    pass


def is_envelope(obj: Any) -> bool:
    return isinstance(obj, dict) and obj.get("enc") is True and "data" in obj and "iv" in obj


def decrypt(envelope: Any, key: bytes | None = None) -> Any:
    """Envelope -> python object. Neu khong phai envelope thi tra ve nguyen xi.

    key: mac dinh lay tu ALOBO_KEY (.env). Truyen tay de override.
    """
    if not is_envelope(envelope):
        return envelope
    key = key or KEY
    if key is None:
        raise KeyMissing("Chua co key. Dat ALOBO_KEY trong .env (xem .env.example).")
    try:
        iv = base64.b64decode(envelope["iv"])
        ct = base64.b64decode(envelope["data"])
    except Exception as e:
        raise DecryptError(f"base64 hong: {e}") from e
    if len(iv) != 16:
        raise DecryptError(f"IV dai {len(iv)} byte, phai 16")
    if len(ct) % 16:
        raise DecryptError(f"ciphertext {len(ct)} byte, khong chia het 16")
    try:
        raw = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ct), 16)
    except ValueError as e:
        raise DecryptError(
            f"unpad that bai ({e}) -> KEY sai hoac build doi key. "
            f"Kiem tra ALOBO_KEY trong .env; lay lai key: xem README."
        ) from e
    text = raw.decode("utf-8", errors="strict")
    return json.loads(text)


def encrypt(obj: Any, iv: bytes = b"0123456789abcdef", key: bytes | None = None) -> dict:
    """Chi dung cho self-test (round-trip). Mac dinh dung key gia self-test."""
    key = key or _SELFTEST_KEY
    from Crypto.Util.Padding import pad
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    ct = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(body, 16))
    return {"data": base64.b64encode(ct).decode(), "enc": True,
            "iv": base64.b64encode(iv).decode()}


def redact(obj: Any) -> Any:
    """Thay moi gia tri o field PII bang '***'. Ap dung TRUOC khi in / ghi file."""
    if isinstance(obj, dict):
        return {k: ("***" if _pii_here(k, obj) and v not in (None, "", [], {})
                    else redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


def shape(obj: Any, depth: int = 0, max_depth: int = 12) -> Any:
    """Tom tat SCHEMA (key + kieu), khong kem gia tri -> an toan de dan di hoi.

    List -> gop shape cua phan tu dau + do dai. Gia tri scalar -> ten kieu
    (rieng str ngan khong-PII thi giu mau de doan y nghia field).
    """
    if depth >= max_depth:
        return "..."
    if isinstance(obj, dict):
        return {k: (f"<PII {type(v).__name__} len={len(str(v))}>" if _pii_here(k, obj)
                    else shape(v, depth + 1, max_depth))
                for k, v in obj.items()}
    if isinstance(obj, list):
        if not obj:
            return "list[0]"
        return {f"list[{len(obj)}]": shape(obj[0], depth + 1, max_depth)}
    if isinstance(obj, str):
        return f"str e.g. {obj[:32]!r}" if len(obj) <= 32 else f"str(len={len(obj)})"
    if obj is None:
        return "null"
    return type(obj).__name__


KEY_RE = re.compile(r'gOX\(\)\s*\{\s*return\s*"([^"]{16,64})"')


def tim_key_moi(main_dart_js: str) -> list[str]:
    """Tim ung vien key trong main.dart.js (khi build moi doi key).

    Truyen vao NOI DUNG file main.dart.js (tai bang trinh duyet / curl).
    """
    cands = KEY_RE.findall(main_dart_js)
    if cands:
        return cands
    # Fallback: moi chuoi dai dung 32 byte ascii trong bundle
    return sorted({m for m in re.findall(r'"([A-Za-z0-9_\-]{32})"', main_dart_js)})


if __name__ == "__main__":
    import sys
    if "--decrypt" in sys.argv:
        # python alobo_codec.py --decrypt envelope.json  -> in SHAPE da redact PII
        i = sys.argv.index("--decrypt")
        path = sys.argv[i + 1] if len(sys.argv) > i + 1 else "envelope.json"
        env = json.load(open(path, encoding="utf-8"))
        try:
            obj = decrypt(env)
        except KeyMissing as e:
            print("LOI:", e); sys.exit(1)
        except DecryptError as e:
            print("LOI:", e); sys.exit(1)
        print("== SHAPE (da an PII, an toan de dan) ==")
        print(json.dumps(shape(obj), ensure_ascii=False, indent=2))
    elif "--key-status" in sys.argv:
        if KEY:
            print(f"ALOBO_KEY da nap ({len(KEY)} byte).")
        else:
            print("Chua co ALOBO_KEY. Tao .env tu .env.example.")
    else:
        print("Dung: python alobo_codec.py --decrypt envelope.json")
        print("      python alobo_codec.py --key-status")
