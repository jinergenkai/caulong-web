/* Server chạy thử ở máy — KHÔNG dùng khi deploy.
 * Giả lập /api/data giống hệt bản trên Vercel, nhưng lưu vào file dev-data.json.
 *
 *   node dev-server.mjs
 *   → http://localhost:3210     (mật khẩu mặc định: 1234)
 *
 * Đổi mật khẩu:  ADMIN_PASS=abc node dev-server.mjs
 */
import http from "node:http";
import { readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { timingSafeEqual } from "node:crypto";

const PORT = process.env.PORT || 3210;
const PASS = process.env.ADMIN_PASS || "1234";
const STORE = new URL("./dev-data.json", import.meta.url);
const EMPTY = { v: 3, sessions: [], members: [], flags: {}, qr: "", note: "" };

async function readStore() {
  if (!existsSync(STORE)) return { rev: 0, updatedAt: null, data: EMPTY };
  try { return JSON.parse(await readFile(STORE, "utf8")); }
  catch { return { rev: 0, updatedAt: null, data: EMPTY }; }
}
const writeStore = p => writeFile(STORE, JSON.stringify(p));

function passOk(given) {
  const a = Buffer.from(String(given || ""), "utf8"), b = Buffer.from(PASS, "utf8");
  return a.length === b.length && timingSafeEqual(a, b);
}
const json = (res, code, obj) => {
  res.writeHead(code, { "Content-Type": "application/json", "Cache-Control": "no-store" });
  res.end(JSON.stringify(obj));
};

http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://x");

  if (url.pathname === "/api/data") {
    if (req.method === "GET") return json(res, 200, await readStore());
    if (req.method === "POST") {
      let raw = ""; for await (const c of req) raw += c;
      let body = {}; try { body = JSON.parse(raw); } catch {}
      if (!passOk(body.pass)) return json(res, 401, { error: "Sai mật khẩu." });
      if (body.check) return json(res, 200, { ok: true });
      const cur = await readStore();
      if (typeof body.rev !== "number" || body.rev !== cur.rev)
        return json(res, 409, { error: "conflict", server: cur });
      const next = { rev: cur.rev + 1, updatedAt: new Date().toISOString(), data: body.data };
      await writeStore(next);
      return json(res, 200, { ok: true, rev: next.rev, updatedAt: next.updatedAt });
    }
    return json(res, 405, { error: "Method không hỗ trợ." });
  }

  const file = url.pathname === "/" ? "index.html" : url.pathname.slice(1);
  try {
    const buf = await readFile(new URL("./" + file, import.meta.url));
    res.writeHead(200, {
      "Content-Type": file.endsWith(".html") ? "text/html; charset=utf-8" : "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
    });
    res.end(buf);
  } catch { res.writeHead(404); res.end("not found"); }
}).listen(PORT, () => console.log("http://localhost:" + PORT + "  (mật khẩu: " + PASS + ")"));
