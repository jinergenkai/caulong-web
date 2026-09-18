#!/usr/bin/env python3
# probe3.py — chẩn đoán 403. pip install httpx pycryptodome  ;  (nếu cần) pip install curl_cffi
import base64, json, datetime as dt
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

BRANCH = "sport_bui_thi_xuan_badminton"
TOKEN  = "PASTE_TOKEN_MOI"   # token cũ chết sau 2h rồi, lấy token MỚI từ DevTools
X_USER = "8ddfb5c33587f13cbb6129628a633fee935c6b15882cc3b1db35f7ba36cce406"

URL = "https://user-global.alobo.vn/v2/user/branch/get_onetime_bookings"
KEY = b"0123456789_0123456789_9876542026"
UA  = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

HDR = {
  "accept":"*/*", "accept-language":"vi,en-US;q=0.9,en;q=0.8",
  "authorization":f"Bearer {TOKEN}",
  "origin":"https://datlich.alobo.vn", "referer":"https://datlich.alobo.vn/",
  "priority":"u=1, i",
  "sec-ch-ua":'"Google Chrome";v="153", "Not_A Brand";v="8", "Chromium";v="153"',
  "sec-ch-ua-mobile":"?0", "sec-ch-ua-platform":'"Windows"',
  "sec-fetch-dest":"empty", "sec-fetch-mode":"cors", "sec-fetch-site":"same-site",
  "user-agent":UA,
  "x-custom-lang":"vi", "x-name-app":"alobo-user", "x-platform":"web",
  "x-user-app":X_USER, "x-version-app":"2.10.1",
}
d1 = (dt.date.today()+dt.timedelta(days=1)).isoformat()
PARAMS = {"branchId":BRANCH, "startDate":d1, "endDate":d1}

def dec(env):
    if not isinstance(env,dict) or not env.get("enc"): return env
    iv=base64.b64decode(env["iv"]); ct=base64.b64decode(env["data"])
    return json.loads(unpad(AES.new(KEY,AES.MODE_CBC,iv).decrypt(ct),16).decode())
PII={"guest_name","guest_phone","phone","name","customerName","customerPhone","note","bookingCode"}
def red(o):
    if isinstance(o,dict): return {k:("***" if k in PII else red(v)) for k,v in o.items()}
    if isinstance(o,list): return [red(x) for x in o]
    return o

# [A] httpx + đủ header Chrome
try:
    import httpx
    r = httpx.get(URL, params=PARAMS, headers=HDR, timeout=25)
    print("[A] httpx full-headers:", r.status_code)
    if r.status_code==200:
        print(json.dumps(red(dec(r.json())), ensure_ascii=False, indent=2)[:2500])
    else:
        print("   ", r.text[:150])
except Exception as e:
    print("[A] error:", e)

# [B] curl_cffi giả TLS fingerprint Chrome (nếu [A] vẫn 403)
try:
    from curl_cffi import requests as creq
    r = creq.get(URL, params=PARAMS, headers=HDR, impersonate="chrome", timeout=25)
    print("\n[B] curl_cffi impersonate chrome:", r.status_code)
    if r.status_code==200:
        print(json.dumps(red(dec(r.json())), ensure_ascii=False, indent=2)[:2500])
    else:
        print("   ", r.text[:150])
except ImportError:
    print("\n[B] chưa cài curl_cffi → chạy: pip install curl_cffi  rồi chạy lại")
except Exception as e:
    print("\n[B] error:", e)