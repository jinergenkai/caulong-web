# Sổ Cầu Lông — trang web

Một trang cho cả nhóm xem tiền, một mật khẩu cho mình sửa.

- **Người xem** (không cần gì cả): tìm tên mình → thấy nợ bao nhiêu, gồm những buổi nào,
  nội dung chuyển khoản, QR. Xem được cả nhóm và cách chia từng buổi. Tải được ảnh để lưu.
- **Chủ sổ** (bấm *Quản trị* ở cuối trang, nhập mật khẩu): thêm buổi, tick ai đã trả,
  quản lý thành viên + ảnh đại diện, gắn ảnh cho từng buổi chơi. Sửa xong **tự lưu**,
  cả nhóm refresh là thấy. Mọi thao tác được ghi vào **Lịch sử chỉnh sửa** (tab Thu tiền).

Ảnh (đại diện và ảnh buổi): bấm vào ô ảnh rồi **Ctrl+V**, hoặc kéo thả, hoặc bấm
**Chọn ảnh** ở thanh hiện ra — cách này dùng được trên điện thoại.

```
index.html        toàn bộ giao diện (xem + quản trị) — một file, không cần build
api/data.js       hàm chạy trên Vercel: GET đọc sổ · POST kiểm mật khẩu rồi ghi
dev-server.mjs    server chạy thử ở máy, KHÔNG deploy
```

---

## Đưa lên mạng (Vercel) — làm một lần

**1. Tạo repo mới trên GitHub**

⚠️ **Đừng dùng repo `jine-ws`.** Repo đó đang chứa `yt-downloader/cookies.txt`, file `.exe`
và nhạc mp3 — công khai nó là hỏng chuyện. Tạo repo riêng, chỉ chứa thư mục này:

```bash
cd caulong-web && git init && git add -A && git commit -m "So Cau Long" && git branch -M main
```

Rồi tạo repo trống trên github.com (private cũng được — Vercel deploy repo private miễn phí) và:

```bash
git remote add origin https://github.com/<tên-bạn>/<tên-repo>.git && git push -u origin main
```

**2. Nối vào Vercel**

Vào [vercel.com](https://vercel.com) → đăng nhập bằng GitHub → **Add New → Project** →
chọn repo vừa tạo → **Deploy**. Không cần chỉnh gì, để mặc định.

**3. Tạo kho dữ liệu**

Trong project vừa tạo: tab **Storage** → **Create Database** → chọn **Blob** → **Connect**.
Vercel tự thêm biến `BLOB_READ_WRITE_TOKEN`, bạn không phải copy gì cả.

Để kho ở dạng **Private** (mặc định). File JSON chứa cả mã QR ngân hàng của bạn —
private nghĩa là chỉ hàm `api/data.js` đọc được, người ngoài có link blob cũng chịu.
Lỡ tạo dạng Public thì thêm biến môi trường `BLOB_ACCESS=public` ở bước 4.

**4. Đặt mật khẩu**

Tab **Settings → Environment Variables** → thêm:

| Name | Value |
|---|---|
| `ADMIN_PASS` | mật khẩu bạn tự chọn |

**5. Deploy lại** — tab **Deployments** → dấu `···` ở bản mới nhất → **Redeploy**.
Bước này bắt buộc: biến môi trường chỉ có tác dụng từ lần deploy sau.

Xong. Link của bạn là `https://<tên-project>.vercel.app`

**6. Nạp dữ liệu cũ** — mở link → *Quản trị* → nhập mật khẩu → tab **Thu tiền** →
**Nhập file JSON** → chọn file xuất ra từ `badminton-bill.html`. Dữ liệu đời cũ tự nâng cấp.

---

## Dùng hằng ngày

Ngồi ở sân, mở link trên điện thoại:

1. *Quản trị* → nhập mật khẩu (máy nhớ, lần sau khỏi nhập)
2. **Buổi chơi → + Thêm buổi chơi** → tiền sân, số cầu, chọn người
3. Ai chuyển khoản thì bấm vào tên người đó trong buổi — hoặc tab **Thu tiền** để tick nhiều người một lượt
4. Không phải bấm Lưu. Thanh dưới màn hình báo *"Đã lưu · phiên bản N"* là xong.

Gửi cho nhóm: link trần, hoặc `?me=<id>` để tag riêng từng người (nút **Chép link riêng**),
hoặc tải ảnh ở nút 📸 rồi đăng.

---

## Những chỗ cần biết

**Ai cũng xem được toàn bộ.** Đúng như thiết kế — minh bạch thì dễ đòi tiền. Nhưng nghĩa là
link lọt ra ngoài thì người lạ đọc được tên, số tiền và QR của bạn. Trang đã gắn `noindex`
(Google không đánh chỉ mục) nhưng đừng đăng link chỗ công khai.

**Mật khẩu nằm ở server**, không có trong code, xem source không ra. Đây là mật khẩu thật.

**Không sửa được khi mất mạng** — cố tình. Sổ là một cục JSON, sửa offline rồi đồng bộ sau
sẽ đè mất thay đổi ở máy khác mà không báo gì. Người *xem* thì vẫn xem được số đã lưu trong máy.

**Mở 2 tab cùng sửa** thì tab lưu sau bị chặn, hiện hộp *"Sổ đã bị sửa ở nơi khác"* cho bạn
chọn lấy bản nào. Không bao giờ âm thầm mất dữ liệu.

**Backup**: tab Thu tiền có *Xuất JSON* và *Tải bản HTML tĩnh* (file chạy độc lập, mở bằng
`file://` cũng xem được, phòng khi Vercel hỏng).

---

## Gặp lỗi?

Thanh dưới màn hình hiện lỗi gì thì chữa theo đó:

| Báo lỗi | Nguyên nhân |
|---|---|
| `Kho Blob chưa được nối` | Bỏ qua bước 3, hoặc nối rồi mà quên Redeploy ở bước 5 |
| `Kiểu truy cập của kho không khớp` | Kho tạo dạng Public → thêm `BLOB_ACCESS=public` rồi Redeploy |
| `Sai mật khẩu` | `ADMIN_PASS` chưa đặt, hoặc đặt xong chưa Redeploy |
| `Sổ đã bị sửa ở nơi khác` | Không phải lỗi — bạn đang mở 2 tab/2 máy. Chọn giữ bản nào. |

Kiểm tra nhanh bằng `curl https://<project>.vercel.app/api/data` — ra `{"rev":0,...}` là ngon.

Biến môi trường **chỉ nạp lúc deploy**. Đổi env xong mà không Redeploy thì bản đang chạy
vẫn dùng cấu hình cũ — đây là chỗ hay vướng nhất.

---

## Chạy thử ở máy

```bash
node dev-server.mjs
```

→ http://localhost:3210, mật khẩu `1234`. Dữ liệu vào `dev-data.json` (đã gitignore).
Đổi mật khẩu: `ADMIN_PASS=abc node dev-server.mjs`

File này chỉ để test, không ảnh hưởng bản trên Vercel.
