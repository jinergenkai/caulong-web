# Heatmap sân trống — server Python

Xem trạng thái sân trống theo **từng sân × nhiều ngày**, nhấn mạnh ô **trống** để dễ săn.
Không API, không giải mã, không cần cài gì — chỉ đọc JSON đã giải mã sẵn trong `data/`.

## Chạy

```bash
cd alobo_crawler && python server.py
```

Mở http://127.0.0.1:8000 . Đổi cổng: `python server.py --port 9000`.

Có sẵn dữ liệu mẫu (`data/sample_*.json`) nên mở là thấy heatmap ngay. Muốn xem từ
máy khác trong mạng (hoặc qua Tailscale): `python server.py --host 0.0.0.0`.

## Đưa dữ liệu thật vào

Phần giải mã API bạn tự làm. Sau khi giải mã, lưu response `get_onetime_bookings`
(một ngày = một file) vào `data/`:

- `data/<gì cũng được>.json` — nếu chỉ theo dõi **một sân**.
- `data/<branchId>__<ngày>.json` — nếu **nhiều sân**: các file cùng `<branchId>`
  (phần trước `__`) được gom thành một branch, chọn ở ô trên cùng.

File phải đúng shape thật của `get_onetime_bookings` (list booking):

```json
[
  {"id":"...","time":"2026-09-19T18:00:00.000","duration":120,
   "services":[{"serviceId":"san_2","startTime":"2026-09-19T18:00:00.000","duration":120}],
   "type":"groupOneTime","status":1}
]
```

Server tự suy: `serviceId` → sân, `startTime`+`duration` → các ô 30 phút bị đặt,
còn lại trong giờ hoạt động = **trống**. Tải lại trang là thấy.

> Dữ liệu thật để trong `data/*.json` **không bị commit** (đã gitignore, tránh lộ PII).
> Chỉ `data/sample_*.json` được commit làm mẫu.

## Giao diện

- **Tổng quan**: lưới sân × ngày, mỗi ô = số ô trống buổi tối (càng xanh càng nhiều chỗ).
  Bấm một ô → nhảy sang chi tiết sân đó.
- **Chi tiết sân**: lưới ngày × giờ cho một sân; ô trống viền xanh + chấm, đã đặt đỏ,
  khoá xám, sự kiện ★ tím. Bên dưới liệt kê giờ trống từng ngày (chip xanh).
- Lọc **18:00–22:00** và **T2–T6** (bật sẵn — đúng mục tiêu). Bỏ tick để xem cả ngày / cả tuần.
- Hover xem chi tiết. Sáng/tối tự theo hệ thống. Chạy tốt trên điện thoại.

## Trạng thái

- `get_onetime_bookings` chỉ có **đặt lẻ**. Muốn đủ, gộp thêm `get_lock_yards` (Khoá)
  và `get_schedule_bookings?month=...` (đặt tháng) — adapter đã chừa status `locked`/`event`,
  bổ sung khi bạn có dữ liệu đó.
- File đang có: `server.py` (server), `adapt.py` (chuẩn hoá shape thật), `viz/index.html`
  (giao diện), `data/sample_*.json` (mẫu).
