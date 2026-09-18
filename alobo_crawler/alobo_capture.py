#!/usr/bin/env python3
"""TEST 2 - Bat get_onetime_bookings bang cach DE CHINH APP THAT KY.

Khong forge chu ky x-user-app. Ta chi mo trang that bang Playwright, de app
tu goi API, roi doc response tu tang network (CDP) qua page.on("response").

DA KIEM CHUNG (xem FINDINGS.md, 2026-09-18):
  - CO cho bat: page.on("response") (muc CDP) bat duoc response.
  - Hook window.fetch / XMLHttpRequest trong trang -> RONG (Flutter khong di qua
    fetch/XHR bat duoc, ke ca inject truoc khi app chay). INIT_JS ben duoi giu lai
    chi de phong ho, thuc te KHONG bat duoc gi -> dung page.on("response").
  - DECRYPT hien BE TAC: key trong bundle (gOX/gadl/gJk...) KHONG giai duoc
    response build 2.10.1 (key dung runtime XOR, obfuscate). Nen script in duoc
    envelope + params + headers (da che secret) nhung SHAPE se bao loi decrypt.
    -> Muon co du lieu co cau truc ma khong decrypt: dung doc-mau-luoi (FINDINGS.md).

Muc tieu (3 cau hoi con mo trong handoff):
  Q1. Cau truc JSON that     -> chi doc duoc khi co key runtime (hien chua)
  Q2. startDate/endDate range -> --probe-range N (sua endDate cua request app da ky)
  Q3. Playwright bat response OK? -> CO (envelope bat duoc; decrypt thi chua)

Cai dat:
    pip install -r requirements.txt
    python -m playwright install chromium

Chay lan dau (khuyen nghi - tu tay bam, script chi ngoi nghe):
    python alobo_capture.py --branch sport_bui_thi_xuan_badminton --manual

Chay tu dong (thu dieu khien UI qua Flutter semantics):
    python alobo_capture.py --branch sport_bui_thi_xuan_badminton --headful

Hoi Q2 (doi endDate cua CHINH request ma app da ky, khong dung lai chu ky cu):
    python alobo_capture.py --branch sport_bui_thi_xuan_badminton --manual --probe-range 7
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import sys
import time
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import alobo_codec as C

BASE = "https://datlich.alobo.vn"
API_HOST = "user-global.alobo.vn"
TARGET = "get_onetime_bookings"

# Header co chu ky / token -> chi ghi nhan CO hay KHONG, khong bao gio luu gia tri.
SECRET_HEADERS = {"authorization", "x-user-app", "cookie", "set-cookie"}

CHROMIUM_ARGS = [  # cho VPS 1GB RAM
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--renderer-process-limit=2",
]

# Hook window.fetch / XHR lam duong du phong, phong khi doc body tu tang
# network that bai. Chay TRUOC khi app khoi dong.
INIT_JS = r"""
(() => {
  const KEEP = 60;
  window.__ALOBO = { hits: [] };
  const push = (rec) => {
    window.__ALOBO.hits.push(rec);
    if (window.__ALOBO.hits.length > KEEP) window.__ALOBO.hits.shift();
  };
  const want = (u) => typeof u === 'string' && u.indexOf('alobo.vn') !== -1
                      && u.indexOf('/v2/') !== -1;

  const of = window.fetch;
  window.fetch = async function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const res = await of.apply(this, arguments);
    if (want(url)) {
      try {
        const txt = await res.clone().text();
        push({ via: 'fetch', url: url, status: res.status, body: txt, t: Date.now() });
      } catch (e) { push({ via: 'fetch', url: url, err: String(e), t: Date.now() }); }
    }
    return res;
  };

  const oo = XMLHttpRequest.prototype.open;
  const os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) {
    this.__u = u; return oo.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    this.addEventListener('load', () => {
      if (want(this.__u)) {
        push({ via: 'xhr', url: this.__u, status: this.status,
               body: this.responseText, t: Date.now() });
      }
    });
    return os.apply(this, arguments);
  };
})();
"""


# --------------------------------------------------------------------------- #
# tien ich
# --------------------------------------------------------------------------- #
def log(*a):
    print(f"[{dt.datetime.now():%H:%M:%S}]", *a, flush=True)


def safe_headers(h: dict) -> dict:
    """Giu ten header, che gia tri bi mat."""
    out = {}
    for k, v in h.items():
        lk = k.lower()
        if lk in SECRET_HEADERS:
            out[k] = f"<co, len={len(v)}>"
        else:
            out[k] = v
    return out


def jwt_info(auth_header: str | None) -> dict:
    """Chi lay iat/exp de biet token con song bao lau. Khong lay gi khac."""
    if not auth_header or "." not in auth_header:
        return {}
    try:
        payload = auth_header.split(" ")[-1].split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}
    out = {}
    for k in ("iat", "exp"):
        if isinstance(data.get(k), (int, float)):
            out[k] = dt.datetime.fromtimestamp(data[k]).isoformat(timespec="seconds")
    if "exp" in data:
        left = data["exp"] - time.time()
        out["con_lai_phut"] = round(left / 60, 1)
    return out


def qs_of(url: str) -> dict:
    return {k: v[0] if len(v) == 1 else v for k, v in parse_qs(urlparse(url).query).items()}


def with_end_date(url: str, end: str) -> str:
    u = urlparse(url)
    q = parse_qs(u.query)
    q["endDate"] = [end]
    return urlunparse(u._replace(query=urlencode(q, doseq=True)))


# --------------------------------------------------------------------------- #
# dieu khien UI Flutter CanvasKit qua semantics tree
# --------------------------------------------------------------------------- #
def enable_semantics(page) -> bool:
    """Flutter web an mot nut 'Enable accessibility'. Bam vao do thi Flutter
    dung mot cay DOM <flt-semantics> co aria-label -> click duoc theo CHU,
    khoi phai mo toa do."""
    try:
        ph = page.locator("flt-semantics-placeholder")
        if ph.count():
            ph.first.click(timeout=3000, force=True)
            page.wait_for_timeout(800)
        n = page.locator("flt-semantics[aria-label]").count()
        log(f"semantics: {n} node co aria-label")
        return n > 0
    except Exception as e:
        log("semantics: bat that bai ->", e)
        return False


def semantic_labels(page) -> list[str]:
    try:
        return page.eval_on_selector_all(
            "flt-semantics[aria-label]", "els => els.map(e => e.getAttribute('aria-label'))"
        )
    except Exception:
        return []


def click_label(page, patterns: list[str], timeout_ms: int = 8000) -> str | None:
    """Bam node semantics dau tien co aria-label khop 1 trong cac regex."""
    rx = [re.compile(p, re.I) for p in patterns]
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        labels = semantic_labels(page)
        for i, lab in enumerate(labels):
            if lab and any(r.search(lab) for r in rx):
                try:
                    page.locator("flt-semantics[aria-label]").nth(i).click(
                        timeout=3000, force=True)
                    log(f"clicked: {lab!r}")
                    page.wait_for_timeout(1200)
                    return lab
                except Exception as e:
                    log(f"click {lab!r} loi: {e}")
        page.wait_for_timeout(500)
    return None


def auto_navigate(page) -> bool:
    """Dat lich -> Dat lich theo san - truc quan."""
    if not enable_semantics(page):
        log("!! khong bat duoc semantics -> khong the click theo chu.")
        return False
    log("labels dang co:", semantic_labels(page)[:25])
    if not click_label(page, [r"^\s*đặt\s*lịch", r"dat\s*lich", r"^\s*booking"]):
        log("!! khong thay nut 'Đặt lịch'")
        return False
    if not click_label(page, [r"trực\s*quan", r"truc\s*quan", r"theo\s*sân"]):
        log("!! khong thay 'Đặt lịch theo sân - trực quan' (co the da vao thang luoi)")
    return True


# --------------------------------------------------------------------------- #
# capture
# --------------------------------------------------------------------------- #
class Collector:
    def __init__(self):
        self.pending = []   # (url, request_headers, Response)
        self.seen = set()

    def on_response(self, resp):
        url = resp.url
        if API_HOST not in url or "/v2/" not in url:
            return
        try:
            hdrs = resp.request.headers
        except Exception:
            hdrs = {}
        self.pending.append((url, hdrs, resp))
        tag = "  <== MUC TIEU" if TARGET in url else ""
        log(f"api {resp.status} {urlparse(url).path}{tag}")

    def drain(self, page) -> list[dict]:
        """Doc body cua cac response da bat. Uu tien tang network, hong thi
        lay tu hook window.fetch."""
        out = []
        for url, hdrs, resp in self.pending:
            body = None
            try:
                body = resp.text()
            except Exception as e:
                log(f"doc body tu network that bai ({e}) -> thu hook JS")
            if body is None:
                body = self._from_js(page, url)
            if body is None:
                continue
            out.append({"url": url, "params": qs_of(url), "status": resp.status,
                        "headers": safe_headers(hdrs), "body_text": body})
        self.pending.clear()
        return out

    @staticmethod
    def _from_js(page, url: str) -> str | None:
        try:
            hits = page.evaluate("() => (window.__ALOBO && window.__ALOBO.hits) || []")
        except Exception:
            return None
        for h in reversed(hits):
            if h.get("url") == url and h.get("body"):
                return h["body"]
        return None


def analyse(rec: dict, verbose: bool) -> dict:
    """envelope -> object -> (shape, redacted). Khong bao gio tra ve raw."""
    res = {"url": rec["url"], "params": rec["params"], "status": rec["status"],
           "headers": rec["headers"]}
    auth = next((v for k, v in rec["headers"].items() if k.lower() == "authorization"), None)
    if auth:
        res["token"] = "<da an>"
    try:
        env = json.loads(rec["body_text"])
    except Exception as e:
        res["error"] = f"body khong phai JSON: {e}; 120 ky tu dau = {rec['body_text'][:120]!r}"
        return res
    res["enc"] = C.is_envelope(env)
    try:
        obj = C.decrypt(env)
    except C.DecryptError as e:
        res["error"] = f"decrypt that bai: {e}"
        return res
    res["shape"] = C.shape(obj)
    if verbose:
        res["data_redacted"] = C.redact(obj)
    return res


# --------------------------------------------------------------------------- #
def run(args) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Thieu playwright. Chay:\n  pip install -r requirements.txt\n"
              "  python -m playwright install chromium")
        return 2

    os.makedirs(args.out, exist_ok=True)
    headless = not (args.headful or args.manual)
    probe = args.probe_range is not None

    col = Collector()
    results = []

    with sync_playwright() as pw:
        launch = dict(headless=headless, args=CHROMIUM_ARGS)
        if args.profile:
            ctx = pw.chromium.launch_persistent_context(
                args.profile, locale="vi-VN", viewport={"width": 1366, "height": 900}, **launch)
            browser = None
        else:
            browser = pw.chromium.launch(**launch)
            ctx = browser.new_context(locale="vi-VN", viewport={"width": 1366, "height": 900})

        ctx.set_default_timeout(20000)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.add_init_script(INIT_JS)
        page.on("response", col.on_response)
        page.on("console", lambda m: log("console:", m.type, m.text[:160])
                if m.type == "error" else None)

        if probe:
            def reroute(route):
                r = route.request
                if TARGET not in r.url:
                    route.continue_()
                    return
                q = qs_of(r.url)
                start = q.get("startDate")
                try:
                    end = (dt.date.fromisoformat(start)
                           + dt.timedelta(days=args.probe_range)).isoformat()
                except Exception:
                    log(f"probe-range: startDate={start!r} khong doc duoc, bo qua")
                    route.continue_()
                    return
                log(f"probe-range: {start}..{q.get('endDate')} -> {start}..{end}")
                route.continue_(url=with_end_date(r.url, end))
            page.route(f"**/*{TARGET}*", reroute)

        for branch in args.branch:
            url = f"{BASE}/san/{branch}"
            log(f"=== {branch} ===")
            log("mo", url)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception as e:
                log("goto loi:", e)
                continue

            # cho Flutter khoi dong
            try:
                page.wait_for_selector("flt-glass-pane, flutter-view, canvas", timeout=45000)
                log("Flutter da render")
            except Exception:
                log("!! khong thay canvas Flutter sau 45s (Cloudflare chan? mang cham?)")

            page.wait_for_timeout(2500)

            if args.manual:
                print("\n--- CHE DO THU CONG ---")
                print("Tu bam trong cua so trinh duyet: Dat lich -> Dat lich theo san"
                      " - truc quan, roi doi ngay qua lai.")
                print(f"Script se nghe {args.wait}s roi tu tong ket. Ctrl+C de dung som.\n")
            else:
                auto_navigate(page)

            end = time.time() + args.wait
            try:
                while time.time() < end:
                    page.wait_for_timeout(1000)
            except KeyboardInterrupt:
                log("dung som theo yeu cau")

            shot = os.path.join(args.out, f"{branch}.png")
            try:
                page.screenshot(path=shot, full_page=False)
                log("screenshot:", shot)
            except Exception:
                pass

            for rec in col.drain(page):
                if TARGET not in rec["url"] and not args.all_endpoints:
                    continue
                results.append({"branch": branch, **analyse(rec, args.verbose)})

        if browser:
            browser.close()
        else:
            ctx.close()

    # ----------------------------------------------------------------- bao cao
    hits = [r for r in results if TARGET in r["url"]]
    print("\n" + "=" * 70)
    print(f"BAT DUOC {len(results)} response ({len(hits)} cai la {TARGET})")
    print("=" * 70)

    for r in results:
        print(f"\n--- {r['branch']} | {urlparse(r['url']).path}")
        print("   params:", json.dumps(r["params"], ensure_ascii=False))
        if "error" in r:
            print("   LOI:", r["error"])
            continue
        print(f"   enc={r.get('enc')}  status={r['status']}")
        print("   SHAPE:")
        print(json.dumps(r.get("shape"), ensure_ascii=False, indent=2)[:6000])

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(args.out, f"capture_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nDa luu (DA REDACT PII): {path}")

    # Ket luan cho 3 cau hoi con mo
    print("\n--- KET LUAN ---")
    print(f"Q3 bat+decrypt duoc?  {'CO' if any('shape' in r for r in hits) else 'CHUA'}")
    if probe:
        for r in hits:
            p = r["params"]
            same = p.get("startDate") == p.get("endDate")
            print(f"Q2 range: startDate={p.get('startDate')} endDate={p.get('endDate')} "
                  f"-> {'API tu choi/bo qua range' if same else 'API NHAN range'}"
                  f"{'' if 'error' not in r else ' (nhung ' + r['error'][:60] + ')'}")
    else:
        print("Q2 range: chua thu, chay lai voi --probe-range 7")
    return 0 if hits else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--branch", action="append", required=True,
                    help="branchId, lap lai duoc (vd sport_bui_thi_xuan_badminton)")
    ap.add_argument("--manual", action="store_true",
                    help="mo cua so that, BAN tu bam, script chi nghe (tin cay nhat)")
    ap.add_argument("--headful", action="store_true", help="hien cua so, script tu bam")
    ap.add_argument("--profile", help="thu muc profile de giu dang nhap giua cac lan chay")
    ap.add_argument("--wait", type=int, default=60, help="giay nghe moi san (mac dinh 60)")
    ap.add_argument("--out", default="captures", help="thu muc ket qua")
    ap.add_argument("--probe-range", type=int, metavar="N",
                    help="doi endDate cua request thanh hom nay+N de xem API co nhan range")
    ap.add_argument("--all-endpoints", action="store_true",
                    help="giu ca cac endpoint /v2/ khac, khong chi get_onetime_bookings")
    ap.add_argument("--verbose", action="store_true",
                    help="luu them data da redact, khong chi shape")
    args = ap.parse_args()
    if args.probe_range is not None and args.probe_range < 0:
        ap.error("--probe-range phai >= 0")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
