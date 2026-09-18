#!/usr/bin/env python3
"""Lấy envelope API qua một browser thật, không cần lưu x-user-app."""
from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Any
from urllib.parse import quote, urlencode

import httpx


_BASE_URL = "https://user-global.alobo.vn/v2/user/branch"
_WEB_BASE_URL = "https://datlich.alobo.vn"
_ENDPOINTS = {
    "get_onetime_bookings": "get_onetime_bookings",
    "get_schedule_bookings": "get_schedule_bookings",
    "get_lock_yards": "get_lock_yards/{branchId}",
    "get_cores": "get_cores/{branchId}",
    "get_core_types": "get_core_types/{branchId}",
    "get_branch": "get_branch/{branchId}",
    "products": "products/{branchId}",
}

# Giữ browser sống trong suốt lifetime của scheduler để không phải khởi động
# Chromium ở mỗi request. Không ghi signature ra disk hay log.
_PLAYWRIGHT: Any = None
_BROWSER: Any = None
_CONTEXT: Any = None
_PAGE: Any = None
_SIGNATURE: str | None = None


def fetch_raw(endpoint: str, params: dict) -> Any:
    """Trả envelope thô cho một endpoint, dùng app thật để lấy chữ ký mới.

    App được mở một lần bằng Playwright và request bootstrap của app cung cấp
    ``x-user-app`` mới trong bộ nhớ. Endpoint đích sau đó được gọi bằng
    ``window.fetch`` trong chính page, nên vẫn giữ browser/CORS context. Khi
    server trả 401/403, hàm refresh chữ ký rồi thử lại đúng một lần.
    """
    global _PLAYWRIGHT, _BROWSER, _CONTEXT, _PAGE, _SIGNATURE

    if endpoint not in _ENDPOINTS:
        allowed = ", ".join(sorted(_ENDPOINTS))
        raise ValueError(f"Endpoint không hỗ trợ: {endpoint!r}. Chọn một trong: {allowed}.")
    if not isinstance(params, dict):
        raise TypeError("params phải là dict.")

    path = _ENDPOINTS[endpoint]
    query = dict(params)
    if "{branchId}" in path:
        try:
            path = path.format(branchId=quote(str(query.pop("branchId")), safe=""))
        except KeyError as exc:
            raise ValueError(f"{endpoint} cần params['branchId'].") from exc
    target_url = f"{_BASE_URL}/{path}"
    if query:
        target_url = f"{target_url}?{urlencode(query, doseq=True)}"

    # Fallback co chu y cho debugging/revert nhanh. Khong tu dong bat che do
    # nay khi .env co ALOBO_X_USER_APP, vi signature cu thuong se 403.
    mode_value = os.environ.get("ALOBO_FETCH_MODE")
    if mode_value is None:
        try:
            for line in Path(__file__).with_name(".env").read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, value = line.split("=", 1)
                if name.strip() == "ALOBO_FETCH_MODE":
                    mode_value = value.strip().strip("\"'")
                    break
        except FileNotFoundError:
            pass
    mode = (mode_value or "playwright").lower()
    if mode == "header":
        signature = os.environ.get("ALOBO_X_USER_APP")
        if signature is None:
            env_path = Path(__file__).with_name(".env")
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    name, value = line.split("=", 1)
                    if name.strip() == "ALOBO_X_USER_APP":
                        signature = value.strip().strip("\"'")
                        break
            except FileNotFoundError:
                pass
        if not signature:
            raise ValueError(
                "ALOBO_FETCH_MODE=header cần ALOBO_X_USER_APP trong .env hoặc environment."
            )
        headers = {
            "accept": "*/*",
            "accept-language": "vi-VN,vi;q=0.9,en-US;q=0.6,en;q=0.5",
            "origin": _WEB_BASE_URL,
            "referer": f"{_WEB_BASE_URL}/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/153.0.0.0 Safari/537.36"
            ),
            "x-custom-lang": "vi",
            "x-name-app": "alobo-user",
            "x-platform": "web",
            "x-user-app": signature,
            "x-version-app": "2.10.1",
        }
        try:
            response = httpx.get(target_url, headers=headers, timeout=25.0)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"ALOBO GET {endpoint} thất bại qua header: {exc}") from exc
        if not isinstance(body, dict):
            raise RuntimeError("ALOBO response phải là JSON object/envelope.")
        return body
    if mode != "playwright":
        raise ValueError("ALOBO_FETCH_MODE chỉ nhận 'playwright' (mặc định) hoặc 'header'.")

    if _PAGE is None or _PAGE.is_closed():
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Thiếu Playwright. Chạy: pip install -r requirements.txt && "
                "python -m playwright install chromium"
            ) from exc

        _PLAYWRIGHT = sync_playwright().start()
        launch_args = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        chrome_path = os.environ.get("ALOBO_CHROME_PATH")
        if not chrome_path:
            try:
                for line in Path(__file__).with_name(".env").read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    name, value = line.split("=", 1)
                    if name.strip() == "ALOBO_CHROME_PATH":
                        chrome_path = value.strip().strip("\"'")
                        break
            except FileNotFoundError:
                pass
        if not chrome_path:
            for candidate in (
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                "/usr/bin/google-chrome",
                "/usr/bin/chromium",
            ):
                if Path(candidate).is_file():
                    chrome_path = candidate
                    break
        if chrome_path:
            launch_args["executable_path"] = chrome_path
        try:
            _BROWSER = _PLAYWRIGHT.chromium.launch(**launch_args)
            _CONTEXT = _BROWSER.new_context(
                locale="vi-VN", viewport={"width": 1366, "height": 900}
            )
            _PAGE = _CONTEXT.new_page()
            _PAGE.set_default_timeout(30_000)

            def capture_signature(request: Any) -> None:
                global _SIGNATURE
                if request.url.startswith("https://user-global.alobo.vn/"):
                    value = request.headers.get("x-user-app")
                    if value:
                        _SIGNATURE = value

            _PAGE.on("request", capture_signature)
        except Exception as exc:
            _PAGE = _CONTEXT = _BROWSER = _PLAYWRIGHT = None
            raise RuntimeError(f"Không thể khởi động Chrome cho ALOBO: {exc}") from exc

    def refresh_signature() -> None:
        """Buộc app phát request bootstrap và chờ header ký mới trong RAM."""
        global _SIGNATURE
        _SIGNATURE = None
        branch_id = str(params.get("branchId", ""))
        bootstrap_url = f"{_WEB_BASE_URL}/san/{quote(branch_id, safe='')}" if branch_id else _WEB_BASE_URL
        _PAGE.goto(bootstrap_url, wait_until="domcontentloaded", timeout=60_000)
        deadline = time.monotonic() + 12
        while _SIGNATURE is None and time.monotonic() < deadline:
            _PAGE.wait_for_timeout(200)
        if not _SIGNATURE:
            raise RuntimeError("App ALOBO không phát x-user-app trong 12 giây.")

    try:
        if not _SIGNATURE:
            refresh_signature()

        result: dict[str, Any] | None = None
        for attempt in range(2):
            result = _PAGE.evaluate(
                """async ({url, signature}) => {
                    const response = await fetch(url, {
                      headers: {
                        'accept': '*/*',
                        'x-custom-lang': 'vi',
                        'x-name-app': 'alobo-user',
                        'x-platform': 'web',
                        'x-user-app': signature,
                        'x-version-app': '2.10.1',
                      },
                    });
                    let body = null;
                    try { body = await response.json(); } catch (_) {}
                    return {status: response.status, body};
                }""",
                {"url": target_url, "signature": _SIGNATURE},
            )
            if result.get("status") not in (401, 403) or attempt:
                break
            refresh_signature()
    except Exception as exc:
        raise RuntimeError(f"ALOBO GET {endpoint} thất bại qua Playwright: {exc}") from exc

    if not result or result.get("status") < 200 or result.get("status") >= 300:
        status = result.get("status") if result else "không rõ"
        raise RuntimeError(f"ALOBO GET {endpoint} thất bại: HTTP {status}.")
    body = result.get("body")
    if not isinstance(body, dict):
        raise RuntimeError("ALOBO response phải là JSON object/envelope.")
    return body
