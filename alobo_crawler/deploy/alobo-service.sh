#!/usr/bin/env bash
# =============================================================================
#  alobo-service.sh — cài / gỡ systemd service cho crawler "Sân trống"
#
#  Mô hình:  Vercel ──http──▶ Linode (IP public) ──WireGuard──▶ home server (crawler)
#
#    Trên HOME SERVER  (chạy crawler):   sudo ./alobo-service.sh install
#    Trên LINODE       (chuyển cổng):    sudo ./alobo-service.sh relay-install 10.8.0.2
#
#  Chạy  ./alobo-service.sh help  để xem đủ lệnh.
# =============================================================================
set -euo pipefail

SERVICE=alobo-crawler
RELAY=alobo-relay
UNIT=/etc/systemd/system/$SERVICE.service
RELAY_UNIT=/etc/systemd/system/$RELAY.service
CONF=/etc/default/$SERVICE                      # cấu hình đổi được mà không sửa unit
RELAY_CONF=/etc/default/$RELAY

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"         # thư mục alobo_crawler/
RUN_USER="${SUDO_USER:-$(id -un)}"

c_ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
c_warn() { printf '\033[33m!\033[0m %s\n' "$*"; }
die()    { printf '\033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }
need_root() { [[ $EUID -eq 0 ]] || die "Lệnh này cần quyền root: chạy lại với sudo"; }
need_systemd() { command -v systemctl >/dev/null || die "Máy này không có systemd"; }

usage() {
cat <<EOF
Cách dùng:  $(basename "$0") <lệnh> [tuỳ chọn]

── HOME SERVER (máy chạy crawler) ─────────────────────────────────────────────
  setup                 Tạo .venv + cài thư viện + Chromium cho Playwright (chạy 1 lần)
  install [tuỳ chọn]    Cài & bật service $SERVICE (tự chạy lại khi crash / khi khởi động máy)
      --crawl             Tự cào định kỳ (interval_min trong config.json). Mặc định: KHÔNG,
                          chỉ cào khi admin bấm "Cào ngay" trên web.
      --port N            Cổng lắng nghe (mặc định 8000)
      --trust CIDR        Thêm mạng được tin như "máy nhà" (lặp được), vd --trust 192.168.1.0/24
                          ⚠ KHÔNG thêm dải WireGuard: request từ Vercel đi qua relay sẽ mang
                          IP WireGuard của Linode → bị coi là máy nhà → bỏ qua token.
      --user U            Chạy dưới user U (mặc định: $RUN_USER)
  mode auto|manual      Bật / tắt tự cào định kỳ rồi khởi động lại (không cần cài lại)
  status                Trạng thái service
  logs                  Xem log trực tiếp (Ctrl+C để thoát)
  restart               Khởi động lại (sau khi sửa .env / config.json / git pull)
  uninstall             Dừng + gỡ service. GIỮ NGUYÊN code, .venv, data/, .env
  print-unit [tuỳ chọn] Chỉ in ra file service sẽ cài, không đụng gì (để xem trước)

── LINODE (máy có IP public, chuyển cổng qua WireGuard về nhà) ─────────────────
  relay-install <IP_WG_HOME> [--port N]
                        Mở cổng N (mặc định 8000) trên Linode, chuyển tiếp tới IP_WG_HOME:N
                        bằng socat. Cần: apt install socat
  relay-uninstall       Gỡ relay
  relay-status          Trạng thái relay

── Sau khi cài ────────────────────────────────────────────────────────────────
  Vercel → Environment Variables:
     CRAWLER_TOKEN        = giống PUSH_TOKEN trong alobo_crawler/.env
     CRAWLER_TRIGGER_URL  = http://<IP public Linode>:8000/api/crawl/run
  rồi Redeploy. Kiểm tra từ máy bất kỳ:  curl http://<IP Linode>:8000/api/crawl
EOF
}

# ---------------------------------------------------------------------------- crawler
python_bin() {
  if [[ -x "$APP_DIR/.venv/bin/python" ]]; then echo "$APP_DIR/.venv/bin/python"
  else command -v python3 || die "Không thấy python3. Chạy: $(basename "$0") setup"; fi
}

parse_install_opts() {
  CRAWL=""; PORT=8000; TRUST="127.0.0.0/8,::1/128"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --crawl) CRAWL="--crawl" ;;
      --port)  PORT="${2:?thiếu số cổng}"; shift ;;
      --trust) TRUST="$TRUST,${2:?thiếu CIDR}"; shift ;;
      --user)  RUN_USER="${2:?thiếu tên user}"; shift ;;
      *) die "Tuỳ chọn lạ: $1 (xem: $(basename "$0") help)" ;;
    esac; shift
  done
  [[ "$PORT" =~ ^[0-9]+$ ]] || die "Cổng phải là số: $PORT"
  id "$RUN_USER" >/dev/null 2>&1 || die "Không có user: $RUN_USER"
}

unit_text() {
cat <<EOF
# Sinh bởi alobo_crawler/deploy/alobo-service.sh — sửa bằng script, đừng sửa tay.
[Unit]
Description=ALOBO crawler — Sân trống (server.py)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$CONF
Environment=PYTHONUTF8=1
Environment=PYTHONUNBUFFERED=1
# \$CRAWL rỗng = chỉ cào khi được gọi; "--crawl" = tự cào định kỳ
ExecStart=$(python_bin) $APP_DIR/server.py --host 0.0.0.0 --port \${PORT} \$CRAWL
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF
}

conf_text() {
cat <<EOF
# Cấu hình $SERVICE — sửa xong chạy: sudo $(basename "$0") restart
PORT=$PORT
# "--crawl" = tự cào định kỳ, rỗng = chỉ cào khi admin bấm trên web
CRAWL=$CRAWL
# Mạng được tin như "máy nhà" (không cần token). KHÔNG thêm dải WireGuard.
TRUSTED_NETS=$TRUST
EOF
}

cmd_setup() {
  [[ $EUID -eq 0 && -n "${SUDO_USER:-}" ]] && die "Chạy setup KHÔNG cần sudo (để .venv thuộc user của bạn)"
  command -v python3 >/dev/null || die "Cần python3 (apt install python3 python3-venv)"
  cd "$APP_DIR"
  [[ -d .venv ]] || python3 -m venv .venv || die "Tạo venv lỗi — thử: sudo apt install python3-venv"
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
  c_ok "Đã cài thư viện vào $APP_DIR/.venv"
  echo "Cài Chromium cho Playwright (cần sudo cho thư viện hệ thống)…"
  sudo "$APP_DIR/.venv/bin/python" -m playwright install-deps chromium
  .venv/bin/python -m playwright install chromium
  c_ok "Xong. Tiếp: sudo $(basename "$0") install"
  [[ -f "$APP_DIR/.env" ]] || c_warn "Chưa có $APP_DIR/.env — copy từ .env.example rồi điền ALOBO_KEY, PUSH_URL, PUSH_TOKEN"
}

cmd_install() {
  need_root; need_systemd
  parse_install_opts "$@"
  [[ -f "$APP_DIR/server.py" ]] || die "Không thấy $APP_DIR/server.py"
  [[ -f "$APP_DIR/.env" ]] || c_warn "Chưa có $APP_DIR/.env — thiếu PUSH_TOKEN thì lệnh cào từ web sẽ bị từ chối"
  grep -qs '^PUSH_TOKEN=..' "$APP_DIR/.env" || c_warn "PUSH_TOKEN trong .env đang trống"
  conf_text > "$CONF"; chmod 644 "$CONF"
  unit_text > "$UNIT"
  systemctl daemon-reload
  systemctl enable --now "$SERVICE" >/dev/null
  sleep 2
  if systemctl is-active --quiet "$SERVICE"; then
    c_ok "Đã cài & chạy $SERVICE (cổng $PORT, $( [[ -n $CRAWL ]] && echo "TỰ cào định kỳ" || echo "chỉ cào khi bấm trên web"))"
    journalctl -u "$SERVICE" -n 15 --no-pager | grep -E "auto-crawl|bảo vệ|Nap" || true
  else
    c_warn "Service chưa chạy được — xem lỗi:"; journalctl -u "$SERVICE" -n 30 --no-pager; exit 1
  fi
}

cmd_mode() {
  need_root; [[ -f "$CONF" ]] || die "Chưa cài. Chạy: sudo $(basename "$0") install"
  case "${1:-}" in
    auto)   sed -i 's/^CRAWL=.*/CRAWL=--crawl/' "$CONF" ;;
    manual) sed -i 's/^CRAWL=.*/CRAWL=/' "$CONF" ;;
    *) die "Dùng: $(basename "$0") mode auto|manual" ;;
  esac
  systemctl restart "$SERVICE"; c_ok "Đã chuyển sang chế độ: $1"
}

cmd_uninstall() {
  need_root; need_systemd
  systemctl disable --now "$SERVICE" 2>/dev/null || true
  rm -f "$UNIT" "$CONF"
  systemctl daemon-reload; systemctl reset-failed "$SERVICE" 2>/dev/null || true
  c_ok "Đã gỡ $SERVICE. Code, .venv, data/, .env vẫn nguyên ở $APP_DIR"
}

# ---------------------------------------------------------------------------- relay (Linode)
cmd_relay_install() {
  need_root; need_systemd
  local target="${1:-}"; shift || true
  [[ -n "$target" ]] || die "Thiếu IP WireGuard của home server. Vd: $(basename "$0") relay-install 10.8.0.2"
  local port=8000
  while [[ $# -gt 0 ]]; do
    case "$1" in --port) port="${2:?}"; shift ;; *) die "Tuỳ chọn lạ: $1" ;; esac; shift
  done
  local socat; socat="$(command -v socat)" || die "Cần socat: apt install socat"
  printf 'PORT=%s\nTARGET=%s\n' "$port" "$target" > "$RELAY_CONF"
  cat > "$RELAY_UNIT" <<EOF
# Sinh bởi alobo-service.sh — chuyển cổng Linode → home server qua WireGuard
[Unit]
Description=ALOBO relay :$port → WireGuard $target
After=network-online.target wg-quick@wg0.service
Wants=network-online.target

[Service]
EnvironmentFile=$RELAY_CONF
ExecStart=$socat TCP-LISTEN:\${PORT},fork,reuseaddr TCP:\${TARGET}:\${PORT},connect-timeout=5
Restart=always
RestartSec=3
DynamicUser=yes
NoNewPrivileges=yes

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now "$RELAY" >/dev/null
  sleep 1
  systemctl is-active --quiet "$RELAY" || { journalctl -u "$RELAY" -n 20 --no-pager; die "Relay không chạy"; }
  c_ok "Relay: 0.0.0.0:$port → $target:$port"
  if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
    ufw allow "$port/tcp" >/dev/null && c_ok "ufw: đã mở cổng $port/tcp"
  else
    c_warn "Nhớ mở cổng $port/tcp trên firewall (Linode Cloud Firewall nếu có dùng)"
  fi
  if command -v curl >/dev/null; then
    curl -s -m 5 "http://$target:$port/api/crawl" >/dev/null \
      && c_ok "Gọi được crawler ở $target:$port qua WireGuard" \
      || c_warn "Chưa gọi được $target:$port — crawler đã chạy chưa? WireGuard đã lên chưa?"
  fi
}

cmd_relay_uninstall() {
  need_root; need_systemd
  systemctl disable --now "$RELAY" 2>/dev/null || true
  rm -f "$RELAY_UNIT" "$RELAY_CONF"
  systemctl daemon-reload; systemctl reset-failed "$RELAY" 2>/dev/null || true
  c_ok "Đã gỡ $RELAY (nếu đã mở cổng ufw, đóng lại bằng: sudo ufw delete allow 8000/tcp)"
}

# ---------------------------------------------------------------------------- main
cmd="${1:-help}"; shift || true
case "$cmd" in
  setup)           cmd_setup ;;
  install)         cmd_install "$@" ;;
  print-unit)      parse_install_opts "$@"; unit_text; echo; echo "# --- $CONF ---"; conf_text ;;
  mode)            cmd_mode "$@" ;;
  status)          need_systemd; systemctl status "$SERVICE" --no-pager || true ;;
  logs)            need_systemd; journalctl -u "$SERVICE" -f ;;
  restart)         need_root; systemctl restart "$SERVICE"; c_ok "Đã khởi động lại $SERVICE" ;;
  uninstall)       cmd_uninstall ;;
  relay-install)   cmd_relay_install "$@" ;;
  relay-uninstall) cmd_relay_uninstall ;;
  relay-status)    need_systemd; systemctl status "$RELAY" --no-pager || true ;;
  help|-h|--help)  usage ;;
  *) usage; echo; die "Lệnh lạ: $cmd" ;;
esac
