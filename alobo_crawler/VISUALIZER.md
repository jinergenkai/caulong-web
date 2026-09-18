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

- **Theo ngày** (mặc định): chọn 1 ngày → lưới **giờ × sân**; ô trống viền xanh + chấm,
  đã đặt đỏ, **khoá kẻ sọc** (mở nhưng chưa book được — rình khi mở), sự kiện ★ tím.
  Cột "Trống" đếm số sân trống mỗi khung; bên dưới liệt kê **khung giờ còn sân nào** +
  "⏳ N khoá". Đúng cho: chọn Thứ 5, xem 18–20h còn sân nào.
- **Tổng quan**: lưới sân × ngày, mỗi ô = số ô trống buổi tối (càng xanh càng nhiều).
  Bấm một ô → mở "Theo ngày" của ngày đó.
- Lọc **18:00–22:00** (bật sẵn). Bỏ tick để xem cả ngày.
- Hover xem chi tiết. Sáng/tối tự theo hệ thống. Chạy tốt trên điện thoại.

## Trạng thái (đã gộp đủ)

Server tự gộp mỗi branch từ các file trong `data/`:
- `<branch>__<ngày>.json` (`get_onetime_bookings`) → **Đã đặt** (đặt lẻ).
- `<branch>__schedule_*.json` (`get_schedule_bookings`) → **Đã đặt** (đặt tháng).
- `<branch>__locks.json` (`get_lock_yards`) → **Khoá** (sân mở nhưng chặn book).
- `<branch>__cores.json` (`get_cores`) → **tên + thứ tự + danh sách sân thật**.

Ưu tiên hiển thị: Đã đặt > Khoá > Trống. "Trống" = sân tồn tại, **không** đặt **và không** khoá.

File: `server.py` (server + control), `adapt.py` (chuẩn hoá + gộp status),
`viz/index.html` (giao diện), `data/sample_*.json` (mẫu).
