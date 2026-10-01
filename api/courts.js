/* Sân trống — nhận dữ liệu từ crawler (webhook) và phát cho trang courts.html
 *
 *   GET  /api/courts   → { updatedAt, data }      (data = null nếu chưa có lần đẩy nào)
 *   POST /api/courts   header  Authorization: Bearer <CRAWLER_TOKEN>
 *                      body    đúng đầu ra load_data() của alobo_crawler/server.py
 *
 * Tách hẳn khỏi sổ tiền: blob riêng, token riêng, file riêng. Dữ liệu sân hỏng
 * hay endpoint này lỗi cũng không đụng được tới so-caulong.json.
 * Chỉ một nguồn ghi (crawler) nên không cần khoá rev — bản đẩy sau thay bản trước.
 */
import { put, get } from "@vercel/blob";
import { timingSafeEqual } from "crypto";

const BLOB_NAME = "courts.json";
const ACCESS = process.env.BLOB_ACCESS === "public" ? "public" : "private";
const MAX_BYTES = 4 * 1024 * 1024;       // Vercel giới hạn thân request ~4.5MB

function tokenOk(header) {
  const want = process.env.CRAWLER_TOKEN || "";
  if (!want) return false;               // chưa đặt token → không ai ghi được
  const given = String(header || "").replace(/^Bearer\s+/i, "");
  const a = Buffer.from(given, "utf8"), b = Buffer.from(want, "utf8");
  return a.length === b.length && timingSafeEqual(a, b);
}

function passOk(given) {                // cùng mật khẩu quản trị của sổ (ADMIN_PASS)
  const want = process.env.ADMIN_PASS || "";
  if (!want) return false;
  const a = Buffer.from(String(given || ""), "utf8"), b = Buffer.from(want, "utf8");
  return a.length === b.length && timingSafeEqual(a, b);
}

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  try {
    if (req.method === "GET") {
      const r = await get(BLOB_NAME, { access: ACCESS, useCache: false });
      if (!r || !r.stream) return res.status(200).json({ updatedAt: null, data: null });
      return res.status(200).json(await new Response(r.stream).json());
    }

    // Admin bấm "Cào ngay" trên courts.html → kiểm mật khẩu sổ → gọi server cào kèm token.
    // Chặng Vercel → server là server-gọi-server nên http://IP:cổng vẫn được (không dính mixed content).
    if (req.method === "POST" && req.query && req.query.action === "crawl") {
      const body = typeof req.body === "string" ? JSON.parse(req.body) : req.body || {};
      if (!passOk(body.pass)) return res.status(401).json({ error: "Sai mật khẩu quản trị." });
      const url = process.env.CRAWLER_TRIGGER_URL || "";
      if (!url) return res.status(501).json({ error: "Chưa đặt CRAWLER_TRIGGER_URL trên Vercel." });
      try {
        const r = await fetch(url, {
          method: "POST",
          headers: { Authorization: "Bearer " + (process.env.CRAWLER_TOKEN || "") },
          signal: AbortSignal.timeout(8000),
        });
        const j = await r.json().catch(() => ({}));
        return res.status(r.ok ? 200 : r.status).json(r.ok ? { ok: true } : { error: j.error || "Server cào trả " + r.status });
      } catch (e) {
        return res.status(502).json({ error: "Không gọi được server cào (máy tắt hoặc chưa mở cổng?): " + (e.message || e) });
      }
    }

    if (req.method === "POST") {
      if (!tokenOk(req.headers.authorization)) return res.status(401).json({ error: "Sai token." });
      const body = typeof req.body === "string" ? JSON.parse(req.body) : req.body || {};
      if (!body || !Array.isArray(body.branches)) {
        return res.status(400).json({ error: "Thiếu branches — gửi đúng đầu ra load_data()." });
      }
      const json = JSON.stringify({ updatedAt: new Date().toISOString(), data: body });
      if (Buffer.byteLength(json, "utf8") > MAX_BYTES) {
        return res.status(413).json({ error: "Dữ liệu sân quá nặng (>4MB). Bớt số sân hoặc số ngày." });
      }
      await put(BLOB_NAME, json, {
        access: ACCESS, contentType: "application/json",
        addRandomSuffix: false, allowOverwrite: true,
      });
      return res.status(200).json({ ok: true, branches: body.branches.length });
    }

    res.setHeader("Allow", "GET, POST");
    return res.status(405).json({ error: "Method không hỗ trợ." });
  } catch (e) {
    return res.status(500).json({ error: String((e && e.message) || e) });
  }
}
