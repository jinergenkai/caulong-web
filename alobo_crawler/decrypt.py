#!/usr/bin/env python3
"""decrypt.py — MỘT hàm duy nhất, DO BẠN VIẾT.

Giao kèo:  envelope (dict {data, enc, iv})  ->  json đã giải mã (dict | list)

Scheduler và adapter chỉ gọi đúng hàm này. Mình (assistant) KHÔNG viết phần thân —
bạn tự điền bằng key bạn đã tự khôi phục (đọc từ .env: ALOBO_KEY).

Gợi ý khung (bạn tự hoàn thiện):

    import os, json, base64
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad

    def decrypt(envelope):
        if not (isinstance(envelope, dict) and envelope.get("enc")):
            return envelope
        key = os.environ["ALOBO_KEY"].encode()
        iv  = base64.b64decode(envelope["iv"])
        ct  = base64.b64decode(envelope["data"])
        raw = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ct), 16)
        return json.loads(raw.decode("utf-8"))
"""
from __future__ import annotations

from typing import Any


def decrypt(envelope: Any) -> Any:
    """BẠN VIẾT: envelope -> json đã giải mã. Trả về dict/list."""
    raise NotImplementedError(
        "decrypt.py chưa được viết. Điền hàm decrypt() bằng key của bạn (ALOBO_KEY)."
    )
