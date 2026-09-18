# API ALOBO hữu ích (đã quan sát trực tiếp qua DevTools, 2026-09-18)

Tất cả trả về envelope mã hoá `{"data","enc":true,"iv"}` (trừ vài cái tĩnh).
Header cần: `x-user-app` (ký theo thời gian), `x-version-app:2.10.1`, `x-platform:web`,
`x-name-app:alobo-user`, `x-custom-lang:vi`, `origin/referer = datlich.alobo.vn`.
**Không cần** Bearer token cho dữ liệu sân (xem ẩn danh). Rate limit: **30 req/phút**.

## Cho bài toán sân trống (quan trọng)

| Endpoint | Params | Trả về | Ghi chú |
|---|---|---|---|
| `GET /v2/user/branch/get_onetime_bookings` | `branchId, startDate, endDate` (=nhau, 1 ngày) | List **đặt lẻ** ngày đó | Đang dùng. 1 call/ngày |
| `GET /v2/user/branch/get_schedule_bookings` | `branchId, month=YYYY-MM` | **Đặt cố định theo tháng** | **1 call phủ cả tháng** — nhẹ hơn nhiều |
| `GET /v2/user/branch/get_lock_yards/{branchId}` | — | Sân/khung bị **khoá** | Để tô ô "Khoá" |
| `GET /v2/user/branch/get_cores/{branchId}` | — | Danh sách **sân (core)** | Có thể có **tên sân thật** (thay `san_1`) |
| `GET /v2/user/branch/get_core_types/{branchId}` | — | Loại sân | |

→ Gộp 4 cái đầu = bức tranh **đầy đủ** trạng thái sân (lẻ + tháng + khoá). Base host:
`https://user-global.alobo.vn`.

## Bổ trợ (thông tin sân, không cần cho lịch)

| Endpoint | Trả về |
|---|---|
| `GET /v2/user/branch/branch_info/{branchId}` | Thông tin chi nhánh (giờ mở, địa chỉ, ảnh) |
| `GET /v2/user/branch/get_branch/{branchId}` | Chi tiết chi nhánh |
| `GET /v2/user/branch/products/{branchId}` | Sản phẩm/dịch vụ + **giá** |
| `GET /v2/user/branch/list_reviews/{branchId}` | Đánh giá |
| `GET /v2/user/branch/branches?lastFetchBranch=` | Danh sách chi nhánh (đồng bộ) |
| `GET /v2/user/branch/get_quick_search` | Nhóm tìm kiếm nhanh |
| `GET /v2/user/sport_social_tag`, `/v2/user/sport_level` | Tag/level (social) |
| `GET /now` (user-global) | Giờ server — app dùng để ký `x-user-app` |
| `GET https://user-api-new.alobo.vn/api/v1/public/sport-type` | Loại môn (tĩnh) |

## Danh sách branchId (rút từ runtime, nhiều hơn branches.json 13 sân)

Quan sát runtime thấy hàng loạt, ví dụ: `sport_ace_pickleball_ho_chi_minh`,
`sport_bkf_pickleball_ho_chi_minh`, `sport_boss_pickleball_truong_tho`,
`sport_city_pickleball_kham_thien`, `sport_dong_phat_pickleball_arena`,
`sport_fpt_pickleball_coffee_club`, `sport_vu_thi_trang_badminton`,
`sport_loca_badminton`, `sport_paddle_park`, `sport_tada_cn1/cn2/cn3`,
`sport_tan_nguyen_cn1/cn2`, `sport_bui_thi_xuan_badminton` (đang theo dõi)... 
Toàn bộ list nằm trong `main.dart.js`/runtime; lấy đủ khi cần.
