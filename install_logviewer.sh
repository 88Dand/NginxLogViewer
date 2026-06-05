#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE_NAME="nginx-log-analyzer"
INSTALL_DIR="/opt/nginx-log-analyzer"
SCRIPT_NAME="logviewer.py"
SCRIPT_PATH="${INSTALL_DIR}/${SCRIPT_NAME}"
CONFIG_FILE="/etc/${SERVICE_NAME}.conf"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

GITHUB_OWNER="88Dand"
GITHUB_REPO="NginxLogViewer"
GITHUB_BRANCH="main"
GITHUB_RAW_BASE="https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/${GITHUB_BRANCH}"

DEFAULT_LOG_PATH="/var/www/api/nginx-logs/site.access.log"
DEFAULT_HOST="0.0.0.0"
DEFAULT_PORT="8080"
DEFAULT_MAX_HISTORY="10000"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${BLUE}[INFO]${NC} $*"; }
ok() { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

LOG_PATH="$DEFAULT_LOG_PATH"
HOST="$DEFAULT_HOST"
PORT="$DEFAULT_PORT"
MAX_HISTORY="$DEFAULT_MAX_HISTORY"
AUTO_INSTALL="false"

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
  local answer=""

  if has_tty; then
    read -r -p "$prompt [$default]: " answer < /dev/tty
    echo "${answer:-$default}"
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
    err "systemctl не найден. Нужна Ubuntu/Debian-система с systemd"
    exit 1
  }
}

load_existing_config() {
  if [[ -f "$CONFIG_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE" || true
  fi

  LOG_PATH="${LOG_PATH:-$DEFAULT_LOG_PATH}"
  HOST="${HOST:-$DEFAULT_HOST}"
  PORT="${PORT:-$DEFAULT_PORT}"
  MAX_HISTORY="${MAX_HISTORY:-$DEFAULT_MAX_HISTORY}"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --install|-i)
        AUTO_INSTALL="true"
        shift
        ;;
      --log-path)
        LOG_PATH="${2:?Не указан путь к логу}"
        shift 2
        ;;
      --host|--ip)
        HOST="${2:?Не указан IP/host}"
        shift 2
        ;;
      --port)
        PORT="${2:?Не указан порт}"
        shift 2
        ;;
      --max-history)
        MAX_HISTORY="${2:?Не указан max-history}"
        shift 2
        ;;
      --branch)
        GITHUB_BRANCH="${2:?Не указана ветка}"
        GITHUB_RAW_BASE="https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/${GITHUB_BRANCH}"
        shift 2
        ;;
      --help|-h)
        show_help
        exit 0
        ;;
      *)
        err "Неизвестный параметр: $1"
        show_help
        exit 1
        ;;
    esac
  done
}

show_help() {
  cat <<EOF
Использование:

  sudo bash install_logviewer.sh

  sudo bash install_logviewer.sh --install \\
    --log-path /var/www/api/nginx-logs/site.access.log \\
    --host 0.0.0.0 \\
    --port 8080 \\
    --max-history 10000

Через curl:

  curl -sL https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/${GITHUB_BRANCH}/install_logviewer.sh | sudo bash

  curl -sL https://raw.githubusercontent.com/${GITHUB_OWNER}/${GITHUB_REPO}/${GITHUB_BRANCH}/install_logviewer.sh | sudo bash -s -- --install --host 0.0.0.0 --port 8080

Параметры:

  --install, -i       установка без меню
  --log-path PATH    путь к nginx access.log
  --host IP          IP/host для прослушивания сервиса
  --port PORT        порт сервиса
  --max-history N    сколько последних строк загружать в UI
  --branch BRANCH    ветка GitHub, по умолчанию main
EOF
}

configure_settings() {
  load_existing_config

  echo
  info "Настройки сервиса"
  LOG_PATH="$(ask "Путь к access.log nginx" "$LOG_PATH")"
  HOST="$(ask "IP/host для прослушивания" "$HOST")"
  PORT="$(ask "Порт сервиса" "$PORT")"
  MAX_HISTORY="$(ask "Максимум строк истории" "$MAX_HISTORY")"

  validate_settings
}

validate_settings() {
  if ! [[ "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then
    err "Некорректный порт: $PORT"
    exit 1
  fi

  if ! [[ "$MAX_HISTORY" =~ ^[0-9]+$ ]] || (( MAX_HISTORY < 1 )); then
    err "Некорректный MAX_HISTORY: $MAX_HISTORY"
    exit 1
  fi

  if [[ -z "$HOST" ]]; then
    err "HOST не может быть пустым"
    exit 1
  fi

  if [[ -z "$LOG_PATH" ]]; then
    err "LOG_PATH не может быть пустым"
    exit 1
  fi
}

write_config() {
  cat > "$CONFIG_FILE" <<EOF
LOG_PATH=${LOG_PATH}
HOST=${HOST}
PORT=${PORT}
MAX_HISTORY=${MAX_HISTORY}
EOF

  chmod 0644 "$CONFIG_FILE"
  ok "Конфиг создан: $CONFIG_FILE"
}

fresh_download() {
  local file_name="$1"
  local dest="$2"
  local tmp
  local url
  local cache_buster

  cache_buster="$(date +%s%N)"
  url="${GITHUB_RAW_BASE}/${file_name}?nocache=${cache_buster}"
  tmp="$(mktemp)"

  info "Загрузка свежей версии ${file_name} из GitHub..."

  if command -v curl >/dev/null 2>&1; then
    curl -fL \
      -H "Cache-Control: no-cache, no-store, must-revalidate" \
      -H "Pragma: no-cache" \
      -H "Expires: 0" \
      -A "nginx-log-analyzer-installer/${cache_buster}" \
      "$url" \
      -o "$tmp"
  else
    wget \
      --no-cache \
      --header="Cache-Control: no-cache, no-store, must-revalidate" \
      --header="Pragma: no-cache" \
      --header="Expires: 0" \
      -O "$tmp" \
      "$url"
  fi

  mv "$tmp" "$dest"
  chmod 0755 "$dest"
  ok "Файл обновлён: $dest"
}

write_service() {
  cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Nginx Log Analyzer
After=network-online.target nginx.service
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${CONFIG_FILE}
ExecStart=/usr/bin/python3 ${SCRIPT_PATH} \${LOG_PATH} \${PORT} --host \${HOST} --max-history \${MAX_HISTORY}
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

  chmod 0644 "$SERVICE_FILE"
  ok "Systemd-unit создан: $SERVICE_FILE"
}

install_app() {
  need_root
  require_cmds
  validate_settings

  info "Установка ${SERVICE_NAME}"

  mkdir -p "$INSTALL_DIR"
  chmod 0755 "$INSTALL_DIR"

  fresh_download "$SCRIPT_NAME" "$SCRIPT_PATH"

  info "Проверка синтаксиса Python..."
  python3 -m py_compile "$SCRIPT_PATH"
  ok "Python-скрипт прошёл проверку"

  write_config
  write_service

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

update_files_only() {
  need_root
  require_cmds

  mkdir -p "$INSTALL_DIR"
  fresh_download "$SCRIPT_NAME" "$SCRIPT_PATH"

  info "Проверка синтаксиса Python..."
  python3 -m py_compile "$SCRIPT_PATH"

  systemctl restart "$SERVICE_NAME" 2>/dev/null || true
  ok "Файлы обновлены"
}

show_info() {
  load_existing_config

  local host_ip
  host_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"

  echo
  echo "────────────────────────────────────────"
  ok "Информация"
  echo "Сервис:        $SERVICE_NAME"
  echo "Файл сервиса:  $SERVICE_FILE"
  echo "Конфиг:        $CONFIG_FILE"
  echo "Скрипт:        $SCRIPT_PATH"
  echo "Лог nginx:     $LOG_PATH"
  echo "Host/IP:       $HOST"
  echo "Порт:          $PORT"
  echo "Max history:   $MAX_HISTORY"
  echo
  echo "Доступ:"
  echo "  http://127.0.0.1:${PORT}"

  if [[ -n "$host_ip" ]]; then
    echo "  http://${host_ip}:${PORT}"
  fi

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
  load_existing_config

  echo "────────────────────────────────────────"
  info "Диагностика ${SERVICE_NAME}"
  echo

  echo "1. systemd:"
  systemctl is-enabled "$SERVICE_NAME" 2>/dev/null || true
  systemctl is-active "$SERVICE_NAME" 2>/dev/null || true
  echo

  echo "2. Конфиг:"
  if [[ -f "$CONFIG_FILE" ]]; then
    cat "$CONFIG_FILE"
  else
    warn "Конфиг не найден"
  fi
  echo

  echo "3. Файлы:"
  ls -l "$SCRIPT_PATH" 2>/dev/null || warn "Нет $SCRIPT_PATH"
  ls -l "$SERVICE_FILE" 2>/dev/null || warn "Нет $SERVICE_FILE"
  ls -l "$LOG_PATH" 2>/dev/null || warn "Лог не найден: $LOG_PATH"
  echo

  echo "4. Проверка Python:"
  if [[ -f "$SCRIPT_PATH" ]]; then
    python3 -m py_compile "$SCRIPT_PATH" && ok "Синтаксис Python OK"
  fi
  echo

  echo "5. Проверка HTTP:"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS "http://127.0.0.1:${PORT}/health" || true
  else
    warn "curl не установлен"
  fi
  echo
  echo

  echo "6. Последние логи сервиса:"
  journalctl -u "$SERVICE_NAME" -n 50 --no-pager || true
  echo "────────────────────────────────────────"
}

restart_app() {
  need_root
  systemctl restart "$SERVICE_NAME"
  systemctl status "$SERVICE_NAME" --no-pager || true
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

  ok "Удаление завершено"
}

menu() {
  while true; do
    load_existing_config

    clear || true
    echo "Nginx Log Analyzer installer"
    echo "────────────────────────────────────────"
    echo "Текущие настройки:"
    echo "  LOG_PATH     = $LOG_PATH"
    echo "  HOST         = $HOST"
    echo "  PORT         = $PORT"
    echo "  MAX_HISTORY  = $MAX_HISTORY"
    echo "────────────────────────────────────────"
    echo "1) Установить / переустановить с настройками"
    echo "2) Изменить настройки без переустановки"
    echo "3) Обновить logviewer.py из GitHub и перезапустить"
    echo "4) Статус сервиса"
    echo "5) Последние логи"
    echo "6) Смотреть логи в реальном времени"
    echo "7) Диагностика"
    echo "8) Перезапустить сервис"
    echo "9) Удалить сервис"
    echo "0) Выход"
    echo "────────────────────────────────────────"

    choice="$(ask "Выберите пункт" "1")"

    case "$choice" in
      1)
        configure_settings
        install_app
        pause
        ;;
      2)
        configure_settings
        write_config
        write_service
        systemctl daemon-reload
        systemctl restart "$SERVICE_NAME" 2>/dev/null || true
        ok "Настройки применены"
        pause
        ;;
      3)
        update_files_only
        pause
        ;;
      4)
        status_app
        pause
        ;;
      5)
        logs_app
        pause
        ;;
      6)
        follow_logs_app
        ;;
      7)
        diagnostics
        pause
        ;;
      8)
        restart_app
        pause
        ;;
      9)
        uninstall_app
        pause
        ;;
      0)
        exit 0
        ;;
      *)
        warn "Неверный пункт"
        pause
        ;;
    esac
  done
}

need_root
load_existing_config
parse_args "$@"

if [[ "$AUTO_INSTALL" == "true" ]]; then
  validate_settings
  install_app
else
  if has_tty; then
    menu
  else
    validate_settings
    install_app
  fi
fi
