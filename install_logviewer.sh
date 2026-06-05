#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="nginx-log-analyzer"
INSTALL_DIR="/opt/nginx-log-analyzer"
SCRIPT_NAME="logviewer.py"
SCRIPT_PATH="${INSTALL_DIR}/${SCRIPT_NAME}"
CONFIG_FILE="/etc/${SERVICE_NAME}.conf"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
GITHUB_RAW_URL="https://raw.githubusercontent.com/88Dand/NginxLogViewer/main/logviewer.py"

DEFAULT_LOG_PATH="/var/www/api/nginx-logs/site.access.log"
DEFAULT_PORT="8080"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $*"; }
ok() { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

need_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    err "Запустите скрипт от root или через sudo"
    exit 1
  fi
}

has_tty() {
  [[ -r /dev/tty && -w /dev/tty ]]
}

ask() {
  local prompt="$1"
  local default="${2:-}"
  local answer

  if has_tty; then
    if [[ -n "$default" ]]; then
      read -r -p "$prompt [$default]: " answer < /dev/tty
      echo "${answer:-$default}"
    else
      read -r -p "$prompt: " answer < /dev/tty
      echo "$answer"
    fi
  else
    echo "$default"
  fi
}

pause() {
  if has_tty; then
    read -r -p "Нажмите Enter для продолжения..." _ < /dev/tty
  fi
}

require_cmds() {
  command -v python3 >/dev/null 2>&1 || {
    err "python3 не найден. Установите: apt update && apt install -y python3"
    exit 1
  }

  if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
    err "Нужен curl или wget"
    exit 1
  fi

  command -v systemctl >/dev/null 2>&1 || {
    err "systemctl не найден. Нужна система с systemd"
    exit 1
  }
}

download_file() {
  local url="$1"
  local dest="$2"

  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$dest"
  else
    wget -qO "$dest" "$url"
  fi
}


write_config() {
  local log_path="$1"
  local port="$2"

  cat > "$CONFIG_FILE" <<EOF
LOG_PATH=${log_path}
PORT=${port}
EOF

  chmod 0644 "$CONFIG_FILE"
  ok "Создан конфиг: $CONFIG_FILE"
}


install_app() {
  need_root
  require_cmds

  local log_path
  local port

  log_path="$(ask "Путь к access.log nginx" "$DEFAULT_LOG_PATH")"
  port="$(ask "Порт сервиса" "$DEFAULT_PORT")"

  info "Установка ${SERVICE_NAME}"

  mkdir -p "$INSTALL_DIR"
  chmod 0755 "$INSTALL_DIR"

  create_user

  info "Скачивание Python-скрипта..."
  download_file "$GITHUB_RAW_URL" "$SCRIPT_PATH"
  chmod 0755 "$SCRIPT_PATH"

  info "Проверка синтаксиса Python..."
  python3 -m py_compile "$SCRIPT_PATH"
  ok "Python-скрипт загружен и прошёл проверку"

  write_config "$log_path" "$port"
  grant_log_access "$log_path"

  cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Nginx Log Analyzer
After=network-online.target nginx.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root

WorkingDirectory=/opt/nginx-log-analyzer
EnvironmentFile=/etc/nginx-log-analyzer.conf

ExecStart=/usr/bin/python3 /opt/nginx-log-analyzer/logviewer.py ${LOG_PATH} ${PORT}

Restart=on-failure
RestartSec=5

StandardOutput=journal
StandardError=journal
SyslogIdentifier=nginx-log-analyzer
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF

  chmod 0644 "$SERVICE_FILE"

  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME"
  systemctl restart "$SERVICE_NAME"

  sleep 2

  if systemctl is-active --quiet "$SERVICE_NAME"; then
    ok "Сервис установлен и запущен"
  else
    err "Сервис не запустился"
    systemctl status "$SERVICE_NAME" --no-pager || true
    exit 1
  fi

  show_info
}

show_info() {
  echo
  echo "────────────────────────────────────────"
  ok "Информация"
  echo "Сервис:        ${SERVICE_NAME}"
  echo "Файл сервиса:  ${SERVICE_FILE}"
  echo "Конфиг:        ${CONFIG_FILE}"
  echo "Скрипт:        ${SCRIPT_PATH}"
  echo
  echo "Так как приложение обычно слушает 127.0.0.1, доступ напрямую:"
  echo "  http://127.0.0.1:${DEFAULT_PORT}"
  echo
  echo "Для внешнего доступа используйте nginx reverse proxy."
  echo
  echo "Команды:"
  echo "  sudo systemctl status ${SERVICE_NAME}"
  echo "  sudo journalctl -u ${SERVICE_NAME} -f"
  echo "  sudo systemctl restart ${SERVICE_NAME}"
  echo "────────────────────────────────────────"
}

status_app() {
  need_root
  systemctl status "$SERVICE_NAME" --no-pager || true
}

logs_app() {
  need_root
  journalctl -u "$SERVICE_NAME" -n 100 --no-pager || true
}

follow_logs_app() {
  need_root
  journalctl -u "$SERVICE_NAME" -f
}

diagnostics() {
  need_root

  echo "────────────────────────────────────────"
  info "Диагностика ${SERVICE_NAME}"
  echo

  echo "1. systemd:"
  systemctl is-enabled "$SERVICE_NAME" 2>/dev/null || true
  systemctl is-active "$SERVICE_NAME" 2>/dev/null || true
  echo

  echo "2. Файлы:"
  ls -l "$SCRIPT_PATH" 2>/dev/null || warn "Нет $SCRIPT_PATH"
  ls -l "$CONFIG_FILE" 2>/dev/null || warn "Нет $CONFIG_FILE"
  ls -l "$SERVICE_FILE" 2>/dev/null || warn "Нет $SERVICE_FILE"
  echo

  echo "3. Конфиг:"
  if [[ -f "$CONFIG_FILE" ]]; then
    cat "$CONFIG_FILE"
  else
    warn "Конфиг не найден"
  fi
  echo

  echo "4. Проверка Python:"
  if [[ -f "$SCRIPT_PATH" ]]; then
    python3 -m py_compile "$SCRIPT_PATH" && ok "Синтаксис Python OK"
  fi
  echo

  echo "5. Проверка лога:"
  local log_path
  log_path="$(grep '^LOG_PATH=' "$CONFIG_FILE" 2>/dev/null | cut -d= -f2- || true)"
  if [[ -n "$log_path" && -e "$log_path" ]]; then
    ls -l "$log_path"
    if sudo -u "$APP_USER" test -r "$log_path"; then
      ok "$APP_USER может читать лог"
    else
      err "$APP_USER не может читать лог"
    fi
  else
    warn "Лог не найден: ${log_path:-не задан}"
  fi
  echo

  echo "6. Последние логи сервиса:"
  journalctl -u "$SERVICE_NAME" -n 50 --no-pager || true
  echo "────────────────────────────────────────"
}

configure_log_path() {
  need_root

  local current_log current_port new_log new_port

  current_log="$(grep '^LOG_PATH=' "$CONFIG_FILE" 2>/dev/null | cut -d= -f2- || echo "$DEFAULT_LOG_PATH")"
  current_port="$(grep '^PORT=' "$CONFIG_FILE" 2>/dev/null | cut -d= -f2- || echo "$DEFAULT_PORT")"

  new_log="$(ask "Новый путь к access.log nginx" "$current_log")"
  new_port="$(ask "Порт сервиса" "$current_port")"

  write_config "$new_log" "$new_port"
  grant_log_access "$new_log"

  systemctl daemon-reload
  systemctl restart "$SERVICE_NAME"

  ok "Настройки обновлены"
}

uninstall_app() {
  need_root

  warn "Удаление ${SERVICE_NAME}"

  systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  systemctl disable "$SERVICE_NAME" 2>/dev/null || true

  rm -f "$SERVICE_FILE"
  rm -f "$CONFIG_FILE"
  rm -rf "$INSTALL_DIR"

  systemctl daemon-reload

  if id "$APP_USER" >/dev/null 2>&1; then
    userdel "$APP_USER" || true
  fi

  ok "Удаление завершено"
}

menu() {
  while true; do
    clear || true
    echo "Nginx Log Analyzer installer"
    echo "────────────────────────────────────────"
    echo "1) Установить / переустановить"
    echo "2) Статус сервиса"
    echo "3) Показать последние логи"
    echo "4) Смотреть логи в реальном времени"
    echo "5) Диагностика"
    echo "6) Изменить путь к access.log / порт"
    echo "7) Удалить сервис"
    echo "0) Выход"
    echo "────────────────────────────────────────"

    choice="$(ask "Выберите пункт" "1")"

    case "$choice" in
      1) install_app; pause ;;
      2) status_app; pause ;;
      3) logs_app; pause ;;
      4) follow_logs_app ;;
      5) diagnostics; pause ;;
      6) configure_log_path; pause ;;
      7) uninstall_app; pause ;;
      0) exit 0 ;;
      *) warn "Неверный пункт"; pause ;;
    esac
  done
}

case "${1:-}" in
  --install|-i) install_app ;;
  --status) status_app ;;
  --logs) logs_app ;;
  --follow-logs) follow_logs_app ;;
  --diagnostics|-d) diagnostics ;;
  --configure|-c) configure_log_path ;;
  --uninstall|-u) uninstall_app ;;
  --help|-h)
    echo "Использование:"
    echo "  sudo bash install_logviewer.sh"
    echo "  sudo bash install_logviewer.sh --install"
    echo "  sudo bash install_logviewer.sh --diagnostics"
    echo "  sudo bash install_logviewer.sh --uninstall"
    ;;
  *) menu ;;
esac
