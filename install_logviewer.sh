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
VERSION="2.1"

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
        local size=$(stat -c%s "${SCRIPT_PATH}" 2>/dev/null || stat -f%z "${SCRIPT_PATH}" 2>/dev/null)
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
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        print_success "Сервис активен"
    else
        print_error "Сервис не активен"
    fi
    echo ""
    systemctl status "${SERVICE_NAME}" --no-pager 2>/dev/null | head -n 15
    echo ""
    if ss -tlnp 2>/dev/null | grep -q ":${PORT}"; then
        print_success "Порт ${PORT} слушается"
        ss -tlnp 2>/dev/null | grep ":${PORT}"
    else
        print_warning "Порт ${PORT} не слушается"
    fi
}

# === Логи ===
show_logs() {
    print_header "ЛОГИ В РЕАЛЬНОМ ВРЕМЕНИ"
    print_info "Нажмите Ctrl+C для выхода"
    echo ""
    journalctl -u "${SERVICE_NAME}" -f
}

# === Перезапуск ===
restart_service() {
    print_info "Перезапуск сервиса..."
    systemctl restart "${SERVICE_NAME}"
    sleep 2
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        print_success "Сервис перезапущен"
    else
        print_error "Ошибка перезапуска"
    fi
}

# === Остановка ===
stop_service() {
    print_info "Остановка сервиса..."
    systemctl stop "${SERVICE_NAME}"
    print_success "Сервис остановлен"
}

# === Удаление ===
full_uninstall() {
    print_header "ПОЛНОЕ УДАЛЕНИЕ"
    echo -n -e "${YELLOW}Вы уверены? (y/N): ${NC}"
    read -r confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        print_info "Отмена"
        return
    fi
    
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
    
    # Проверяем зависимости
    if ! command -v python3 &> /dev/null; then
        print_error "Python3 не установлен"
        return 1
    fi
    print_success "Python3: $(python3 --version)"
    
    if ! command -v curl &> /dev/null && ! command -v wget &> /dev/null; then
        print_error "curl или wget не установлены"
        return 1
    fi
    print_success "curl/wget установлены"
    
    clean_old_files
    download_from_github || return 1
    
    # Проверяем, что файл скачался
    if [ ! -s "${SCRIPT_PATH}" ]; then
        print_error "Скрипт пустой или не скачался"
        return 1
    fi
    
    create_systemd_service
    install_and_start || return 1
    
    # Получаем IP
    LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    if [ -z "${LOCAL_IP}" ]; then
        LOCAL_IP=$(curl -s ifconfig.me 2>/dev/null)
    fi
    
    echo ""
    print_success "УСТАНОВКА ЗАВЕРШЕНА!"
    echo ""
    echo -e "${GREEN}🔗 ДОСТУП:${NC}"
    echo -e "   Локально:  ${BLUE}http://127.0.0.1:${PORT}${NC}"
    echo -e "   По сети:   ${BLUE}http://${LOCAL_IP}:${PORT}${NC}"
    echo ""
}

# === Обновление скрипта ===
update_script() {
    print_header "ОБНОВЛЕНИЕ СКРИПТА"
    
    systemctl stop "${SERVICE_NAME}" 2>/dev/null
    rm -f "${SCRIPT_PATH}"
    download_from_github || return 1
    systemctl start "${SERVICE_NAME}"
    sleep 2
    
    if systemctl is-active --quiet "${SERVICE_NAME}"; then
        print_success "Скрипт обновлён, сервис перезапущен"
    else
        print_error "Сервис не запустился"
        journalctl -u "${SERVICE_NAME}" -n 20 --no-pager
    fi
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

# === Пауза после выполнения ===
pause() {
    echo ""
    echo -n "Нажмите Enter для продолжения..."
    read -r
}

# === Главный цикл ===
main() {
    # Если есть аргумент командной строки
    case "$1" in
        install) full_install; exit 0 ;;
        update) update_script; exit 0 ;;
        status) show_status; exit 0 ;;
        logs) show_logs; exit 0 ;;
        restart) restart_service; exit 0 ;;
        stop) stop_service; exit 0 ;;
        uninstall) full_uninstall; exit 0 ;;
    esac
    
    # Интерактивный режим
    while true; do
        show_menu
        read -r choice
        
        case "$choice" in
            1) full_install; pause ;;
            2) update_script; pause ;;
            3) show_status; pause ;;
            4) show_logs ;;  # Без паузы, так как это интерактивный режим
            5) restart_service; pause ;;
            6) stop_service; pause ;;
            7) clean_old_files; pause ;;
            8) full_uninstall; pause ;;
            0) 
                echo ""
                print_info "До свидания!"
                exit 0
                ;;
            *)
                print_error "Неверный выбор. Пожалуйста, введите число от 0 до 8"
                sleep 1.5
                ;;
        esac
    done
}

# === Запуск ===
main "$1"
