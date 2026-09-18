#!/usr/bin/env python3
"""Giải mã envelope AES-CBC do API trả về."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


def decrypt(envelope: Any) -> Any:
    """Trả JSON đã giải mã từ envelope ``{data, enc, iv}``.

    Response không mã hoá được trả nguyên vẹn. ``ALOBO_KEY`` được lấy từ
    ``.env`` cạnh file này; biến môi trường cùng tên được ưu tiên để tiện
    chạy trên VPS mà không cần chép file secret.
    """
    if not isinstance(envelope, dict) or not envelope.get("enc"):
        return envelope

    key_text = os.environ.get("ALOBO_KEY")
    if key_text is None:
        env_path = Path(__file__).with_name(".env")
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, value = line.split("=", 1)
                if name.strip() == "ALOBO_KEY":
                    key_text = value.strip().strip("\"'")
                    break
        except FileNotFoundError:
            pass

    if not key_text:
        raise ValueError("Thiếu ALOBO_KEY trong alobo_crawler/.env.")

    key = key_text.encode("utf-8")
    if len(key) not in (16, 24, 32):
        raise ValueError("ALOBO_KEY phải dài 16, 24 hoặc 32 byte cho AES.")

    try:
        iv = base64.b64decode(envelope["iv"], validate=True)
        ciphertext = base64.b64decode(envelope["data"], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Envelope mã hoá phải có data và iv ở dạng base64.") from exc

    if len(iv) != AES.block_size:
        raise ValueError("IV trong envelope phải dài 16 byte.")

    try:
        plaintext = unpad(
            AES.new(key, AES.MODE_CBC, iv).decrypt(ciphertext), AES.block_size
        )
        return json.loads(plaintext.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "Không thể giải mã envelope; kiểm tra ALOBO_KEY và dữ liệu response."
        ) from exc
