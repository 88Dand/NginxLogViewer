#!/bin/bash

# === Конфигурация ===
SERVICE_NAME="nginx-log-analyzer"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
INSTALL_DIR="/home/rps"
SCRIPT_NAME="logviewer.py"
SCRIPT_PATH="${INSTALL_DIR}/${SCRIPT_NAME}"
LOG_PATH_DEFAULT="/var/www/api/nginx-logs/site.access.log"
GITHUB_RAW_URL="https://raw.githubusercontent.com/88Dand/NginxLogViewer/main/logviewer.py"
PORT=8080
VERSION="2.0"

# === Цветной вывод ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# === Функции ===
print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[✓]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[!]${NC} $1"; }
print_error() { echo -e "${RED}[✗]${NC} $1"; }

print_header() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
}

# === Проверка зависимостей ===
check_dependencies() {
    print_info "Проверка зависимостей..."
    
    if ! command -v python3 &> /dev/null; then
        print_error "Python3 не установлен"
        exit 1
    fi
    print_success "Python3: $(python3 --version)"
    
    if ! command -v curl &> /dev/null && ! command -v wget &> /dev/null; then
        print_error "curl или wget не установлены"
        exit 1
    fi
    print_success "curl/wget установлены"
    
    echo ""
}

# === Очистка старых файлов ===
clean_old_files() {
    print_info "Очистка старых файлов..."
    
    systemctl stop "${SERVICE_NAME}" 2>/dev/null
    rm -f "${SCRIPT_PATH}"
    rm -rf "${INSTALL_DIR}/__pycache__"
    find "${INSTALL_DIR}" -name "*.pyc" -delete 2>/dev/null
    
    print_success "Очистка завершена"
}

# === Скачивание с GitHub ===
download_from_github() {
    print_info "Скачивание с GitHub..."
    
    if command -v curl &> /dev/null; then
        curl -sL "${GITHUB_RAW_URL}" -o "${SCRIPT_PATH}"
    else
        wget -q "${GITHUB_RAW_URL}" -O "${SCRIPT_PATH}"
    fi
    
    if [ -f "${SCRIPT_PATH}" ] && [ -s "${SCRIPT_PATH}" ]; then
        local size=$(stat -c%s "${SCRIPT_PATH}")
        print_success "Скачано ${size} байт"
        return 0
    else
        print_error "Не удалось скачать"
        return 1
    fi
}

# === Создание сервиса ===
create_systemd_service() {
    print_info "Создание systemd сервиса..."
    
    cat > "${SERVICE_FILE}" << EOF
[Unit]
Description=Nginx Log Analyzer Pro
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=/usr/bin/python3 ${SCRIPT_PATH} ${LOG_PATH_DEFAULT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    print_success "Сервис создан"
}

# === Установка и запуск ===
install_and_start() {
    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}"
    systemctl restart "${SERVICE_NAME}"
    sleep 2
    
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        print_success "Сервис запущен"
        return 0
    else
        print_error "Сервис не запустился"
        journalctl -u "${SERVICE_NAME}" -n 20 --no-pager
        return 1
    fi
}

# === Показать статус ===
show_status() {
    print_header "СТАТУС СЕРВИСА"
    systemctl status "${SERVICE_NAME}" --no-pager | head -n 15
    echo ""
    ss -tlnp | grep ":${PORT}" 2>/dev/null || echo "Порт ${PORT} не слушается"
}

# === Логи ===
show_logs() {
    print_header "ЛОГИ (Ctrl+C для выхода)"
    journalctl -u "${SERVICE_NAME}" -f
}

# === Перезапуск ===
restart_service() {
    print_info "Перезапуск..."
    systemctl restart "${SERVICE_NAME}"
    sleep 2
    show_status
}

# === Остановка ===
stop_service() {
    print_info "Остановка..."
    systemctl stop "${SERVICE_NAME}"
    print_success "Сервис остановлен"
}

# === Удаление ===
full_uninstall() {
    print_header "ПОЛНОЕ УДАЛЕНИЕ"
    read -p "Вы уверены? (y/N): " confirm
    [[ ! "$confirm" =~ ^[Yy]$ ]] && return
    
    systemctl stop "${SERVICE_NAME}" 2>/dev/null
    systemctl disable "${SERVICE_NAME}" 2>/dev/null
    rm -f "${SERVICE_FILE}"
    rm -f "${SCRIPT_PATH}"
    rm -rf "${INSTALL_DIR}/__pycache__"
    systemctl daemon-reload
    
    print_success "Удаление завершено"
}

# === Полная установка ===
full_install() {
    print_header "ПОЛНАЯ УСТАНОВКА"
    check_dependencies
    clean_old_files
    download_from_github || exit 1
    create_systemd_service
    install_and_start || exit 1
    
    LOCAL_IP=$(hostname -I | awk '{print $1}')
    [[ -z "${LOCAL_IP}" ]] && LOCAL_IP=$(curl -s ifconfig.me 2>/dev/null)
    
    echo ""
    print_success "УСТАНОВКА ЗАВЕРШЕНА!"
    echo -e "${GREEN}🔗 Доступ: http://${LOCAL_IP}:${PORT}${NC}"
    echo -e "   Локально: http://127.0.0.1:${PORT}"
}

# === Обновление скрипта ===
update_script() {
    print_header "ОБНОВЛЕНИЕ"
    systemctl stop "${SERVICE_NAME}" 2>/dev/null
    rm -f "${SCRIPT_PATH}"
    download_from_github || exit 1
    systemctl start "${SERVICE_NAME}"
    sleep 2
    systemctl is-active --quiet "${SERVICE_NAME}" && print_success "Обновлено" || print_error "Ошибка"
}

# === Меню ===
show_menu() {
    clear
    print_header "NGINX LOG ANALYZER PRO v${VERSION}"
    echo ""
    echo -e "  ${GREEN}1${NC}) 🚀 Полная установка (очистка + загрузка + запуск)"
    echo -e "  ${GREEN}2${NC}) 🔄 Только обновление скрипта (с GitHub)"
    echo -e "  ${GREEN}3${NC}) 📊 Показать статус сервиса"
    echo -e "  ${GREEN}4${NC}) 📜 Показать логи в реальном времени"
    echo -e "  ${GREEN}5${NC}) 🔄 Перезапустить сервис"
    echo -e "  ${GREEN}6${NC}) ⏹️ Остановить сервис"
    echo -e "  ${GREEN}7${NC}) 🧹 Очистить кэш и старые файлы"
    echo -e "  ${GREEN}8${NC}) 🗑️ Полное удаление"
    echo -e "  ${GREEN}0${NC}) 🚪 Выход"
    echo ""
    echo -e "${CYAN}────────────────────────────────────────${NC}"
    echo -n -e "${BLUE}Выберите действие [0-8]: ${NC}"
}

# === Главный цикл ===
main() {
    case "$1" in
        install) full_install ;;
        update) update_script ;;
        status) show_status ;;
        logs) show_logs ;;
        restart) restart_service ;;
        stop) stop_service ;;
        uninstall) full_uninstall ;;
        *)
            while true; do
                show_menu
                read -r choice
                echo ""
                case $choice in
                    1) full_install ;;
                    2) update_script ;;
                    3) show_status ;;
                    4) show_logs ;;
                    5) restart_service ;;
                    6) stop_service ;;
                    7) clean_old_files ;;
                    8) full_uninstall ;;
                    0) print_info "До свидания!"; exit 0 ;;
                    *) print_error "Неверный выбор" ;;
                esac
                echo ""
                read -p "Нажмите Enter для продолжения..."
            done
            ;;
    esac
}

main "$1"
