# alobo_crawler — bộ script test (đã kiểm chứng thật)

Mục tiêu cuối: theo dõi slot trống 18:00–22:00, T2–T6, từ ngày mai → +15 ngày, nhiều sân,
báo khi bất kỳ sân nào có ô trống. Lưu SQLite time-series. VPS 1GB RAM.

> **Đọc [FINDINGS.md](FINDINGS.md) trước.** Tôi đã tự mở browser + Chrome DevTools kiểm chứng
> từng tầng. Nhiều điểm trong handoff **sai với build hiện tại (2.10.1)** — tóm tắt bên dưới.

## Kết luận 3 tầng (dễ → khó)

| Tầng | Cách | Kết luận |
|---|---|---|
| Dễ — kéo API không trình duyệt | httpx + header | ❌ **Không được**. Vướng chữ ký `x-user-app` theo thời gian + decrypt (key XOR-obfuscate). |
| Vừa — Playwright để app ký, bắt response | `page.on("response")` | ⚠️ Bắt được envelope, **nhưng chưa decrypt được** (key build 2.10.1 chưa giải). |
| **Khó — Playwright lái app + đọc màu lưới** | screenshot + dò màu | ✅ **Khả thi & bền nhất**. Không forge chữ ký, không token, không decrypt. **Khuyến nghị.** |

Phát hiện chính (chi tiết + bằng chứng trong FINDINGS.md):
- Xem lịch sân **không cần Bearer token** (ẩn danh OK) — handoff nói cần JWT 2h là **sai**.
- Request thiếu header → **401** (không phải 403 như handoff).
- **Rate limit 30 req/phút** (`x-ratelimit-limit: 30`) — ràng buộc thiết kế crawler.
- **Key giải mã trong handoff `0123...9876542026` KHÔNG giải được** response build 2.10.1
  (kiểm chứng trên 2 response thật, cả Python lẫn WebCrypto). Key thật dựng runtime bằng XOR.
- Flutter **không đi qua `window.fetch`/XHR** bắt được → phải dùng `page.on("response")` (CDP),
  KHÔNG phải hook fetch trong trang (handoff đề xuất cái này — vô dụng).
- Lưới là **canvas thuần** (semantics không lộ ô) → đọc có cấu trúc chỉ còn: API (bị chặn)
  hoặc **đọc màu** (Trắng=trống, Đỏ=đã đặt, Xám=khoá, Tím=sự kiện).

## Cài đặt

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## Các script

| Script | Cần gì | Vai trò |
|---|---|---|
| `test_codec.py` | offline | Test giải mã AES + vứt PII (self-test cipher) |
| `test_capture_logic.py` | offline | Test logic đọc query / đổi endDate / che token |
| `alobo_grid_reader.py` | offline test + (Playwright để crawl) | **Tầng khuyến nghị**: đọc màu lưới → SQLite time-series |
| `alobo_capture.py` | Chromium + mạng | Bắt envelope API qua `page.on("response")` (decrypt hiện bế tắc) |
| `test.py` | — | Probe httpx cũ, giữ tham chiếu (403 vì tầng chữ ký) |

### Chạy offline (5 giây, đang PASS hết)

```bash
python test_codec.py && python test_capture_logic.py && python alobo_grid_reader.py --self-test
```

### Tầng khuyến nghị — đọc màu lưới

```bash
python alobo_grid_reader.py --branch sport_bui_thi_xuan_badminton --calibrate
```

`--calibrate` mở lưới, chụp screenshot để bạn đo toạ độ lattice (grid là canvas nên toạ độ
phụ thuộc kích thước cửa sổ — đo 1 lần rồi điền vào `read_grid_from_image`). Sau đó crawl
15 ngày × N sân, lọc T2–T6 + 18:00–22:00, ghi SQLite time-series (không ghi đè).

### Bắt envelope API (nếu sau này có key runtime)

```bash
python alobo_capture.py --branch sport_bui_thi_xuan_badminton --manual --wait 90
```

Dùng `page.on("response")` (đúng cơ chế). In được params + header (đã che secret) + envelope;
phần SHAPE sẽ báo lỗi decrypt cho tới khi có key đúng.

## Ranh giới cố ý

- **Không** forge `x-user-app` (chữ ký chống-bot theo thời gian).
- **Không** tái tạo key runtime bị XOR-obfuscate (lớp chống-bot cố ý).
- Mọi request đều do **app thật** phát ra và ký.

## PII

Response chứa `guest_name`/`guest_phone`. `alobo_codec.redact()` che trước khi in/ghi;
`shape()` chỉ in key+kiểu; redact phân biệt ngữ cảnh (tên sân giữ, tên người che). `captures/`
và `*.sqlite` nằm trong `.gitignore`.

## Pipeline hoàn chỉnh (hướng API + decrypt)

```
  fetch_raw.py   →   decrypt.py   →   adapt.py   →   data/*.json   →   server.py
  (BẠN viết)         (BẠN viết)       (có sẵn)       (đã redact PII)   (heatmap)
       ▲                 ▲
       └─────────────────┴──  scheduler.py điều phối + giãn nhịp (30 req/phút)
```

| File | Ai viết | Vai trò |
|---|---|---|
| `fetch_raw.py` | **Bạn** | Gọi ALOBO → envelope thô (headers hoặc Playwright). Stub sẵn. |
| `decrypt.py` | **Bạn** | envelope → json (1 hàm, key từ `.env`). Stub sẵn. |
| `adapt.py` | có sẵn | Chuẩn hoá shape thật → lưới trạng thái |
| `scheduler.py` | có sẵn | Lặp mỗi 30' × N sân × 15 ngày T2–T6, gọi 2 stub, redact, lưu `data/` |
| `server.py` + `viz/` | có sẵn | Heatmap (xem [VISUALIZER.md](VISUALIZER.md)) |
| `config.json` | bạn chỉnh | Danh sách sân, days_ahead, interval, delay |

Xem kế hoạch quét (không gọi gì): `python scheduler.py --plan`.
Chạy 1 lượt: `python scheduler.py --once`. Lặp theo lịch: `python scheduler.py`.
Chưa viết stub → scheduler tự chạy **DRY-RUN**, in đúng các call sẽ thực hiện.

API hữu ích khác đã liệt kê ở [API_ENDPOINTS.md](API_ENDPOINTS.md) (đặt tháng, khoá,
danh sách sân/tên sân…).

## Ranh giới (giữ nhất quán)

- `fetch_raw.py` (tạo chữ ký `x-user-app` + gọi API) và `decrypt.py` (khôi phục key)
  là **của bạn** — mình dựng mọi thứ quanh chúng nhưng không viết thân, vì đó là phần
  hệ thống chặn (chống-bot / tấn công bên thứ ba).
