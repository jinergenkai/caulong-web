#!/usr/bin/env python3
"""fetch_raw.py — cách LẤY envelope thô từ ALOBO. DO BẠN VIẾT.

Giao kèo:  (endpoint, params)  ->  envelope thô (dict {data, enc, iv})

Vì sao mình (assistant) KHÔNG viết phần thân: nó đòi tạo chữ ký chống-bot
`x-user-app` rồi gọi API họ (hoặc Playwright tự động gọi) — đúng phần bị hệ thống
chặn (tấn công bên thứ ba). Nên đây là stub của BẠN, giống decrypt.py.

Hai hướng bạn có thể tự làm (tự quyết, tự chịu):

  A) Header thủ công: tự sinh `x-user-app` (thuật toán erW trong bundle) + các
     header chuẩn, rồi httpx/requests GET. Cần tái tạo chữ ký theo thời gian.

  B) Playwright "để app thật ký": mở datlich.alobo.vn bằng trình duyệt thật, cho
     app tự gọi API và tự ký; bắt response qua page.on("response"); hoặc dùng
     window (trong context đã có app) để phát request có chữ ký. Không tái tạo chữ ký.

Trả về ĐÚNG envelope thô (chưa giải mã). Scheduler sẽ đưa nó qua decrypt.decrypt().

Ví dụ chữ ký hàm (bạn tự hoàn thiện thân):

    def fetch_raw(endpoint, params):
        # endpoint: "get_onetime_bookings" | "get_schedule_bookings" | "get_lock_yards" | "get_cores"
        # params:   {"branchId": "...", "startDate": "...", "endDate": "..."}  (tuỳ endpoint)
        ...
        return {"data": "...", "enc": True, "iv": "..."}
"""
from __future__ import annotations

from typing import Any


def fetch_raw(endpoint: str, params: dict) -> Any:
    """BẠN VIẾT: gọi ALOBO, trả envelope thô {data, enc, iv}."""
    raise NotImplementedError(
        "fetch_raw.py chưa được viết. Điền hàm fetch_raw() theo cách bạn chọn (headers/Playwright)."
    )
