/* Sổ Cầu Lông — API dữ liệu
 *
 *   GET  /api/data              → { rev, updatedAt, data }
 *   POST /api/data  {pass, check:1}          → kiểm mật khẩu
 *   POST /api/data  {pass, rev, data}        → ghi sổ, rev phải khớp
 *
 * Mật khẩu nằm ở biến môi trường ADMIN_PASS trên Vercel — không có trong code,
 * không lộ ra trình duyệt. Người xem không cần gì cả, chỉ gọi GET.
 *
 * Chống đè nhau: mỗi lần ghi rev tăng 1. Client phải gửi đúng rev nó đọc được.
 * Lệch rev = ai đó vừa sửa ở nơi khác → trả 409 kèm bản trên server.
 */
import { put, list } from "@vercel/blob";
import { timingSafeEqual } from "crypto";

const BLOB_NAME = "so-caulong.json";
const MAX_BYTES = 3 * 1024 * 1024;           // chặn payload quá to (ảnh đại diện + QR)
const EMPTY = { v: 3, sessions: [], members: [], flags: {}, qr: "", note: "" };

async function readStore() {
  const { blobs } = await list({ prefix: BLOB_NAME, limit: 1 });
  if (!blobs.length) return { rev: 0, updatedAt: null, data: EMPTY };
  const r = await fetch(blobs[0].url, { cache: "no-store" });
  if (!r.ok) throw new Error("Không đọc được kho dữ liệu (" + r.status + ")");
  const j = await r.json();
  return {
    rev: typeof j.rev === "number" ? j.rev : 0,
    updatedAt: j.updatedAt || null,
    data: j.data || EMPTY,
  };
}

async function writeStore(payload) {
  await put(BLOB_NAME, JSON.stringify(payload), {
    access: "public",
    contentType: "application/json",
    addRandomSuffix: false,
    allowOverwrite: true,
    cacheControlMaxAge: 0,                   // luôn lấy bản mới nhất, không để CDN giữ
  });
}

function passOk(given) {
  const want = process.env.ADMIN_PASS || "";
  if (!want) return false;                   // chưa đặt mật khẩu → khóa hẳn, không cho ghi
  const a = Buffer.from(String(given || ""), "utf8");
  const b = Buffer.from(want, "utf8");
  if (a.length !== b.length) return false;   // độ dài khác nhau thì khỏi so
  return timingSafeEqual(a, b);
}

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");

  try {
    if (req.method === "GET") {
      return res.status(200).json(await readStore());
    }

    if (req.method === "POST") {
      const body = typeof req.body === "string" ? JSON.parse(req.body) : req.body || {};

      if (!passOk(body.pass)) {
        return res.status(401).json({ error: "Sai mật khẩu." });
      }
      if (body.check) {
        return res.status(200).json({ ok: true });
      }
      if (!body.data || typeof body.data !== "object") {
        return res.status(400).json({ error: "Thiếu dữ liệu." });
      }

      const json = JSON.stringify(body.data);
      if (Buffer.byteLength(json, "utf8") > MAX_BYTES) {
        return res.status(413).json({ error: "Sổ quá nặng (>3MB). Xóa bớt ảnh đại diện hoặc mã QR." });
      }

      const cur = await readStore();
      if (typeof body.rev !== "number" || body.rev !== cur.rev) {
        // Ai đó đã lưu trong lúc bạn đang sửa — trả bản server về cho client tự xử
        return res.status(409).json({ error: "conflict", server: cur });
      }

      const next = { rev: cur.rev + 1, updatedAt: new Date().toISOString(), data: body.data };
      await writeStore(next);
      return res.status(200).json({ ok: true, rev: next.rev, updatedAt: next.updatedAt });
    }

    res.setHeader("Allow", "GET, POST");
    return res.status(405).json({ error: "Method không hỗ trợ." });
  } catch (e) {
    return res.status(500).json({ error: String((e && e.message) || e) });
  }
}
