# FINDINGS — kiểm chứng thật bằng browser + Chrome DevTools (CDP)

Ngày test: 2026-09-18. Sân test: `sport_bui_thi_xuan_badminton`.
Đây là những gì **đo được trực tiếp**, không phải suy đoán. Nhiều điểm **mâu thuẫn với HANDOFF**.

## 1. Danh sách branchId
- `GET /assets/assets/json/branches.json` (file tĩnh) → 13 sân, nhưng đây chỉ là
  config landing page. `sport_bui_thi_xuan_badminton` **KHÔNG** có trong đó → file này
  **không phải registry đầy đủ**. branchId lấy từ path `/san/<branchId>`.
- 13 id thấy được: `sport_minh_nhat_cn1`, `dong_an_1`, `sport_tuong_anh_cn1`,
  `sport_tan_nguyen_cn1/cn2`, `sport_tada_cn1/cn2/cn3`, `sport_dao_tri_cn1`,
  `sport_vu_thi_trang_badminton`, `sport_loca_badminton`, `sport_paddle_park`.

## 2. Endpoint & auth — MÂU THUẪN với handoff
- `GET https://user-global.alobo.vn/v2/user/branch/get_onetime_bookings?branchId=..&startDate=YYYY-MM-DD&endDate=YYYY-MM-DD`
- App gọi **1 ngày/lần** (`startDate == endDate`) — xác nhận từ chính request của app.
- Request trần (không header) → **401 Unauthorized**. Handoff ghi 403 "kiểm tra thời gian
  thiết bị" — cái 403 đó là do gửi `x-user-app` CŨ; còn thiếu hẳn thì ra 401.
- **Header app thật sự gửi** (bắt qua CDP, request `branch_info`/`get_quick_search`):
  ```
  x-user-app: 18dfa544e0e2692a0c6345ddc43ae2038a99a8296197391360fd2c001e92e5c9  (64-hex, đổi theo thời gian)
  x-version-app: 2.10.1
  x-platform: web
  x-name-app: alobo-user
  x-custom-lang: vi
  origin: https://datlich.alobo.vn
  referer: https://datlich.alobo.vn/
  ```
- **KHÔNG có `authorization: Bearer`** cho dữ liệu sân khi xem ẩn danh. Handoff nói cần
  JWT sống ~2h — **sai với luồng xem lịch**. Không cần token; chỉ cần chữ ký `x-user-app`.
- **Rate limit**: response trả `x-ratelimit-limit: 30`, `x-ratelimit-remaining`, `x-ratelimit-reset`
  → ~**30 request / phút**. Đây là ràng buộc thiết kế crawler (15 ngày × N sân phải nằm dưới ngưỡng).

## 3. `x-user-app` = chữ ký chống-bot (giữ nguyên kết luận handoff)
- Là SHA-256 64-hex, nhúng timestamp, sinh trong app mỗi request.
- Tôi **không** tái tạo/forge nó (ranh giới cố ý). Mọi cách "kéo API không trình duyệt"
  đều vướng đúng chỗ này.

## 4. Giải mã response — KEY TRONG HANDOFF ĐÃ SAI với build 2.10.1
- Response là envelope `{"data":"<b64>","enc":true,"iv":"<b64>"}`. Đọc bundle xác nhận:
  `AES/CBC/PKCS7`, key = UTF-8 của `$.kH().gOX()`, iv = base64(iv field), ct = base64(data field).
- **Nhưng** giải mã 2 response THẬT (`get_quick_search`, `branch_info`) bằng key handoff
  `0123456789_0123456789_9876542026` → **thất bại** (padding sai / ra rác). Kiểm chứng
  cả bằng Python (pycryptodome) LẪN WebCrypto ngay trong app → cùng fail.
- Trong bundle còn nhiều key/iv ứng viên (đều thử, đều fail):
  - `gadl/gYd = 5v8y/B?E(H+MbQeThWmZq4t7w!z$C&F)` (32) + iv cố định `gYc = vavwBT/X+av1+dg0+Z5KBQ==`
  - `gJk = 0123456789_0123456789_0123456789` (32) + iv `gJj = bmjSyRV4MLcxfvEWGJdqXQ==`
  - `ga0C = Alobo-User-Key-2026`, `ga1s = JvusR8Y9lt6U8YfzjASPVIhuptk25HsALK1wEqxn`
  - đã brute cả utf8 / base64 / md5 / sha256 × CBC/ECB × các iv, kèm thử giải nén → **0 hit**.
- Getter thật là `gOX(){return this.f}` (field runtime), và cạnh nó có hàm
  `$1(a){return (B.bnp[a] ^ B.bmC[a]) >>> 0}` → **key được dựng runtime bằng XOR 2 bảng byte**
  (obfuscation cố ý). Tái tạo cái này là vượt lớp chống-bot → **DỪNG**, không làm.

## 5. Cơ chế mạng của Flutter — quan trọng cho cách bắt
- App Flutter **không đi qua `window.fetch` cũng không qua `XMLHttpRequest`** ở mức bắt được.
  Hook page-context (kể cả `initScript` chạy TRƯỚC mọi script) → **rỗng tuyệt đối**.
- Chỉ tầng **CDP Network** (DevTools) thấy request. Kết luận: muốn bắt phải dùng
  **Playwright `page.on("response")`** (mức CDP), KHÔNG phải hook `fetch` trong trang.
- Handoff đề xuất "hook window.fetch" → **không dùng được**. Đây là lý do bản `alobo_capture.py`
  dùng `page.on("response")` làm cơ chế chính.

## 6. Lưới (grid) là canvas thuần
- Accessibility/semantics tree chỉ có 4 node (menu), **không lộ ô lịch**. Ô sân được vẽ pixel.
- Đọc có cấu trúc chỉ còn 2 cửa: (a) API (vướng chữ ký + decrypt), hoặc (b) đọc màu screenshot.
- Legend màu (đọc từ lưới thật): **Trắng = Trống**, **Đỏ = Đã đặt**, **Xám = Khoá**, **Tím = Sự kiện**.
- Lưới có dòng: "Khách đặt lịch tháng vui lòng liên hệ 0979496086" → **có đặt cố định theo tháng**.

## Kết luận theo 3 tầng (từ dễ → khó)

| Tầng | Cách | Kết luận (bằng chứng) |
|---|---|---|
| **Dễ** — kéo API, không trình duyệt | httpx/curl + header | **KHÔNG khả thi**. Vướng chữ ký `x-user-app` theo thời gian (401/403) **và** decrypt (key bị XOR-obfuscate). Cả hai là rào cản cố ý. |
| **Vừa** — Playwright để app tự ký, bắt response | `page.on("response")` + decrypt | Bắt được envelope OK. **Nhưng hiện KHÔNG đọc được data** vì key build 2.10.1 chưa giải được. Bế tắc ở decrypt cho tới khi có key đúng. |
| **Khó** — Playwright lái app + đọc màu screenshot | chụp lưới, dò màu ô tại toạ độ | **KHẢ THI & bền nhất**. Không forge chữ ký, không cần token, không cần decrypt. Chỉ dùng app thật render rồi đọc pixel. Đây là đường **khuyến nghị**. |

**Khuyến nghị**: đi tầng Khó (Playwright lái app thật + đọc màu lưới). Nó né toàn bộ
chữ ký + mã hoá, chỉ đọc thứ mắt người cũng đọc được. Tầng Vừa chỉ nối lại được nếu
sau này lấy đúng key runtime (không khuyến khích vì phải phá XOR obfuscation).

**Bối cảnh**: sân có đặt cố định theo tháng (liên hệ SĐT) → bài toán giữ slot 18–22h
T2–T6 có thể giải bằng đặt tháng, nhẹ hơn nuôi bot săn slot hủy.
